"""新建 / 升级 / 连接工作区服务（P0-08，服务层，供 CLI 与 Web API 共用）。

三条流程：
- **create-new**：选 Work Root → staging 目录 → 原子改名到 ``<work_root>/_vault``；
  只从 allowlist 模板拷贝种子文件（inbox/conventions，``{{date}}`` 填充），写
  workspace marker，建本机 profile 并设为 active。目标 ``_vault`` 已存在/非空即拒绝。
- **upgrade-existing**：旧 vault（无 marker）→ 只读预检 → Application Support 下
  timestamped 备份（只备份将被修改的 marker/config 快照，不复制整个 vault）→
  写 marker + profile。**不改动任何既有业务文件**（内容哈希不变）。
- **connect-local**：已 clone/拷贝的带 marker vault → 校验 schema 兼容（cannot-open
  拒绝，提示升级 App）→ 建本机 profile。

硬边界（P0-08）：
- 全程**不运行系统 git**、不 ``git init``（新 vault 的 git 只经 P0-09 backend）；
  仅探测目录是否含 ``.git`` 作为预检信息。
- 目标位于网盘同步路径（iCloud Drive/Dropbox/OneDrive/Google Drive 等）一律拒绝：
  网盘会同步含 ``.git`` 的工作区导致仓库损坏（验收禁止）。
- 模板复制前做**个人化卫生扫描**：绝对用户路径、本机 home、仓库路径、
  ``WB_BLOCKED_ACCOUNTS`` 中的账号命中即拒绝拷贝（命中即拒绝）。
- 失败必须回滚本次创建的 marker/profile/registry；绝不删除用户原有目录。
- 只写本机 Application Support 与用户显式选择的目标目录，全程用临时 HOME 可完整测试。
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.app_support import PROFILE_DIR_MODE, backups_dir
from summit_workbench.domain.onboarding import (
    OnboardingFlow,
    OnboardingResult,
    PreflightReport,
)
from summit_workbench.domain.workspace import (
    Compatibility,
    DeviceRole,
    LocalProfile,
    WorkspaceManifest,
    evaluate_manifest_compatibility,
)
from summit_workbench.repositories.profile_registry import (
    drop_profile,
    ensure_device_identity,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import (
    WorkspaceManifestError,
    load_workspace_manifest,
    write_workspace_manifest,
)

# vault 种子模板 allowlist：仅这些模板会被复制进新 vault（其余为内容模板，不直接种入）。
TEMPLATE_TARGETS: dict[str, str] = {
    "inbox.template.md": "inbox.md",
    "conventions.template.md": "conventions.md",
}
_TEMPLATE_DATE_TOKEN = "{{date}}"

# 常见网盘同步目录名（大小写不敏感，命中任一祖先即视为网盘路径）。
_CLOUD_STORAGE_MARKERS = frozenset(
    {
        "icloud",
        "icloud drive",
        "dropbox",
        "onedrive",
        "google drive",
        "box",
        "box sync",
        "mobile documents",
        "cloudstorage",
        "com.apple.clouddocs",
    }
)

_MIN_SPACE_BYTES = 64 * 1024 * 1024  # 创建新工作区的空间下限
_TEMPLATES_DIR_ENV = "WB_VAULT_TEMPLATES"
_BLOCKED_ACCOUNTS_ENV = "WB_BLOCKED_ACCOUNTS"
_HOME_PATH_RE = re.compile(r"/Users/[^/\s'\"]+")


class OnboardingError(RuntimeError):
    """onboarding 被拒绝或失败；``reasons`` 为可解释的阻断/失败理由。"""

    def __init__(self, message: str, *, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.reasons = list(reasons or [])

    def __str__(self) -> str:
        message = str(self.args[0])
        if not self.reasons:
            return message
        return f"{message}：{'；'.join(self.reasons)}"


def current_app_version() -> str:
    """当前 App 版本（新 marker 的 min_reader/min_writer 默认值）。"""
    try:
        return importlib.metadata.version("summit-workbench")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


# ---- CloudStorage / 模板卫生 ----


def detect_cloud_storage(path: Path) -> bool:
    """判断目标或其任一祖先是否位于常见网盘同步目录（iCloud/Dropbox/OneDrive…）。"""
    absolute = path.expanduser().absolute()
    for part in absolute.parts:
        if part.casefold() in _CLOUD_STORAGE_MARKERS:
            return True
    return False


def _blocked_accounts() -> frozenset[str]:
    raw = os.environ.get(_BLOCKED_ACCOUNTS_ENV, "")
    return frozenset(token.strip().casefold() for token in raw.split(",") if token.strip())


def scan_template_hygiene(
    templates_dir: Path,
    *,
    home: Path | None = None,
) -> list[str]:
    """扫描模板目录里的个人化内容；命中返回逐文件/行的说明（命中即拒绝拷贝）。

    规则：绝对 ``/Users/<name>/`` 路径、本机 home 绝对路径、仓库内绝对路径、
    ``WB_BLOCKED_ACCOUNTS``（逗号分隔）中的账号词。
    """
    home_path = (home or Path.home()).expanduser().resolve()
    blocked = _blocked_accounts()
    issues: list[str] = []
    if not templates_dir.is_dir():
        return issues
    for file in sorted(templates_dir.rglob("*")):
        if not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if _HOME_PATH_RE.search(line) or home_path.as_posix() in line:
                issues.append(f"{file.name}:{lineno} 行含个人化绝对路径")
                break
            lowered = line.casefold()
            if blocked and any(account in lowered for account in blocked):
                issues.append(f"{file.name}:{lineno} 行含被禁账号")
                break
    return issues


def default_vault_templates_dir() -> Path:
    """默认 vault 种子模板目录：``WB_VAULT_TEMPLATES`` 覆盖，否则仓库内 templates/vault。

    打包发行时模板应作为包数据内置（P0-13 一并处理）。
    """
    override = os.environ.get(_TEMPLATES_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "templates" / "vault"


# ---- 只读预检 ----


def _first_existing(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return None


def preflight(
    flow: OnboardingFlow,
    target: Path,
    *,
    templates_dir: Path | None = None,
    home: Path | None = None,
    app_version: str | None = None,
) -> PreflightReport:
    """只读预检（不写任何文件）。阻断理由进 ``report.rejections``；ok=False 即拒绝。"""
    target = target.expanduser()
    report = PreflightReport(flow=flow, target=str(target))
    exists = target.exists()
    report.exists = exists
    report.is_dir = target.is_dir()
    anchor = target if exists else _first_existing(target)
    report.writable = bool(anchor and os.access(str(anchor), os.W_OK))
    report.empty = exists and target.is_dir() and not any(target.iterdir())
    if anchor is not None:
        try:
            report.space_free_bytes = shutil.disk_usage(anchor).free
            report.space_ok = report.space_free_bytes > _MIN_SPACE_BYTES
        except OSError:
            report.space_ok = False
    report.cloud_storage = detect_cloud_storage(target)

    version = app_version or current_app_version()
    reject = report.rejections.append

    if flow is OnboardingFlow.CREATE_NEW:
        vault_target = target / "_vault"
        report.vault_target_exists = vault_target.exists()
        if report.vault_target_exists:
            reject(f"目标 {vault_target} 已存在，绝不覆盖（create-new 需要全新目录）")
        if not report.writable:
            reject("目标位置不可写")
        if not report.space_ok:
            reject("目标磁盘可用空间不足")
        if report.cloud_storage:
            reject(
                "目标位于网盘同步目录（iCloud/Dropbox/OneDrive 等）：网盘同步含 .git 的"
                "工作区会损坏 Git 仓库，请换本地目录"
            )
        tpl_dir = templates_dir if templates_dir is not None else default_vault_templates_dir()
        if not tpl_dir.is_dir():
            reject(f"vault 模板目录不可用：{tpl_dir}")
        else:
            issues = scan_template_hygiene(tpl_dir, home=home)
            report.template_issues = issues
            for issue in issues:
                reject(f"模板含个人化内容（{issue}），已拒绝本次创建")

    elif flow in {OnboardingFlow.UPGRADE_EXISTING, OnboardingFlow.CONNECT_LOCAL}:
        if not exists or not target.is_dir():
            reject(f"vault 目录不存在或不是目录：{target}")
            return report
        if not report.writable:
            reject("vault 目录不可写")
        if report.cloud_storage:
            reject(
                "vault 位于网盘同步目录（iCloud/Dropbox/OneDrive 等）：网盘同步含 .git 的"
                "工作区会损坏 Git 仓库，请换本地目录"
            )
        # 仅探测 .git 目录存在，绝不运行 git（P0-09 backend 前）
        report.has_git_dir = (target / ".git").exists()
        try:
            manifest = load_workspace_manifest(target)
        except WorkspaceManifestError:
            manifest = None
        if manifest is not None:
            report.has_marker = True
            report.marker_workspace_id = manifest.workspace_id
            report.compatibility = evaluate_manifest_compatibility(manifest, version)
        if flow is OnboardingFlow.UPGRADE_EXISTING:
            if manifest is not None:
                reject(
                    "该 vault 已是工作区（已有 marker）：升级仅用于无 marker 的旧 vault，"
                    "请用 connect-local 连接"
                )
        else:  # CONNECT_LOCAL
            if manifest is None:
                reject("该 vault 没有 workspace marker：请先用 upgrade-existing 升级")
            elif report.compatibility is Compatibility.CANNOT_OPEN:
                reject(
                    "workspace 要求更高的 App 版本（cannot-open）：请升级 SummitWorkbench 后重试"
                )
    return report


# ---- 完成结果与 marker 构建 ----


def _new_manifest(workspace_id: str, display_name: str, app_version: str) -> WorkspaceManifest:
    return WorkspaceManifest.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": display_name,
            "created_at": datetime.now(UTC).isoformat(),
            "min_reader_version": app_version,
            "min_writer_version": app_version,
        }
    )


def _make_result(
    flow: OnboardingFlow,
    *,
    workspace_id: str,
    work_root: Path,
    vault_dir: Path,
    device_id: str,
    display_name: str,
    backup_dir: Path | None = None,
) -> OnboardingResult:
    return OnboardingResult(
        flow=flow,
        workspace_id=workspace_id,
        work_root=str(work_root),
        vault_dir=str(vault_dir),
        device_id=device_id,
        display_name=display_name,
        created_at=datetime.now(UTC).isoformat(),
        backup_dir=str(backup_dir) if backup_dir is not None else None,
    )


def _copy_seed_templates(staging: Path, templates_dir: Path, day: str | None) -> None:
    """把 allowlist 种子模板拷入 staging（``{{date}}`` 填当天日期）。"""
    stamp = day or datetime.now(UTC).date().isoformat()
    for source_name, target_rel in TEMPLATE_TARGETS.items():
        source = templates_dir / source_name
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        text = text.replace(_TEMPLATE_DATE_TOKEN, stamp)
        destination = staging / target_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")


def _ensure_profile(
    workspace_id: str,
    display_name: str,
    work_root: Path,
    vault_dir: Path,
    home: Path | None,
    device_role: DeviceRole = DeviceRole.SECONDARY,
) -> LocalProfile:
    profile = LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": display_name,
            "work_root": str(work_root),
            "vault_dir": str(vault_dir),
            "device_role": device_role.value,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    save_profile(profile, home=home)
    return profile


def _rollback_created_vault(
    vault: Path | None,
    workspace_id: str,
    home: Path | None,
    created_dirs: list[Path],
) -> None:
    """回滚本次创建：删除我们新建的 vault/marker 与 profile/registry 记录。

    只操作本流程创建的内容与新建的空父目录，绝不触碰用户原有目录。
    """
    if vault is not None and vault.exists():
        shutil.rmtree(vault, ignore_errors=True)
    drop_profile(workspace_id, home=home)
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()  # 只删已空的目录；非空说明有用户内容，保留
        except OSError:
            pass


def create_workspace(
    work_root: Path,
    *,
    display_name: str | None = None,
    device_name: str | None = None,
    day: str | None = None,
    templates_dir: Path | None = None,
    home: Path | None = None,
    app_version: str | None = None,
    device_role: DeviceRole = DeviceRole.AUTOMATION_PRIMARY,
) -> OnboardingResult:
    """create-new：全新 workspace（staging + 原子改名），失败回滚全部产物。"""
    report = preflight(
        OnboardingFlow.CREATE_NEW,
        work_root,
        templates_dir=templates_dir,
        home=home,
        app_version=app_version,
    )
    if not report.ok:
        raise OnboardingError("创建被拒绝", reasons=report.rejections)

    templates = templates_dir if templates_dir is not None else default_vault_templates_dir()
    version = app_version or current_app_version()
    workspace_id = str(uuid4())
    display = display_name or work_root.name or "Workbench"
    vault_target = work_root / "_vault"
    staging: Path | None = None
    created_dirs: list[Path] = []

    try:
        # 准备父目录（记录本次新建的空父目录供回滚清理）
        cursor = work_root
        to_create: list[Path] = []
        while not cursor.exists():
            to_create.append(cursor)
            cursor = cursor.parent
        for directory in reversed(to_create):
            directory.mkdir()
            created_dirs.append(directory)

        staging = Path(
            tempfile.mkdtemp(
                prefix=".summit-workbench-onboarding-",
                dir=work_root if work_root.is_dir() else cursor,
            )
        )
        _copy_seed_templates(staging, templates, day)
        manifest = _new_manifest(workspace_id, display, version)
        write_workspace_manifest(staging, manifest)  # marker 先落在 staging 内
        os.replace(staging, vault_target)  # 原子改名到最终 _vault
        staging = None

        device = ensure_device_identity(home, device_name=device_name)
        _ensure_profile(workspace_id, display, work_root, vault_target, home, device_role)
        if device_role is DeviceRole.AUTOMATION_PRIMARY:
            from summit_workbench.repositories.automation_primary import claim_automation_primary

            claim_automation_primary(vault_target, workspace_id, device.device_id)
        set_active_profile(workspace_id, home=home)
        return _make_result(
            OnboardingFlow.CREATE_NEW,
            workspace_id=workspace_id,
            work_root=work_root,
            vault_dir=vault_target,
            device_id=device.device_id,
            display_name=display,
        )
    except BaseException as exc:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        _rollback_created_vault(vault_target, workspace_id, home, created_dirs)
        if isinstance(exc, OnboardingError):
            raise
        raise OnboardingError(
            f"工作区创建失败，已回滚本次产物：{type(exc).__name__}: {exc}",
            reasons=[str(exc)],
        ) from exc


def upgrade_workspace(
    vault_dir: Path,
    *,
    device_name: str | None = None,
    home: Path | None = None,
    app_version: str | None = None,
    device_role: DeviceRole = DeviceRole.AUTOMATION_PRIMARY,
) -> OnboardingResult:
    """upgrade-existing：旧 vault（无 marker）→ 备份 → 写 marker/profile，内容不动。"""
    report = preflight(
        OnboardingFlow.UPGRADE_EXISTING,
        vault_dir,
        home=home,
        app_version=app_version,
    )
    if not report.ok:
        raise OnboardingError("升级被拒绝", reasons=report.rejections)

    version = app_version or current_app_version()
    workspace_id = str(uuid4())
    display = vault_dir.name or "Workbench"
    backup_root = (
        backups_dir(home=home)
        / f"{vault_dir.name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    )

    try:
        # timestamped 备份：只保存将被修改/涉及的最小快照（不复制整个大 vault）
        backup_root.mkdir(parents=True, exist_ok=True)
        os.chmod(backup_root, PROFILE_DIR_MODE)
        summary = {
            "flow": OnboardingFlow.UPGRADE_EXISTING.value,
            "vault_dir": str(vault_dir),
            "created_at": datetime.now(UTC).isoformat(),
            "marker_before": None,
            "top_level_files": sorted(p.name for p in vault_dir.iterdir() if p.is_file()),
        }
        (backup_root / "upgrade-before.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        marker_file = vault_dir / ".summit-workbench" / "workspace.json"
        if marker_file.is_file():
            (backup_root / "workspace.json.before").write_bytes(marker_file.read_bytes())

        manifest = _new_manifest(workspace_id, display, version)
        write_workspace_manifest(vault_dir, manifest)
        device = ensure_device_identity(home, device_name=device_name)
        _ensure_profile(workspace_id, display, vault_dir.parent, vault_dir, home, device_role)
        if device_role is DeviceRole.AUTOMATION_PRIMARY:
            from summit_workbench.repositories.automation_primary import claim_automation_primary

            claim_automation_primary(vault_dir, workspace_id, device.device_id)
        set_active_profile(workspace_id, home=home)
        return _make_result(
            OnboardingFlow.UPGRADE_EXISTING,
            workspace_id=workspace_id,
            work_root=vault_dir.parent,
            vault_dir=vault_dir,
            device_id=device.device_id,
            display_name=display,
            backup_dir=backup_root,
        )
    except BaseException as exc:
        # 回滚：删除本次写入的 marker（若非本次创建则不动），并清理 profile/registry
        try:
            if marker_file.is_file():
                marker_file.unlink()
            marker_dir = marker_file.parent
            if marker_dir.is_dir():
                try:
                    marker_dir.rmdir()
                except OSError:
                    pass
        except OSError:
            pass
        drop_profile(workspace_id, home=home)
        if isinstance(exc, OnboardingError):
            raise
        raise OnboardingError(
            f"工作区升级失败，已回滚本次写入：{type(exc).__name__}: {exc}",
            reasons=[str(exc)],
        ) from exc


def connect_workspace(
    vault_dir: Path,
    *,
    display_name: str | None = None,
    device_name: str | None = None,
    home: Path | None = None,
    app_version: str | None = None,
) -> OnboardingResult:
    """connect-local：连接已 clone/拷贝的带 marker vault → 建档并设为 active。"""
    report = preflight(
        OnboardingFlow.CONNECT_LOCAL,
        vault_dir,
        home=home,
        app_version=app_version,
    )
    if not report.ok:
        raise OnboardingError("连接被拒绝", reasons=report.rejections)

    manifest = load_workspace_manifest(vault_dir)
    assert manifest is not None  # preflight 已保证 marker 存在且可读
    workspace_id = manifest.workspace_id
    display = display_name or manifest.display_name

    try:
        device = ensure_device_identity(home, device_name=device_name)
        _ensure_profile(workspace_id, display, vault_dir.parent, vault_dir, home)
        set_active_profile(workspace_id, home=home)
        return _make_result(
            OnboardingFlow.CONNECT_LOCAL,
            workspace_id=workspace_id,
            work_root=vault_dir.parent,
            vault_dir=vault_dir,
            device_id=device.device_id,
            display_name=display,
        )
    except BaseException as exc:
        drop_profile(workspace_id, home=home)
        if isinstance(exc, OnboardingError):
            raise
        raise OnboardingError(
            f"连接工作区失败，已回滚本机档案：{type(exc).__name__}: {exc}",
            reasons=[str(exc)],
        ) from exc
