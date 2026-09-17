"""P1-07D read-only preflight report tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.profile_registry import save_profile
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.workflows import acceptance_preflight as module


class FakeRepo:
    def __init__(self, path: Path, remote: str, dirty: bool = False) -> None:
        self.path = path
        self.remote = remote
        self.dirty = dirty

    def remote_url(self, name: str = "origin") -> str | None:
        return self.remote

    def is_dirty(self) -> bool:
        return self.dirty

    def fetch(self, remote: str = "origin") -> None:
        return None

    def ahead_behind(self):
        from summit_workbench.repositories.git_backend import AheadBehind

        return AheadBehind(ahead=0, behind=0)

    def current_branch(self) -> str:
        return "main"

    def has_upstream(self) -> bool:
        return True


def _setup(tmp_path: Path, *, remote: str, dirty: bool = False) -> tuple[Path, Path, str]:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    workspace_id = str(uuid4())
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            schema_version=1,
            workspace_id=workspace_id,
            display_name="Preflight fixture",
            created_at=datetime.now(UTC),
            min_reader_version="0.4.1",
            min_writer_version="0.4.1",
        ),
    )
    save_profile(
        LocalProfile(
            workspace_id=workspace_id,
            display_name="Preflight fixture",
            work_root=tmp_path,
            vault_dir=vault,
            device_role=DeviceRole.SECONDARY,
            created_at=datetime.now(UTC),
            git_username="alice",
            git_remote_url=remote,
        ),
        home=home,
    )
    return home, vault, workspace_id


def test_preflight_is_green_for_https_clean_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home, vault, workspace_id = _setup(tmp_path, remote="https://github.com/owner/repo.git")
    fake = FakeRepo(vault, "https://github.com/owner/repo.git")
    seen_kwargs: list[dict[str, object]] = []

    def repo_factory(*args: object, **kwargs: object) -> FakeRepo:
        seen_kwargs.append(kwargs)
        return fake

    monkeypatch.setattr(module, "GitRepo", repo_factory)
    monkeypatch.setattr(module, "resolve_git_credentials", lambda *args: SecretStr("secret"))

    report = module.acceptance_preflight(
        vault,
        home=home,
        workspace_id=workspace_id,
        app_version="0.4.2",
        backend_kind="dulwich",
    )

    assert report.ok
    assert "secret" not in report.text
    assert "[PASS] remote-scheme" in report.text
    assert "[PASS] dirty-consistency" in report.text
    assert "[PASS] schema-path" in report.text
    assert any(item.get("username") == "alice" for item in seen_kwargs)


def test_preflight_explicitly_reports_unsupported_remote_and_dirty_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home, vault, workspace_id = _setup(tmp_path, remote="http://github.com/owner/repo.git")
    production = FakeRepo(vault, "http://github.com/owner/repo.git", dirty=False)
    system = FakeRepo(vault, "http://github.com/owner/repo.git", dirty=True)
    monkeypatch.setattr(
        module,
        "GitRepo",
        lambda _path, backend_kind=None, **kwargs: (
            system if backend_kind == "system" else production
        ),
    )

    report = module.acceptance_preflight(
        vault,
        home=home,
        workspace_id=workspace_id,
        app_version="0.4.2",
        backend_kind="dulwich",
    )

    assert not report.ok
    assert "remote_scheme_unsupported" in report.text
    assert "[FAIL] dirty-consistency: system=True; dulwich=False" in report.text
    assert "[BLOCKED] fetch: remote_scheme_unsupported" in report.text


def test_preflight_app_build_reports_full_build_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home, vault, workspace_id = _setup(tmp_path, remote="https://github.com/owner/repo.git")
    fake = FakeRepo(vault, "https://github.com/owner/repo.git")
    monkeypatch.setattr(module, "GitRepo", lambda *args, **kwargs: fake)
    monkeypatch.setattr(module, "resolve_git_credentials", lambda *args: SecretStr("secret"))

    report = module.acceptance_preflight(
        vault,
        home=home,
        workspace_id=workspace_id,
        app_version="0.4.3",
        backend_kind="dulwich",
        build_number="18",
        frontend_build="v2026.09.07-9a0fa15",
        git_revision="9a0fa15",
    )

    assert "version=0.4.3" in report.text
    assert "build=18" in report.text
    assert "frontend_build=v2026.09.07-9a0fa15" in report.text
    assert "git_revision=9a0fa15" in report.text


def test_preflight_fetch_failure_reports_redacted_error_classification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from summit_workbench.repositories.git_backend import GitAuthError

    home, vault, workspace_id = _setup(tmp_path, remote="https://github.com/owner/repo.git")

    class FailingFetchRepo(FakeRepo):
        def fetch(self, remote: str = "origin") -> None:
            raise GitAuthError("fetch origin 失败")

    fake = FailingFetchRepo(vault, "https://github.com/owner/repo.git")
    seen_kwargs: list[dict[str, object]] = []

    def repo_factory(*args: object, **kwargs: object) -> FailingFetchRepo:
        seen_kwargs.append(kwargs)
        return fake

    monkeypatch.setattr(module, "GitRepo", repo_factory)
    monkeypatch.setattr(module, "resolve_git_credentials", lambda *args: SecretStr("secret"))

    report = module.acceptance_preflight(
        vault,
        home=home,
        workspace_id=workspace_id,
        app_version="0.4.3",
        backend_kind="dulwich",
        build_number="18",
    )

    assert not report.ok
    assert "error_code=git_auth_failed" in report.text
    assert "backend=dulwich" in report.text
    assert "operation=fetch" in report.text
    assert "host=github.com" in report.text
    assert "credential_found=true" in report.text
    # 稳定脱敏：不出现 PAT、完整本机路径或 credential URL 的 path 部分
    assert "secret" not in report.text
    assert "owner/repo" not in report.text
    assert str(vault) not in report.text
