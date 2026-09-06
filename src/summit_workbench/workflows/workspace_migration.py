"""工作区 marker schema 迁移（P1-02）。

迁移是显式、可审计且可回滚的本地事务：先在工作区锁内确认 Git 远端处于
ready，再生成本机备份，原子写入每一步迁移，最后用独立的 ``wb: migrate``
提交并推送。旧版本不会被静默改写，未知未来 schema 也不会被猜测处理。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from summit_workbench import __version__
from summit_workbench.config.app_support import PROFILE_DIR_MODE, backups_dir
from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.domain.workspace import SUPPORTED_WORKSPACE_SCHEMA, WorkspaceManifest
from summit_workbench.repositories._atomic import atomic_write_bytes, atomic_write_text
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    GitRemoteSchemeUnsupported,
    require_https_remote,
)
from summit_workbench.repositories.workspace_manifest import (
    WorkspaceManifestError,
    load_workspace_manifest,
    manifest_path,
)

_MIGRATION_HISTORY_FIELD = "migration_history"
_MIGRATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,199}$")
_BACKUP_SCHEMA_VERSION = 1


MigrationFunction = Callable[[dict[str, Any]], dict[str, Any]]
AfterWriteFunction = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class MigrationStep:
    """一个不可跳过的单版本迁移边。"""

    from_version: int
    to_version: int
    migration_id: str
    apply: MigrationFunction
    after_write: AfterWriteFunction | None = None

    def __post_init__(self) -> None:
        if self.from_version < 1 or self.to_version != self.from_version + 1:
            raise ValueError("migration 必须是相邻版本的 from_version -> to_version")
        if not _MIGRATION_ID_RE.fullmatch(self.migration_id):
            raise ValueError("migration_id 必须是 3-200 位小写字母、数字或连字符")


class MigrationRegistry:
    """按 source version 唯一登记迁移边，并拒绝跳版本/重复边。"""

    def __init__(self, steps: Iterable[MigrationStep] = ()) -> None:
        self._steps: dict[int, MigrationStep] = {}
        for step in steps:
            if step.from_version in self._steps:
                raise ValueError(f"重复 migration source version：{step.from_version}")
            self._steps[step.from_version] = step

    def next_step(self, version: int) -> MigrationStep | None:
        """返回从给定版本开始的下一条迁移边。"""
        return self._steps.get(version)

    def path(self, from_version: int, to_version: int) -> tuple[MigrationStep, ...]:
        """解析完整连续路径；任何缺边都拒绝，不允许跳跃迁移。"""
        steps: list[MigrationStep] = []
        current = from_version
        while current < to_version:
            step = self.next_step(current)
            if step is None:
                raise WorkspaceMigrationError(
                    f"没有从 workspace schema v{current} 迁移到 v{to_version} 的完整路径",
                    code="migration_path_missing",
                )
            steps.append(step)
            current = step.to_version
        if current != to_version:
            raise WorkspaceMigrationError(
                f"workspace schema v{from_version} 不能迁移到 v{to_version}",
                code="migration_path_invalid",
            )
        return tuple(steps)


@dataclass(frozen=True)
class MigrationResult:
    """迁移结果；路径只指向本机 backups，不进入 vault。"""

    status: str
    workspace_id: str
    from_version: int
    to_version: int
    backup_dir: Path | None
    backup_manifest: Path | None
    backup_snapshot: Path | None


class WorkspaceMigrationError(RuntimeError):
    """迁移拒绝或失败；``failure_report`` 指向本机脱敏失败报告。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "migration_rejected",
        failure_report: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.failure_report = failure_report


def _migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """v1 marker 增加迁移历史并升级 schema envelope；未知字段原样保留。"""
    if raw.get("schema_version") != 1:
        raise ValueError("v1 -> v2 迁移收到非 v1 marker")
    history = raw.get(_MIGRATION_HISTORY_FIELD, [])
    if not isinstance(history, list) or not all(isinstance(item, str) for item in history):
        raise ValueError("migration_history 不是字符串列表")
    updated = dict(raw)
    updated["schema_version"] = 2
    updated[_MIGRATION_HISTORY_FIELD] = [*history]
    if "workspace-v1-to-v2" not in updated[_MIGRATION_HISTORY_FIELD]:
        updated[_MIGRATION_HISTORY_FIELD].append("workspace-v1-to-v2")
    return updated


def default_migration_registry() -> MigrationRegistry:
    """当前生产支持的迁移登记表。"""
    return MigrationRegistry(
        [
            MigrationStep(
                from_version=1,
                to_version=2,
                migration_id="workspace-v1-to-v2",
                apply=_migrate_v1_to_v2,
            )
        ]
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _backup_name(workspace_id: str, from_version: int, to_version: int, now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{workspace_id}-migration-v{from_version}-to-v{to_version}-{stamp}"


def _latest_backup(
    workspace_id: str, *, home: Path | None, from_version: int, to_version: int
) -> tuple[Path, Path, Path] | None:
    root = backups_dir(home=home)
    prefix = f"{workspace_id}-migration-v{from_version}-to-v{to_version}-"
    candidates = sorted(p for p in root.glob(f"{prefix}*") if p.is_dir())
    if not candidates:
        return None
    directory = candidates[-1]
    manifest = directory / "manifest.json"
    snapshot = directory / "files" / ".summit-workbench" / "workspace.json"
    if not manifest.is_file() or not snapshot.is_file():
        return None
    return directory, manifest, snapshot


def _safe_error(exc: BaseException) -> str:
    """失败报告不回显可能包含远端凭据的 URL。"""
    text = str(exc).replace("\n", " ").strip()
    return re.sub(r"https?://[^\s]+", "<redacted-url>", text)[:500]


def _write_failure_report(
    backup_dir: Path,
    *,
    error: BaseException,
    restored: bool,
    committed_head: str | None,
) -> Path:
    path = backup_dir / "failure.json"
    payload = {
        "schema_version": _BACKUP_SCHEMA_VERSION,
        "created_at": _now().isoformat(),
        "error_type": type(error).__name__,
        "error": _safe_error(error),
        "restored": restored,
        "rollback_commit": committed_head,
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _require_ready(repo: GitRepo) -> None:
    if not repo.is_git_repo():
        raise WorkspaceMigrationError(
            "工作区不是 Git 仓库，迁移要求同步状态 ready",
            code="migration_sync_not_ready",
        )
    if not repo.has_remote() or not repo.has_upstream():
        raise WorkspaceMigrationError(
            "工作区没有可验证的 Git 远端，迁移要求同步状态 ready",
            code="migration_sync_not_ready",
        )
    try:
        remote_url = repo.remote_url("origin")
        if not remote_url:
            raise GitRemoteSchemeUnsupported("生产同步只支持 HTTPS remote")
        require_https_remote(remote_url)
    except GitRemoteSchemeUnsupported as exc:
        raise WorkspaceMigrationError(
            "当前 Git remote 不是 HTTPS，请先在设置中心完成 remote 规范化",
            code="remote_scheme_unsupported",
        ) from exc
    if repo.is_dirty():
        raise WorkspaceMigrationError(
            "工作树存在未提交改动，迁移要求先达到 ready",
            code="migration_dirty_tree",
        )
    try:
        repo.fetch()
        counts = repo.ahead_behind()
    except GitError as exc:
        raise WorkspaceMigrationError(
            "Git 远端不可达，迁移已停止",
            code="migration_remote_unreachable",
        ) from exc
    if counts != AheadBehind(ahead=0, behind=0):
        raise WorkspaceMigrationError(
            f"同步状态不是 ready（ahead={counts.ahead}, behind={counts.behind}）",
            code="migration_sync_not_ready",
        )


def _write_backup(
    vault_dir: Path,
    *,
    home: Path | None,
    workspace_id: str,
    from_version: int,
    to_version: int,
    app_version: str,
    git_head: str,
    now: datetime,
) -> tuple[Path, Path, Path, bytes]:
    original_path = manifest_path(vault_dir)
    original = original_path.read_bytes()
    directory = backups_dir(home=home) / _backup_name(workspace_id, from_version, to_version, now)
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(PROFILE_DIR_MODE)
    snapshot = directory / "files" / ".summit-workbench" / "workspace.json"
    atomic_write_bytes(snapshot, original, ensure_parents=True)
    manifest = directory / "manifest.json"
    manifest_payload = {
        "schema_version": _BACKUP_SCHEMA_VERSION,
        "kind": "workspace-migration",
        "created_at": now.isoformat(),
        "app_version": app_version,
        "workspace_id": workspace_id,
        "from_version": from_version,
        "to_version": to_version,
        "git_head": git_head,
        "files": [
            {
                "path": ".summit-workbench/workspace.json",
                "snapshot": "files/.summit-workbench/workspace.json",
                "sha256": _sha256(original),
                "size": len(original),
            }
        ],
    }
    atomic_write_text(
        manifest,
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        ensure_parents=True,
    )
    return directory, manifest, snapshot, original


def _restore_snapshot(path: Path, original: bytes) -> None:
    atomic_write_bytes(path, original, ensure_parents=True)


def migrate_workspace(
    vault_dir: Path,
    *,
    home: Path | None = None,
    app_version: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    confirmed_device_id: str | None = None,
    repo: GitRepo | None = None,
    registry: MigrationRegistry | None = None,
) -> MigrationResult:
    """在全部安全门通过后，把 workspace marker 迁移到当前 schema。"""
    registry = registry or default_migration_registry()
    version = app_version or __version__
    git = repo or GitRepo(vault_dir, backend_kind="dulwich", workspace_id=workspace_id)

    try:
        with workspace_lock(vault_dir.parent):
            try:
                manifest = load_workspace_manifest(vault_dir)
            except WorkspaceManifestError as exc:
                raise WorkspaceMigrationError(
                    "workspace marker 损坏，不能猜测迁移",
                    code="migration_marker_invalid",
                ) from exc
            if manifest is None:
                raise WorkspaceMigrationError(
                    "workspace marker 缺失，请先通过升级工作区流程生成 marker",
                    code="migration_marker_missing",
                )
            if workspace_id is not None and manifest.workspace_id != workspace_id:
                raise WorkspaceMigrationError(
                    "workspace marker 与当前 profile 不一致",
                    code="migration_workspace_mismatch",
                )
            ws_id = manifest.workspace_id
            if manifest.schema_version > SUPPORTED_WORKSPACE_SCHEMA:
                raise WorkspaceMigrationError(
                    "workspace schema "
                    f"v{manifest.schema_version} 高于当前支持版本 "
                    f"v{SUPPORTED_WORKSPACE_SCHEMA}",
                    code="migration_schema_too_new",
                )
            if manifest.schema_version == SUPPORTED_WORKSPACE_SCHEMA:
                latest = _latest_backup(
                    ws_id,
                    home=home,
                    from_version=SUPPORTED_WORKSPACE_SCHEMA - 1,
                    to_version=SUPPORTED_WORKSPACE_SCHEMA,
                )
                return MigrationResult(
                    status="already-current",
                    workspace_id=ws_id,
                    from_version=SUPPORTED_WORKSPACE_SCHEMA,
                    to_version=SUPPORTED_WORKSPACE_SCHEMA,
                    backup_dir=latest[0] if latest else None,
                    backup_manifest=latest[1] if latest else None,
                    backup_snapshot=latest[2] if latest else None,
                )
            if manifest.schema_version < 1:
                raise WorkspaceMigrationError(
                    f"workspace schema v{manifest.schema_version} 不可迁移",
                    code="migration_schema_unsupported",
                )
            if not device_id or not confirmed_device_id or device_id != confirmed_device_id:
                raise WorkspaceMigrationError(
                    "必须明确确认当前设备执行 workspace 迁移（迁移设备确认不匹配）",
                    code="migration_device_not_confirmed",
                )

            steps = registry.path(manifest.schema_version, SUPPORTED_WORKSPACE_SCHEMA)
            _require_ready(git)
            original_path = manifest_path(vault_dir)
            original = original_path.read_bytes()
            backup_dir, backup_manifest, backup_snapshot, _ = _write_backup(
                vault_dir,
                home=home,
                workspace_id=ws_id,
                from_version=manifest.schema_version,
                to_version=SUPPORTED_WORKSPACE_SCHEMA,
                app_version=version,
                git_head=git.head_revision(),
                now=_now(),
            )
            raw = json.loads(original)
            if not isinstance(raw, dict):
                raise ValueError("workspace marker 顶层不是 JSON object")
            current = dict(raw)
            committed_head: str | None = None
            try:
                for step in steps:
                    if current.get("schema_version") != step.from_version:
                        raise ValueError(f"migration {step.migration_id} 收到错误 schema version")
                    current = step.apply(current)
                    # 保留旧 reader 兼容，同时把写门提升到执行迁移的 App 版本；旧 App
                    # 会因未来 schema 自动进入只读保护，新 App 再按 min_writer 判定。
                    if step.to_version == SUPPORTED_WORKSPACE_SCHEMA:
                        current["min_writer_version"] = version
                    validated = WorkspaceManifest.model_validate(current)
                    current = validated.model_dump(mode="json") | {
                        key: value
                        for key, value in current.items()
                        if key not in WorkspaceManifest.model_fields
                    }
                    atomic_write_text(
                        original_path,
                        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                    )
                    if step.after_write is not None:
                        step.after_write(current)
                if current.get("schema_version") != SUPPORTED_WORKSPACE_SCHEMA:
                    raise ValueError("migration 没有到达当前 workspace schema")
                git.add([".summit-workbench/workspace.json"])
                if not git.has_staged_changes([".summit-workbench/workspace.json"]):
                    raise ValueError("迁移后的 workspace marker 没有形成 Git 变更")
                git.commit(
                    "wb: migrate workspace "
                    f"v{manifest.schema_version} -> v{SUPPORTED_WORKSPACE_SCHEMA}"
                )
                committed_head = git.head_revision()
                git.push()
            except BaseException as exc:
                if committed_head is not None:
                    try:
                        git.revert(committed_head)
                    except BaseException:
                        pass
                restored = False
                try:
                    _restore_snapshot(original_path, original)
                    restored = original_path.read_bytes() == original
                except BaseException:
                    restored = False
                failure_report = _write_failure_report(
                    backup_dir,
                    error=exc,
                    restored=restored,
                    committed_head=committed_head,
                )
                raise WorkspaceMigrationError(
                    f"workspace 迁移失败，已回滚：{_safe_error(exc)}",
                    code="migration_failed",
                    failure_report=failure_report,
                ) from exc
            return MigrationResult(
                status="migrated",
                workspace_id=ws_id,
                from_version=manifest.schema_version,
                to_version=SUPPORTED_WORKSPACE_SCHEMA,
                backup_dir=backup_dir,
                backup_manifest=backup_manifest,
                backup_snapshot=backup_snapshot,
            )
    except LockBusy as exc:
        raise WorkspaceMigrationError(
            "工作区正被另一个任务使用，迁移未执行",
            code="migration_busy",
        ) from exc
