"""P0-10 同步协调器矩阵测试（本地 bare remote + 双 clone 模拟 Studio/Air）。

覆盖：A push B ff、双端离线写 → diverged 两侧不 force 不丢文件、offline pending
重启保留 + 联网 push 清零、auth 与 offline 区分、secondary automation 拒绝记
not-primary（交互允许）、并发三连 sync 只一次实际 push、mutation guard。
全程临时仓库/临时 HOME，绝不触碰真实远端或 ~/Documents/Work。
"""

from __future__ import annotations

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
    )
    save_sync_state(snapshot, home=home)
    assert sync_state_path("workspace-sync", home=home).is_file()
    loaded = load_sync_state("workspace-sync", home=home)
    assert loaded is not None
    assert loaded.state is SyncState.OFFLINE_LOCAL_AHEAD
    assert loaded.pending_commits == 3


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
