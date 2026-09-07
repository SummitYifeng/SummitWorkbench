"""P0-09C：production Git backend 与 remote clone onboarding 离线契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from summit_workbench.config.git_credentials import GitCredentials
from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import (
    CommitIdentity,
    GitCredentialsUnavailable,
)
from summit_workbench.repositories.profile_registry import load_profile
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.workflows.remote_onboarding import (
    RemoteCloneError,
    cancel_remote_clone,
    confirm_remote_clone,
    stage_remote_clone,
    validate_remote_url,
)


def _manifest(workspace_id: str, *, min_reader: str = "0.1.0") -> WorkspaceManifest:
    return WorkspaceManifest(
        schema_version=2,
        workspace_id=workspace_id,
        display_name="Remote workspace",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
        min_reader_version=min_reader,
        min_writer_version="0.1.0",
    )


class _FakeRemoteBackend:
    def __init__(self, path: Path, manifest: WorkspaceManifest | None) -> None:
        self.path = path
        self.manifest = manifest

    def clone(self, url: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "README.md").write_text("remote\n", encoding="utf-8")
        if self.manifest is not None:
            write_workspace_manifest(destination, self.manifest)


def _factory(manifest: WorkspaceManifest | None):
    def build(path: Path, **_: object) -> _FakeRemoteBackend:
        return _FakeRemoteBackend(path, manifest)

    return build


def test_production_git_backend_is_explicit_and_does_not_leak_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_GIT_BACKEND", "system")
    repo = GitRepo(tmp_path / "repo", backend_kind="dulwich")
    assert type(repo.backend).__name__ == "DulwichGitBackend"


def test_dulwich_https_transport_callback_is_workspace_scoped(monkeypatch, tmp_path) -> None:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    calls: list[tuple[str, str, str]] = []

    def resolve(workspace_id: str, host: str, username: str) -> GitCredentials:
        calls.append((workspace_id, host, username))
        return GitCredentials(workspace_id, host, username, SecretStr("canary-secret"))

    backend = DulwichGitBackend(
        tmp_path / "repo",
        workspace_id="workspace-a",
        username="alice",
        credential_resolver=resolve,
    )
    kwargs = backend.transport_kwargs("https://github.com/acme/private.git", operation="fetch")
    assert kwargs["username"] == "alice"
    assert kwargs["password"] == "canary-secret"
    # P1-07D：HTTPS transport 必须携带 TLS 校验开启、且指向可信 CA 的连接池。
    pool_manager = kwargs["pool_manager"]
    assert pool_manager.connection_pool_kw["cert_reqs"] == "CERT_REQUIRED"
    assert pool_manager.connection_pool_kw.get("ca_certs")
    assert calls == [("workspace-a", "github.com", "alice")]
    assert "canary-secret" not in repr(backend)


def test_dulwich_credential_callback_errors_are_sanitized(tmp_path) -> None:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    def broken(*_: str) -> GitCredentials:
        raise RuntimeError("Keychain failed: canary-secret")

    backend = DulwichGitBackend(
        tmp_path / "repo",
        workspace_id="workspace-a",
        username="alice",
        credential_resolver=broken,
    )
    with pytest.raises(GitCredentialsUnavailable) as exc_info:
        backend.transport_kwargs("https://github.com/acme/private.git", operation="fetch")
    assert "canary-secret" not in str(exc_info.value)


def test_remote_clone_staging_confirm_creates_secondary_profile(tmp_path) -> None:
    home = tmp_path / "home"
    target = tmp_path / "work" / "_vault"
    target.parent.mkdir()
    workspace_id = str(uuid4())
    staged = stage_remote_clone(
        "https://github.com/acme/private.git",
        target,
        workspace_id=workspace_id,
        username="alice",
        home=home,
        backend_factory=_factory(_manifest(workspace_id)),
    )
    assert staged.staging_dir.exists()
    result = confirm_remote_clone(staged, home=home, display_name="Remote", device_name="Air")
    assert result.workspace_id == workspace_id
    profile = load_profile(workspace_id, home=home)
    assert profile is not None
    assert profile.device_role.value == "secondary"
    assert target.is_dir()
    assert not staged.staging_dir.exists()


def test_remote_clone_cancel_only_removes_own_staging(tmp_path) -> None:
    target = tmp_path / "work" / "_vault"
    target.parent.mkdir()
    workspace_id = str(uuid4())
    staged = stage_remote_clone(
        "https://gitlab.com/acme/private.git",
        target,
        workspace_id=workspace_id,
        username="alice",
        home=tmp_path / "home",
        backend_factory=_factory(_manifest(workspace_id)),
    )
    marker = target.parent / "keep.txt"
    marker.write_text("user\n", encoding="utf-8")
    cancel_remote_clone(staged)
    assert not staged.staging_dir.exists()
    assert marker.read_text(encoding="utf-8") == "user\n"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://github.com/acme/repo.git", "remote_scheme_unsupported"),
        ("https://alice:" + "secret" + "@github.com/acme/repo.git", "remote_url_userinfo"),
        ("ssh://git@github.com/acme/repo.git", "remote_scheme_unsupported"),
    ],
)
def test_remote_url_validation_is_stable(url: str, code: str) -> None:
    with pytest.raises(RemoteCloneError) as exc_info:
        validate_remote_url(url)
    assert exc_info.value.code == code
    assert "secret" not in str(exc_info.value)


def test_remote_clone_missing_marker_does_not_touch_target_or_registry(tmp_path) -> None:
    home = tmp_path / "home"
    target = tmp_path / "work" / "_vault"
    target.parent.mkdir()
    with pytest.raises(RemoteCloneError) as exc_info:
        stage_remote_clone(
            "https://github.com/acme/private.git",
            target,
            workspace_id=None,
            username="alice",
            home=home,
            backend_factory=_factory(None),
        )
    assert exc_info.value.code == "remote_missing_marker"
    assert not target.exists()
    assert not (home / "Library").exists()


def test_remote_clone_rejects_schema_too_new_and_target_conflict(tmp_path) -> None:
    target = tmp_path / "work" / "_vault"
    target.parent.mkdir()
    workspace_id = str(uuid4())
    with pytest.raises(RemoteCloneError) as exc_info:
        stage_remote_clone(
            "https://github.com/acme/private.git",
            target,
            workspace_id=workspace_id,
            username="alice",
            home=tmp_path / "home",
            backend_factory=_factory(_manifest(workspace_id, min_reader="99.0.0")),
        )
    assert exc_info.value.code == "workspace_incompatible"
    assert not target.exists()

    target.mkdir(parents=True)
    with pytest.raises(RemoteCloneError) as conflict:
        stage_remote_clone(
            "https://github.com/acme/private.git",
            target,
            workspace_id=workspace_id,
            username="alice",
            home=tmp_path / "home",
            backend_factory=_factory(_manifest(workspace_id)),
        )
    assert conflict.value.code == "target_exists"


def test_path_empty_dulwich_can_init_commit_without_system_git(monkeypatch, tmp_path) -> None:
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend, ca_bundle_path

    monkeypatch.setenv("PATH", "")
    path = tmp_path / "repo"
    backend = DulwichGitBackend(path)
    backend.init()
    (path / "note.md").write_text("offline\n", encoding="utf-8")
    backend.add(["note.md"])
    backend.commit("seed", author=CommitIdentity("Test", "wb@local"))
    assert backend.is_git_repo()
    assert ca_bundle_path() is not None
