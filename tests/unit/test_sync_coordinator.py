"""P0-10 同步协调器矩阵测试（本地 bare remote + 双 clone 模拟 Studio/Air）。

覆盖：A push B ff、双端离线写 → diverged 两侧不 force 不丢文件、offline pending
重启保留 + 联网 push 清零、auth 与 offline 区分、secondary automation 拒绝记
not-primary（交互允许）、并发三连 sync 只一次实际 push、mutation guard。
全程临时仓库/临时 HOME，绝不触碰真实远端或 ~/Documents/Work。
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from summit_workbench.domain.sync import (
    AutomationOutcome,
    SyncState,
    classify_repo_error,
    combine_repo_states,
    is_offline_error,
    state_from_counts,
)
from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import (
    CommitIdentity,
    GitAuthError,
    GitRemoteSchemeUnsupported,
)
from summit_workbench.repositories.local_sync_state import (
    load_sync_state,
    save_sync_state,
    sync_state_path,
)
from summit_workbench.repositories.workspace_manifest import (
    load_workspace_manifest,
    write_workspace_manifest,
)
from summit_workbench.workflows.sync_coordinator import (
    automation_gate,
    current_snapshot,
    mutation_guard,
    push_after_commit,
    sync_workspace,
)

ID = CommitIdentity("Sync 作者", "sync@example.com")


def _write_file(repo_root: Path, rel: str, content: str) -> None:
    target = repo_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(repo: GitRepo, path: Path, rel: str, content: str, message: str) -> None:
    _write_file(path, rel, content)
    repo.add([rel])
    repo.commit(message, author=ID)


def _clone_worktree(remote: Path, name: str) -> tuple[Path, GitRepo]:
    root = remote.parent / name
    cmd = ["git", "clone", "--quiet", str(remote), str(root)]
    import subprocess

    subprocess.run(cmd, capture_output=True, check=True)
    return root, GitRepo(root)


def _ensure_marker(vault: Path) -> None:
    from uuid import uuid4

    if load_workspace_manifest(vault) is None:
        write_workspace_manifest(
            vault,
            __import__(
                "summit_workbench.domain.workspace", fromlist=["WorkspaceManifest"]
            ).WorkspaceManifest.model_validate(
                {
                    "schema_version": 1,
                    "workspace_id": str(uuid4()),
                    "display_name": "sync-vault",
                    "created_at": "2026-09-05T00:00:00Z",
                    "min_reader_version": "0.4.1",
                    "min_writer_version": "0.4.1",
                }
            ),
        )


# ---- 领域纯函数 ----


def test_offline_and_auth_classification() -> None:
    offline = GitError(
        "连接超时 fetch 失败", stderr="Could not resolve host: fatal: unable to access"
    )
    assert is_offline_error(offline) is True
    assert classify_repo_error(offline) is SyncState.OFFLINE_LOCAL_AHEAD
    auth = GitAuthError("认证失败", stderr="Authentication failed")
    assert classify_repo_error(auth) is SyncState.AUTH_REQUIRED
    assert classify_repo_error(GitRemoteSchemeUnsupported("remote_scheme_unsupported")) is (
        SyncState.REMOTE_SCHEME_UNSUPPORTED
    )
    assert state_from_counts(pending=1, ahead=0, behind=0, reachable=False) is (
        SyncState.OFFLINE_LOCAL_AHEAD
    )
    assert (
        combine_repo_states([SyncState.READY, SyncState.AUTH_REQUIRED]) is SyncState.AUTH_REQUIRED
    )
    assert combine_repo_states([SyncState.READY, SyncState.DIVERGED_PROTECTED]) is (
        SyncState.DIVERGED_PROTECTED
    )


def test_sync_state_persists_and_roundtrips(tmp_path) -> None:
    from summit_workbench.domain.sync import SyncSnapshot

    home = tmp_path / "home"
    snapshot = SyncSnapshot(
        workspace_id="workspace-sync",
        state=SyncState.OFFLINE_LOCAL_AHEAD,
        pending_commits=3,
        remote_checked_at="2026-09-16T00:00:00+00:00",
        remote_check_status="success",
    )
    save_sync_state(snapshot, home=home)
    assert sync_state_path("workspace-sync", home=home).is_file()
    loaded = load_sync_state("workspace-sync", home=home)
    assert loaded is not None
    assert loaded.state is SyncState.OFFLINE_LOCAL_AHEAD
    assert loaded.pending_commits == 3
    assert loaded.remote_checked_at == "2026-09-16T00:00:00+00:00"
    assert loaded.remote_check_status == "success"


def test_current_snapshot_does_not_fabricate_remote_check_or_fetch(tmp_path, monkeypatch) -> None:
    _remote, (a_root, _a), _ = _two_device_fixture(tmp_path)
    home = tmp_path / "home"
    sync_workspace(a_root, home=home)
    saved = load_sync_state(load_workspace_manifest(a_root).workspace_id, home=home)
    assert saved is not None and saved.remote_checked_at is not None
    before = saved.remote_checked_at

    def offline_fetch(self, remote: str = "origin") -> None:
        raise GitError("连接超时 fetch 失败")

    monkeypatch.setattr(GitRepo, "fetch", offline_fetch)
    failed_state, _outcomes, _failed_snapshot = sync_workspace(a_root, home=home)
    failed_saved = load_sync_state(saved.workspace_id, home=home)
    assert failed_state is SyncState.OFFLINE_LOCAL_AHEAD
    assert failed_saved is not None
    assert failed_saved.remote_check_status == "failed"
    assert failed_saved.remote_checked_at == before

    calls = {"fetch": 0}

    def forbidden_fetch(self, remote: str = "origin") -> None:
        calls["fetch"] += 1
        raise AssertionError("current_snapshot must not fetch")

    monkeypatch.setattr(GitRepo, "fetch", forbidden_fetch)
    snapshot = current_snapshot(a_root, home=home)

    assert calls["fetch"] == 0
    assert snapshot.remote_checked_at == before
    assert snapshot.remote_check_status == "failed"
    assert snapshot.last_sync_at == saved.last_sync_at


def test_mutation_guard_and_role_gate() -> None:
    from summit_workbench.domain.sync import SyncSnapshot

    snapshot = SyncSnapshot(workspace_id="w", state=SyncState.DIVERGED_PROTECTED, pending_commits=0)
    ok, reason = mutation_guard(snapshot)
    assert ok is False and "阻止" in reason
    assert mutation_guard(None)[0] is True
    primary = LocalProfile.model_validate(
        {
            "workspace_id": "workspace-111111",
            "display_name": "Studio",
            "work_root": str(tmp_path := Path("/tmp/x")),
            "vault_dir": str(tmp_path / "_vault"),
            "device_role": DeviceRole.AUTOMATION_PRIMARY.value,
            "created_at": "2026-09-05T00:00:00Z",
        }
    )
    secondary = primary.model_copy(update={"device_role": DeviceRole.SECONDARY})
    assert automation_gate(primary) is AutomationOutcome.PRIMARY_OK
    assert automation_gate(secondary) is AutomationOutcome.NOT_PRIMARY
    assert automation_gate(None) is AutomationOutcome.PRIMARY_OK  # env-compat 放行


# ---- 双机场景（本地 bare remote） ----


def _two_device_fixture(tmp_path: Path):
    """返回 (bare, A 工作树/GitRepo, B 工作树/GitRepo)。

    用 SystemGitBackend 直接搭台（init/bare/clone/push），协调器走 GitRepo 门面。
    """
    from summit_workbench.repositories.system_git import SystemGitBackend as S

    remote = tmp_path / "shared.git"
    S(remote).init(bare=True)
    a_root = tmp_path / "d-a" / "repo"  # 每台设备各自独立 work root，避免协调器互扫
    S(a_root).init()
    _write_file(a_root, "seed.md", "seed")
    _ensure_marker(a_root)
    backend_a = S(a_root)
    backend_a.add(["seed.md", ".summit-workbench/workspace.json"])
    backend_a.commit("wb: seed", author=ID)
    backend_a.add_remote("origin", str(remote))
    backend_a.push()
    import subprocess

    subprocess.run(
        ["git", "-C", str(a_root), "push", "--quiet", "-u", "origin", "HEAD"],
        capture_output=True,
        check=True,
    )
    b_root = tmp_path / "d-b" / "repo"
    S(b_root).clone(str(remote), b_root)
    return remote, (a_root, GitRepo(a_root)), (b_root, GitRepo(b_root))


def test_a_pushes_then_b_fast_forwards(tmp_path) -> None:
    remote, (a_root, a), (b_root, b) = _two_device_fixture(tmp_path)
    _commit(a, a_root, "f.txt", "a1", "wb: a-one")
    state_a, _, _ = sync_workspace(a_root)
    assert state_a is SyncState.READY
    state_b, _, _ = sync_workspace(b_root)
    assert state_b is SyncState.READY
    assert (b_root / "f.txt").read_text(encoding="utf-8") == "a1"
    # 同 workspace_id：marker 一致
    manifest_a = load_workspace_manifest(a_root)
    manifest_b = load_workspace_manifest(b_root)
    assert manifest_a is not None and manifest_b is not None
    assert manifest_a.workspace_id == manifest_b.workspace_id


def test_both_offline_writes_then_diverged_no_force_no_loss(tmp_path) -> None:
    remote, (a_root, a), (b_root, b) = _two_device_fixture(tmp_path)
    _commit(a, a_root, "shared.md", "base", "wb: base")
    sync_workspace(a_root)
    from summit_workbench.repositories.system_git import SystemGitBackend as S

    b_root_2 = tmp_path / "d-b2" / "repo"
    S(b_root_2).clone(str(remote), b_root_2)
    b2 = GitRepo(b_root_2)
    # A、B 各自离线提交同一文件
    _commit(a, a_root, "shared.md", "from-A", "wb: a-write")
    _commit(b2, b_root_2, "shared.md", "from-B", "wb: b-write")
    state_a, _, _ = sync_workspace(a_root)  # A 先上线推送
    assert state_a is SyncState.READY
    state_b, _, _ = sync_workspace(b_root_2)  # B 快进 → 分叉被拒（non-ff）
    assert state_b is SyncState.DIVERGED_PROTECTED
    assert (b_root_2 / "shared.md").read_text(encoding="utf-8") == "from-B"  # 本地提交未丢
    assert (a_root / "shared.md").read_text(encoding="utf-8") == "from-A"  # A 未覆盖
    # 无 force：状态机可解释
    assert state_b in {SyncState.DIVERGED_PROTECTED}


def test_offline_pending_survives_restart_then_online_push_clears(tmp_path, monkeypatch) -> None:
    remote, (a_root, a), _ = _two_device_fixture(tmp_path)
    _commit(a, a_root, "f.txt", "x", "wb: x")
    sync_workspace(a_root)

    real_push = GitRepo.push

    def offline_push(self) -> None:
        raise GitError("离线：unable to access ... Connection refused", stderr="offline")

    monkeypatch.setattr(GitRepo, "push", offline_push)
    state, snap = push_after_commit(a_root, home=tmp_path / "home")
    assert state is SyncState.OFFLINE_LOCAL_AHEAD
    assert snap is not None and snap.pending_commits == 1
    # 「重启」= 重新从磁盘读状态
    loaded = load_sync_state(snap.workspace_id, home=tmp_path / "home")
    assert loaded is not None and loaded.pending_commits == 1

    monkeypatch.setattr(GitRepo, "push", real_push)
    state2, snap2 = push_after_commit(a_root, home=tmp_path / "home")
    assert state2 is SyncState.READY
    assert snap2 is not None and snap2.pending_commits == 0


def test_three_concurrent_syncs_run_one_actual_push(tmp_path, monkeypatch) -> None:
    remote, (a_root, a), _ = _two_device_fixture(tmp_path)
    _commit(a, a_root, "f.txt", "p1", "wb: p1")
    sync_workspace(a_root)
    _commit(a, a_root, "f.txt", "p2", "wb: p2")  # 待推送

    count = {"n": 0}
    real_push = GitRepo.push

    def counting_push(self) -> None:
        count["n"] += 1
        real_push(self)

    monkeypatch.setattr(GitRepo, "push", counting_push)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            sync_workspace(a_root)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors
    assert count["n"] == 1, f"三次并发同步应只产生一次实际 push，实际 {count['n']}"


def test_auth_required_distinct_from_offline(tmp_path, monkeypatch) -> None:
    remote, (a_root, a), _ = _two_device_fixture(tmp_path)
    _commit(a, a_root, "f.txt", "x", "wb: x")
    sync_workspace(a_root)
    _commit(a, a_root, "f.txt", "y", "wb: y")

    def auth_push(self) -> None:
        raise GitAuthError("认证失败", stderr="Authentication failed")

    monkeypatch.setattr(GitRepo, "push", auth_push)
    state, _ = push_after_commit(a_root)
    assert state is SyncState.AUTH_REQUIRED


def test_discover_skips_remote_clone_staging(tmp_path) -> None:
    """P1-07D：onboarding 的 remote clone staging 目录不作为 workspace 子仓库同步。"""
    from summit_workbench.workflows.sync_coordinator import _discover

    work = tmp_path / "work"
    work.mkdir()
    vault = work / "_vault"
    vault.mkdir()
    (vault / ".git").mkdir()
    staging = work / ".summit-workbench-remote-bd5fjceu"
    staging.mkdir()
    (staging / ".git").mkdir()

    discovered = _discover(work)
    assert vault in discovered
    assert staging not in discovered


# ---- D3（2026-09-13 双机复跑）：失败原因必须可见、稳定、脱敏 ----------------


def test_repo_error_reason_is_type_based_and_sanitized() -> None:
    """原因码只由异常类型决定：dulwich/Keychain 的原文绝不进 detail。"""
    from summit_workbench.domain.sync import repo_error_reason, repo_reason_detail
    from summit_workbench.repositories.git_backend import (
        GitConflictError,
        GitCredentialsUnavailable,
        GitNonFastForward,
        GitProxyError,
        GitTlsError,
    )

    assert (
        repo_error_reason(GitCredentialsUnavailable("含 user:canary-secret@host/x.git"))
        == "credentials-missing"
    )
    assert repo_error_reason(GitProxyError("代理 127.0.0.1:7890 失败")) == "proxy-unreachable"
    assert repo_error_reason(GitTlsError("certificate verify failed")) == "tls-failed"
    assert repo_error_reason(GitNonFastForward("non-fast-forward")) == "non-fast-forward"
    assert repo_error_reason(GitConflictError("conflict")) == "conflict"
    assert repo_error_reason(RuntimeError("别的")) == "unclassified"
    detail = repo_reason_detail("credentials-missing")
    assert "credentials-missing" in detail and "canary-secret" not in detail


def test_classify_repo_error_treats_missing_credentials_as_auth_required() -> None:
    from summit_workbench.repositories.git_backend import GitCredentialsUnavailable

    assert (
        classify_repo_error(GitCredentialsUnavailable("HTTPS remote 缺少凭据"))
        is SyncState.AUTH_REQUIRED
    )


def test_sync_workspace_snapshot_detail_names_the_failure(monkeypatch, tmp_path) -> None:
    """拉取路径此前完全不带 detail —— 用户只能看到裸 error（D3 的真机症状）。"""
    from summit_workbench.repositories.git_backend import GitCredentialsUnavailable
    from summit_workbench.workflows import sync_coordinator

    vault = tmp_path / "_vault"
    vault.mkdir()
    subprocess.run(["git", "init", "--quiet", str(vault)], check=True)
    subprocess.run(
        ["git", "-C", str(vault), "remote", "add", "origin", "https://github.com/acme/private.git"],
        check=True,
    )

    canary = "user:canary-secret@github.com/acme/private.git"

    def boom(self, remote: str = "origin") -> None:
        raise GitCredentialsUnavailable(f"HTTPS remote 缺少 workspace-scoped 凭据 {canary}")

    monkeypatch.setattr(GitRepo, "fetch", boom)
    monkeypatch.setattr(sync_coordinator, "require_https_remote", lambda url: None)

    state, outcomes, snapshot = sync_coordinator.sync_workspace(vault, workspace_id="ws-1")
    assert state is SyncState.AUTH_REQUIRED
    assert outcomes == [("_vault", SyncState.AUTH_REQUIRED)]
    assert snapshot is not None
    assert "credentials-missing" in snapshot.detail
    assert "canary-secret" not in snapshot.detail


def test_push_after_commit_detail_is_sanitized(monkeypatch, tmp_path) -> None:
    """写路径原先把 str(exc) 直接写进持久化状态与界面，会带出 URL/路径。"""
    from summit_workbench.workflows import sync_coordinator

    vault = tmp_path / "_vault"
    vault.mkdir()
    subprocess.run(["git", "init", "--quiet", str(vault)], check=True)
    subprocess.run(
        ["git", "-C", str(vault), "remote", "add", "origin", "https://github.com/acme/private.git"],
        check=True,
    )

    canary = "embedded user:canary-secret@github.com/acme/private.git"

    def boom(self, remote: str = "origin") -> None:
        raise GitError(f"push {remote} 失败：{canary}")

    monkeypatch.setattr(GitRepo, "has_remote", lambda self, name="origin": True)
    monkeypatch.setattr(GitRepo, "has_upstream", lambda self: True)
    monkeypatch.setattr(GitRepo, "push", boom)

    state, snapshot = sync_coordinator.push_after_commit(vault, workspace_id="ws-1")
    assert state is SyncState.ERROR
    assert snapshot is not None
    assert "unclassified" in snapshot.detail
    assert "canary-secret" not in snapshot.detail


def test_sync_uses_the_on_disk_git_username_not_the_startup_snapshot(monkeypatch, tmp_path) -> None:
    """D2：git_username 由「确认并转换」写入磁盘 profile，而 context 在启动时冻结。

    真机症状：转换成功后同一进程内点「立即重试」必然失败（凭据查找用了空用户名），
    重启 App 才恢复。
    """
    from uuid import uuid4

    from summit_workbench.config.profiles import resolve_active_workspace
    from summit_workbench.domain.workspace import LocalProfile, WorkspaceManifest
    from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
    from summit_workbench.workflows import sync_coordinator

    home = tmp_path / "home"
    vault = tmp_path / "work" / "_vault"
    vault.mkdir(parents=True)
    workspace_id = str(uuid4())
    write_workspace_manifest(
        vault,
        WorkspaceManifest.model_validate(
            {
                "schema_version": 2,
                "workspace_id": workspace_id,
                "display_name": "d2",
                "created_at": "2026-09-05T00:00:00Z",
                "min_reader_version": "0.1.0",
                "min_writer_version": "0.1.0",
            }
        ),
    )
    profile = LocalProfile.model_validate(
        {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "display_name": "d2",
            "work_root": str(vault.parent),
            "vault_dir": str(vault),
            "device_role": DeviceRole.SECONDARY.value,
            "created_at": "2026-09-05T00:00:00Z",
        }
    )
    save_profile(profile, home=home)
    set_active_profile(workspace_id, home=home)

    context = resolve_active_workspace(home=home)
    assert context.profile is not None
    assert context.profile.git_username is None, "启动时 profile 还没有 git_username"

    # 模拟「确认并转换」：只改磁盘上的 profile（本进程的 context 不会更新）。
    save_profile(profile.model_copy(update={"git_username": "alice"}), home=home)

    seen: dict[str, object] = {}

    def fake_single(path, *, backend_kind=None, workspace_id=None, username=None):
        seen["username"] = username
        return SyncState.READY, ""

    monkeypatch.setattr(sync_coordinator, "_sync_single_repo", fake_single)
    sync_coordinator.sync_workspace(vault, context=context)
    assert seen["username"] == "alice", "同步必须用磁盘上的当前 git_username"
