"""P1-02 工作区 schema 迁移的安全边界与回滚契约。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from summit_workbench import __version__
from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    GitBackend,
    GitRemoteUnavailable,
)
from summit_workbench.repositories.workspace_manifest import (
    manifest_path,
    write_workspace_manifest,
)
from summit_workbench.workflows.workspace_migration import (
    MigrationRegistry,
    MigrationResult,
    MigrationStep,
    WorkspaceMigrationError,
    default_migration_registry,
    migrate_workspace,
)


class FakeGitBackend:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.dirty = False
        self.remote = True
        self.upstream = True
        self.counts = AheadBehind(ahead=0, behind=0)
        self.fetch_error: BaseException | None = None
        self.push_error: BaseException | None = None
        self.commits: list[str] = []
        self.push_count = 0
        self._staged = False

    def is_git_repo(self) -> bool:
        return True

    def init(self, *, bare: bool = False) -> None:
        raise NotImplementedError

    def clone(self, url: str, destination: Path) -> None:
        raise NotImplementedError

    def has_remote(self, name: str = "origin") -> bool:
        return self.remote

    def remote_url(self, name: str = "origin") -> str | None:
        return "https://example.invalid/private.git" if self.remote else None

    def add_remote(self, name: str, url: str) -> None:
        raise NotImplementedError

    def current_branch(self) -> str:
        return "main"

    def head_revision(self) -> str:
        return "head-sha"

    def has_upstream(self) -> bool:
        return self.upstream

    def is_dirty(self) -> bool:
        return self.dirty

    def is_dirty_paths(self, rel_paths: list[str]) -> bool:
        return self.dirty

    def staged_paths(self) -> list[str]:
        return [".summit-workbench/workspace.json"] if self._staged else []

    def has_staged_changes(self, paths: list[str] | None = None) -> bool:
        return self._staged

    def add(self, paths: list[str]) -> None:
        self._staged = True

    def commit(self, message: str, *, author: CommitIdentity | None = None) -> None:
        self.commits.append(message)
        self._staged = False

    def fetch(self, remote: str = "origin") -> None:
        if self.fetch_error is not None:
            raise self.fetch_error

    def ahead_behind(self) -> AheadBehind:
        return self.counts

    def pending_wb_commits(self) -> int:
        return 0

    def ff_merge_upstream(self) -> None:
        raise NotImplementedError

    def push(self, remote: str = "origin") -> None:
        if self.push_error is not None:
            raise self.push_error
        self.push_count += 1

    def resolve_commit(self, sha: str) -> str:
        raise NotImplementedError

    def commit_subject(self, sha: str) -> str:
        raise NotImplementedError

    def commit_parent_count(self, sha: str) -> int:
        raise NotImplementedError

    def validate_commit(self, sha: str) -> tuple[str, int]:
        raise NotImplementedError

    def files_changed_by(self, sha: str) -> list[str]:
        raise NotImplementedError

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        raise NotImplementedError

    def show_patch(self, sha: str) -> str:
        raise NotImplementedError

    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]:
        raise NotImplementedError

    def revert(self, sha: str) -> None:
        self.commits.append(f"revert:{sha}")


def _repo(vault: Path, backend: FakeGitBackend) -> GitRepo:
    return GitRepo(vault, backend=cast(GitBackend, backend))


def _manifest(*, schema_version: int = 1) -> WorkspaceManifest:
    return WorkspaceManifest.model_validate(
        {
            "schema_version": schema_version,
            "workspace_id": str(uuid4()),
            "display_name": "Migration fixture",
            "created_at": "2026-09-05T00:00:00Z",
            "min_reader_version": "0.4.1",
            "min_writer_version": "0.4.1",
        }
    )


def _setup(tmp_path: Path) -> tuple[Path, Path, WorkspaceManifest, FakeGitBackend]:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir(parents=True)
    manifest = _manifest()
    write_workspace_manifest(vault, manifest)
    backend = FakeGitBackend(vault)
    return home, vault, manifest, backend


def test_default_migration_registry_has_explicit_v1_to_v2_step() -> None:
    registry = default_migration_registry()
    step = registry.next_step(1)

    assert step is not None
    assert (step.from_version, step.to_version) == (1, 2)
    assert registry.next_step(2) is None


def test_migration_requires_explicit_confirmation_of_current_device(tmp_path: Path) -> None:
    home, vault, manifest, backend = _setup(tmp_path)
    before = manifest_path(vault).read_bytes()

    with pytest.raises(WorkspaceMigrationError, match="迁移设备确认"):
        migrate_workspace(
            vault,
            home=home,
            device_id="device-current",
            confirmed_device_id="device-other",
            repo=_repo(vault, backend),
        )

    assert manifest_path(vault).read_bytes() == before
    assert json.loads(before)["workspace_id"] == manifest.workspace_id
    assert backend.commits == []
    assert backend.push_count == 0


def test_migration_requires_ready_clean_and_reachable_workspace(tmp_path: Path) -> None:
    for mutation in ("dirty", "remote", "diverged"):
        home, vault, _manifest_before, backend = _setup(tmp_path / mutation)
        if mutation == "dirty":
            backend.dirty = True
        elif mutation == "remote":
            backend.fetch_error = GitRemoteUnavailable("offline")
        else:
            backend.counts = AheadBehind(ahead=1, behind=1)

        before = manifest_path(vault).read_bytes()
        with pytest.raises(WorkspaceMigrationError):
            migrate_workspace(
                vault,
                home=home,
                device_id="device-current",
                confirmed_device_id="device-current",
                repo=_repo(vault, backend),
            )
        assert manifest_path(vault).read_bytes() == before
        assert backend.commits == []
        assert backend.push_count == 0


def test_migration_creates_checksum_backup_commits_and_pushes(tmp_path: Path) -> None:
    home, vault, manifest, backend = _setup(tmp_path)

    result = migrate_workspace(
        vault,
        home=home,
        device_id="device-current",
        confirmed_device_id="device-current",
        repo=_repo(vault, backend),
    )

    upgraded = json.loads(manifest_path(vault).read_text(encoding="utf-8"))
    assert result.from_version == 1
    assert result.to_version == 2
    assert upgraded["schema_version"] == 2
    assert "workspace-v1-to-v2" in upgraded["migration_history"]
    # 迁移会把写门提升到**执行迁移的那个 App 版本**（workspace_migration.py 的
    # `current["min_writer_version"] = version`，version 缺省取 `__version__`）。
    # 这里按真源断言，避免每次发版都要手改这个字面量。
    assert upgraded["min_writer_version"] == __version__
    assert backend.commits == ["wb: migrate workspace v1 -> v2"]
    assert backend.push_count == 1

    backup_manifest_path = result.backup_manifest
    backup_snapshot_path = result.backup_snapshot
    assert backup_manifest_path is not None
    assert backup_snapshot_path is not None
    backup_manifest = json.loads(backup_manifest_path.read_text(encoding="utf-8"))
    assert backup_manifest["workspace_id"] == manifest.workspace_id
    assert backup_manifest["from_version"] == 1
    assert backup_manifest["to_version"] == 2
    assert backup_manifest["git_head"] == "head-sha"
    assert backup_manifest["files"][0]["path"] == ".summit-workbench/workspace.json"
    assert backup_manifest["files"][0]["sha256"]
    assert backup_snapshot_path.is_file()


def test_migration_is_idempotent_when_workspace_is_already_current(tmp_path: Path) -> None:
    home, vault, _manifest_before, backend = _setup(tmp_path)
    first = migrate_workspace(
        vault,
        home=home,
        device_id="device-current",
        confirmed_device_id="device-current",
        repo=_repo(vault, backend),
    )
    before = manifest_path(vault).read_bytes()

    second = migrate_workspace(
        vault,
        home=home,
        device_id="device-current",
        confirmed_device_id="device-current",
        repo=_repo(vault, backend),
    )

    assert second.status == "already-current"
    assert second.backup_manifest == first.backup_manifest
    assert manifest_path(vault).read_bytes() == before
    assert backend.commits == ["wb: migrate workspace v1 -> v2"]
    assert backend.push_count == 1


def test_failed_migration_restores_backup_and_leaves_failure_report(tmp_path: Path) -> None:
    home, vault, _manifest_before, backend = _setup(tmp_path)
    before = manifest_path(vault).read_bytes()
    registry = MigrationRegistry(
        [
            MigrationStep(
                from_version=1,
                to_version=2,
                migration_id="failing-v1-to-v2",
                apply=lambda raw: {**raw, "schema_version": 2},
                after_write=lambda _raw: (_ for _ in ()).throw(RuntimeError("fixture failure")),
            )
        ]
    )

    with pytest.raises(WorkspaceMigrationError, match="已回滚") as caught:
        migrate_workspace(
            vault,
            home=home,
            device_id="device-current",
            confirmed_device_id="device-current",
            repo=_repo(vault, backend),
            registry=registry,
        )

    error = caught.value
    assert error.failure_report is not None
    assert error.failure_report.is_file()
    assert manifest_path(vault).read_bytes() == before
    assert backend.commits == []
    assert backend.push_count == 0
    report = json.loads(error.failure_report.read_text(encoding="utf-8"))
    assert report["restored"] is True
    assert report["error_type"] == "RuntimeError"


def test_push_failure_restores_marker_without_destructive_reset(tmp_path: Path) -> None:
    home, vault, _manifest_before, backend = _setup(tmp_path)
    backend.push_error = GitRemoteUnavailable("push timeout")
    before = manifest_path(vault).read_bytes()

    with pytest.raises(WorkspaceMigrationError, match="已回滚") as caught:
        migrate_workspace(
            vault,
            home=home,
            device_id="device-current",
            confirmed_device_id="device-current",
            repo=_repo(vault, backend),
        )

    assert manifest_path(vault).read_bytes() == before
    assert "revert:head-sha" in backend.commits
    failure_report = caught.value.failure_report
    assert failure_report is not None
    report = json.loads(failure_report.read_text(encoding="utf-8"))
    assert report["restored"] is True


def test_unknown_future_schema_is_rejected_without_writing(tmp_path: Path) -> None:
    home, vault, _manifest_before, backend = _setup(tmp_path)
    future = _manifest(schema_version=99)
    write_workspace_manifest(vault, future)
    before = manifest_path(vault).read_bytes()

    with pytest.raises(WorkspaceMigrationError, match="高于当前支持版本"):
        migrate_workspace(
            vault,
            home=home,
            device_id="device-current",
            confirmed_device_id="device-current",
            repo=_repo(vault, backend),
        )

    assert manifest_path(vault).read_bytes() == before
    assert backend.commits == []


def test_legacy_git_workspace_migration_endpoint_is_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧 schema 的只读保护不能把唯一的迁移入口一起挡住。"""
    from fastapi.testclient import TestClient

    from summit_workbench.config.profiles import resolve_active_workspace
    from summit_workbench.domain.workspace import LocalProfile
    from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
    from summit_workbench.webapp.app import WebContext, create_app

    home, vault, manifest, _backend = _setup(tmp_path)
    profile = LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": manifest.workspace_id,
            "display_name": manifest.display_name,
            "work_root": str(vault.parent),
            "vault_dir": str(vault),
            "created_at": "2026-09-05T00:00:00Z",
        }
    )
    save_profile(profile, home=home)
    set_active_profile(profile.workspace_id, home=home)
    context = resolve_active_workspace(home=home, app_version="0.4.1")
    assert context.device_id is not None
    web_context = WebContext.from_active_workspace(context)
    assert web_context is not None

    from summit_workbench.workflows import workspace_migration

    monkeypatch.setattr(
        workspace_migration,
        "migrate_workspace",
        lambda *_args, **_kwargs: MigrationResult(
            status="migrated",
            workspace_id=manifest.workspace_id,
            from_version=1,
            to_version=2,
            backup_dir=home / "backup",
            backup_manifest=home / "backup" / "manifest.json",
            backup_snapshot=home / "backup" / "snapshot",
        ),
    )
    response = TestClient(create_app(web_context, static_dir=tmp_path / "missing")).post(
        "/api/workspace/migration",
        json={"confirmed_device_id": context.device_id},
    )

    assert response.status_code == 404
