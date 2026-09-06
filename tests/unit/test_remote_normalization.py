"""P1-07D remote normalization is previewed, reversible, and secret-free."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.profile_registry import load_profile, save_profile
from summit_workbench.workflows import remote_normalization as workflow


class FakeRepo:
    def __init__(self, path: Path, remote: str = "git@github.com:owner/repo.git") -> None:
        self.path = path
        self.remote = remote
        self.set_calls: list[str] = []

    def remote_url(self, name: str = "origin") -> str | None:
        return self.remote

    def current_branch(self) -> str:
        return "main"

    def has_upstream(self) -> bool:
        return True

    def is_dirty(self) -> bool:
        return False

    def set_remote_url(self, url: str, name: str = "origin") -> None:
        self.set_calls.append(url)
        self.remote = url


def _profile(workspace_id: str, vault: Path) -> LocalProfile:
    return LocalProfile(
        workspace_id=workspace_id,
        display_name="Normalization fixture",
        work_root=vault.parent,
        vault_dir=vault,
        device_role=DeviceRole.SECONDARY,
        created_at=datetime.now(UTC),
        git_username=None,
        git_remote_url=None,
    )


def _validation(url: str) -> workflow.RemoteValidation:
    return workflow.RemoteValidation(
        remote_url=url,
        workspace_id="workspace",
        branch="main",
        ahead=0,
        behind=0,
    )


def test_preview_does_not_change_origin_or_persist_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    fake = FakeRepo(vault)
    monkeypatch.setattr(workflow, "GitRepo", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        workflow,
        "_validate_candidate",
        lambda *args, **kwargs: _validation("https://github.com/owner/repo.git"),
    )

    plan = workflow.preview_remote_normalization(
        vault,
        workspace_id=workspace_id,
        username="alice",
        pat=SecretStr("pat-never-on-disk"),
        candidate_url="https://github.com/owner/repo.git",
        home=tmp_path / "home",
    )

    assert plan.old_url == "git@github.com:owner/repo.git"
    assert fake.remote == plan.old_url
    assert fake.set_calls == []


def test_preview_rejects_a_different_repository_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    fake = FakeRepo(vault)
    monkeypatch.setattr(workflow, "GitRepo", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        workflow,
        "_validate_candidate",
        lambda *args, **kwargs: _validation("https://github.com/other/repo.git"),
    )

    with pytest.raises(workflow.RemoteNormalizationError) as exc_info:
        workflow.preview_remote_normalization(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=SecretStr("pat-never-on-disk"),
            candidate_url="https://github.com/other/repo.git",
            home=tmp_path / "home",
        )
    assert exc_info.value.code == "repository_identity_mismatch"
    assert fake.set_calls == []


def test_apply_failure_restores_origin_and_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    old_profile = _profile(workspace_id, vault)
    save_profile(old_profile, home=home)
    fake = FakeRepo(vault)
    monkeypatch.setattr(workflow, "GitRepo", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        workflow,
        "_validate_candidate",
        lambda *args, **kwargs: _validation("https://github.com/owner/repo.git"),
    )
    monkeypatch.setattr(
        workflow,
        "store_git_credentials",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("keychain unavailable")),
    )
    plan = workflow.RemoteNormalizationPlan(
        plan_id=str(uuid4()),
        workspace_id=workspace_id,
        old_url=fake.remote,
        candidate_url="https://github.com/owner/repo.git",
        branch="main",
        candidate=_validation("https://github.com/owner/repo.git"),
    )

    with pytest.raises(workflow.RemoteNormalizationError) as exc_info:
        workflow.apply_remote_normalization(
            vault,
            plan,
            username="alice",
            pat=SecretStr("pat-never-on-disk"),
            home=home,
        )

    assert exc_info.value.code == "normalization_rolled_back"
    assert fake.remote == plan.old_url
    restored = load_profile(workspace_id, home=home)
    assert restored is not None
    assert restored.git_username is None
    assert restored.git_remote_url is None
    assert not (
        home
        / "Library"
        / "Application Support"
        / "SummitWorkbench"
        / "profiles"
        / workspace_id
        / "remote-normalization.json"
    ).exists()


def test_transaction_record_never_contains_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    fake = FakeRepo(vault)
    monkeypatch.setattr(workflow, "GitRepo", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        workflow,
        "_validate_candidate",
        lambda *args, **kwargs: _validation("https://github.com/owner/repo.git"),
    )
    monkeypatch.setattr(workflow, "store_git_credentials", lambda *args, **kwargs: None)
    plan = workflow.RemoteNormalizationPlan(
        plan_id=str(uuid4()),
        workspace_id=workspace_id,
        old_url=fake.remote,
        candidate_url="https://github.com/owner/repo.git",
        branch="main",
        candidate=_validation("https://github.com/owner/repo.git"),
    )

    workflow.apply_remote_normalization(
        vault,
        plan,
        username="alice",
        pat=SecretStr("pat-never-on-disk"),
        home=home,
    )
    record = (
        home
        / "Library"
        / "Application Support"
        / "SummitWorkbench"
        / "profiles"
        / workspace_id
        / "remote-normalization.json"
    ).read_text()
    assert "pat-never-on-disk" not in record
    assert "alice" not in record
