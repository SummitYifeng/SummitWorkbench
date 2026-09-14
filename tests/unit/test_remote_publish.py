"""G2：已有本地工作台首次发布到新远端（绑定 origin + 首次推送）。

刻意用替身而不是真 HTTPS：本套件只验证工作流的顺序与失败回滚语义，
真实私有远端的推送属真机门。凭据相关函数全部替换，绝不碰开发者本机 Keychain。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.git_backend import GitError
from summit_workbench.repositories.profile_registry import load_profile, save_profile
from summit_workbench.workflows import remote_publish as workflow

PAT_TEXT = "pat-never-on-disk-1234"
PAT = SecretStr(PAT_TEXT)
HTTPS = "https://github.com/owner/repo.git"


class FakeBackend:
    """临时克隆里的"候选" backend：只记录动作，不联网。"""

    def __init__(self, *, push_error: Exception | None = None) -> None:
        self.added: list[tuple[str, str]] = []
        self.pushes = 0
        self.push_error = push_error

    def transport_kwargs(self, url: str, *, operation: str) -> dict[str, object]:
        return {}

    def clone(self, url: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)

    def add_remote(self, name: str, url: str) -> None:
        self.added.append((name, url))

    def push(self, remote: str = "origin") -> None:
        self.pushes += 1
        if self.push_error is not None:
            raise self.push_error


class FakeRepo:
    """真实 vault 的 GitRepo 门面替身。"""

    def __init__(
        self,
        path: Path,
        *,
        remote: str | None = None,
        dirty: bool = False,
        head_error: bool = False,
        push_error: Exception | None = None,
        backend: FakeBackend | None = None,
    ) -> None:
        self.path = path
        self.remote = remote
        self.dirty = dirty
        self.head_error = head_error
        self.push_error = push_error
        self.added: list[tuple[str, str]] = []
        self.removed: list[str] = []
        self.upstream: list[tuple[str, str | None]] = []
        self.pushes = 0
        self.backend = backend if backend is not None else FakeBackend()

    def is_git_repo(self) -> bool:
        return True

    def remote_url(self, name: str = "origin") -> str | None:
        return self.remote

    def is_dirty(self) -> bool:
        return self.dirty

    def current_branch(self) -> str:
        return "main"

    def head_revision(self) -> str:
        if self.head_error:
            raise GitError("HEAD 没有指向任何提交")
        return "a" * 40

    def add_remote(self, name: str, url: str) -> None:
        self.added.append((name, url))
        self.remote = url

    def remove_remote(self, name: str = "origin") -> None:
        self.removed.append(name)
        self.remote = None

    def set_upstream(self, remote: str = "origin", branch: str | None = None) -> None:
        self.upstream.append((remote, branch))

    def push(self, remote: str = "origin") -> None:
        self.pushes += 1
        if self.push_error is not None:
            raise self.push_error


class KeychainSpy:
    """记录凭据读写，绝不接触真实 Keychain。"""

    def __init__(self, *, existing: object | None = None) -> None:
        self.stored: list[tuple[str, str, str, str]] = []
        self.deleted: list[tuple[str, str, str]] = []
        self.existing = existing
        self.resolved: list[tuple[str, str, str]] = []

    def store(self, workspace_id: str, host: str, username: str, pat: SecretStr) -> None:
        self.stored.append((workspace_id, host, username, pat.get_secret_value()))

    def delete(self, workspace_id: str, host: str, username: str) -> None:
        self.deleted.append((workspace_id, host, username))

    def resolve(self, workspace_id: str, host: str, username: str) -> object:
        self.resolved.append((workspace_id, host, username))
        if self.existing is None:
            raise RuntimeError("no stored credential")
        return self.existing


def _profile(workspace_id: str, vault: Path) -> LocalProfile:
    return LocalProfile(
        workspace_id=workspace_id,
        display_name="Publish fixture",
        work_root=vault.parent,
        vault_dir=vault,
        device_role=DeviceRole.SECONDARY,
        created_at=datetime.now(UTC),
        git_username=None,
        git_remote_url=None,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: FakeRepo,
    candidate: FakeBackend,
    ls_remote,
) -> KeychainSpy:
    spy = KeychainSpy()
    monkeypatch.setattr(workflow, "GitRepo", lambda *args, **kwargs: repo)
    monkeypatch.setattr(workflow, "credential_scoped_backend", lambda *args, **kwargs: candidate)
    monkeypatch.setattr("dulwich.porcelain.ls_remote", ls_remote)
    monkeypatch.setattr(workflow, "store_git_credentials", spy.store)
    monkeypatch.setattr(workflow, "delete_git_credentials", spy.delete)
    monkeypatch.setattr(
        workflow, "resolve_git_credentials", lambda *args, **kwargs: spy.resolve(*args, **kwargs)
    )
    return spy


def test_publish_binds_origin_pushes_and_never_persists_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault)
    candidate = FakeBackend()
    spy = _install(monkeypatch, repo=repo, candidate=candidate, ls_remote=lambda *a, **k: {})

    result = workflow.publish_workspace_to_remote(
        vault,
        workspace_id=workspace_id,
        username="alice",
        pat=PAT,
        candidate_url=HTTPS,
        home=home,
    )

    assert result.remote_url == HTTPS
    assert result.branch == "main"
    # 预检真的推过一次（证明可推送），真 vault 只绑定并推一次
    assert candidate.added == [("origin", HTTPS)]
    assert candidate.pushes == 1
    assert repo.added == [("origin", HTTPS)]
    assert repo.pushes == 1
    assert repo.upstream == [("origin", "main")]
    assert repo.removed == []
    stored = load_profile(workspace_id, home=home)
    assert stored is not None
    assert stored.git_username == "alice"
    assert stored.git_remote_url == HTTPS
    assert spy.stored == [(workspace_id, "github.com", "alice", PAT_TEXT)]
    # PAT 绝不落盘
    for path in home.rglob("*"):
        if path.is_file():
            assert PAT_TEXT not in path.read_text(encoding="utf-8", errors="replace")


def test_publish_rejects_non_empty_remote_before_touching_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault)
    candidate = FakeBackend()
    spy = _install(
        monkeypatch,
        repo=repo,
        candidate=candidate,
        ls_remote=lambda *a, **k: {b"refs/heads/main": b"0" * 40},
    )

    with pytest.raises(workflow.RemotePublishError) as exc_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )

    assert exc_info.value.code == "remote_not_empty"
    assert repo.added == [] and repo.pushes == 0
    assert candidate.added == [] and candidate.pushes == 0
    assert spy.stored == []


def test_publish_requires_https(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault)
    _install(monkeypatch, repo=repo, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})

    with pytest.raises(workflow.RemotePublishError) as exc_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url="git@github.com:owner/repo.git",
            home=home,
        )
    assert exc_info.value.code == "remote_scheme_unsupported"
    assert repo.added == []


def test_publish_rejects_existing_origin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault, remote="https://github.com/old/repo.git")
    _install(monkeypatch, repo=repo, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})

    with pytest.raises(workflow.RemotePublishError) as exc_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )
    assert exc_info.value.code == "remote_already_configured"
    assert repo.pushes == 0


def test_publish_rejects_dirty_tree_and_unborn_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)

    dirty = FakeRepo(vault, dirty=True)
    _install(monkeypatch, repo=dirty, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})
    with pytest.raises(workflow.RemotePublishError) as dirty_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )
    assert dirty_info.value.code == "dirty_tree"

    unborn = FakeRepo(vault, head_error=True)
    _install(monkeypatch, repo=unborn, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})
    with pytest.raises(workflow.RemotePublishError) as head_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )
    assert head_info.value.code == "vault_has_no_commits"


def test_publish_rolls_back_origin_profile_and_credential_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault, push_error=GitError("远端拒绝"))
    spy = _install(monkeypatch, repo=repo, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})

    with pytest.raises(workflow.RemotePublishError) as exc_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )

    assert exc_info.value.code == "remote_publish_rolled_back"
    assert repo.removed == ["origin"]
    assert repo.remote is None
    assert repo.upstream == []
    restored = load_profile(workspace_id, home=home)
    assert restored is not None
    assert restored.git_username is None
    assert restored.git_remote_url is None
    assert spy.stored == []
    assert spy.deleted == []


# ---- BUG-1：全新 workspace 的首次发布（2026-09-14 实测）----


def test_fresh_workspace_publish_pushes_the_real_vault_with_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """回归 BUG-1：真 vault 的那次 push 必须**带本次凭据**。

    旧实现只在预检的临时克隆里注入了凭据；真 vault 的 ``repo.push()`` 走的是
    「只有 workspace_id、没有 username」的后端，dulwich 直接抛 ``GitCredentialsUnavailable``，
    被兜底 except 吞成 ``remote_publish_rolled_back``——于是**全新 workspace 的首次发布必然失败**，
    而远端已经被预检推上了 ``main``（半成品状态）。

    判据：``credential_scoped_backend`` 必须被**以真 vault 路径**调用过——这一点在旧实现下
    永远不成立（旧实现只在预检时用临时克隆路径调它）。

    变异验证：把 ``_push_with_credentials`` 换回直接 ``repo.push()``，本用例必须变红。
    """
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    repo = FakeRepo(vault)
    candidate = FakeBackend()
    scoped_paths: list[Path] = []

    def scoped(path: Path, *args: object, **kwargs: object) -> FakeBackend:
        scoped_paths.append(Path(path))
        return candidate

    _install(monkeypatch, repo=repo, candidate=candidate, ls_remote=lambda *a, **k: {})
    monkeypatch.setattr(workflow, "credential_scoped_backend", scoped)

    workflow.publish_workspace_to_remote(
        vault,
        workspace_id=workspace_id,
        username="alice",
        pat=PAT,
        candidate_url=HTTPS,
        home=home,
    )

    assert vault in scoped_paths, (
        "真 vault 的 push 没有走带凭据的后端——全新 workspace 的首次发布会失败"
    )
    assert repo.pushes >= 1, "真 vault 必须真的推过一次"


def test_publish_failure_surfaces_the_underlying_cause_and_scrubs_the_pat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """首次发布失败时必须说清**真正的原因**，而且不得把 PAT 带进错误文案。

    旧实现只回一句「首次发布失败，已恢复到没有远端的状态」——BUG-1 的真因
    （``GitCredentialsUnavailable``）因此完全不可见，只能靠读代码猜。
    """
    workspace_id = str(uuid4())
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    save_profile(_profile(workspace_id, vault), home=home)
    secret = PAT.get_secret_value()
    repo = FakeRepo(vault, push_error=GitError(f"认证失败（token={secret}）"))
    _install(monkeypatch, repo=repo, candidate=FakeBackend(), ls_remote=lambda *a, **k: {})

    with pytest.raises(workflow.RemotePublishError) as exc_info:
        workflow.publish_workspace_to_remote(
            vault,
            workspace_id=workspace_id,
            username="alice",
            pat=PAT,
            candidate_url=HTTPS,
            home=home,
        )

    message = str(exc_info.value)
    assert "GitError" in message, f"没有暴露底层异常类型：{message}"
    assert "认证失败" in message, f"没有暴露底层原因：{message}"
    assert secret not in message, "PAT 被写进了错误文案"
    assert repo.removed == ["origin"], "失败后必须回滚掉 origin"
