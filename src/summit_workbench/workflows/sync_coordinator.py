"""workspace 同步协调器（P0-10 核心，服务层）。

- :func:`sync_workspace`：在工作区锁内对 workspace（vault 及 work_root 下的直接子仓库）
  执行 fetch →（clean 时）ff-merge → push；绝不 force/rebase/stash/reset；typed 错误
  归类为 auth/offline/diverged/dirty/error 并合并成 workspace 状态。
- :func:`push_after_commit`：wb commit 之后触发的中心推送能力（锁外执行、失败不回滚、
  仅回写 pending/最后同步时间）。
- :func:`automation_gate`：DeviceRole 门控（secondary → not-primary，不执行；env-compat
  视为允许，直到 P0-11 设置中心接管）。
- :func:`mutation_guard`：diverged/dirty 保护态下拒绝修改共享 vault 的写（读照常）。

持久化策略：仅调用方显式传 ``home``（ACTIVE profile 场景）时写
sync-state.json；env-compat 不落盘（不触碰真实 Application Support）。
"""

from __future__ import annotations

import datetime
from pathlib import Path

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.domain.sync import (
    AutomationOutcome,
    SyncSnapshot,
    SyncState,
    classify_repo_error,
    combine_repo_states,
    is_offline_error,
    next_step_for,
    state_from_counts,
)
from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import (
    GitAuthError,
    GitNonFastForward,
)
from summit_workbench.repositories.local_sync_state import save_sync_state
from summit_workbench.workflows.external_actions import workspace_id_for_vault


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _workspace_id_of(vault_dir: Path) -> str:
    return workspace_id_for_vault(vault_dir)


def _snapshot(
    workspace_id: str,
    *,
    state: SyncState,
    pending: int,
    detail: str = "",
    branch: str | None = None,
    remote_host: str | None = None,
) -> SyncSnapshot:
    return SyncSnapshot(
        workspace_id=workspace_id,
        state=state,
        last_sync_at=_now() if state is SyncState.READY else None,
        pending_commits=pending,
        detail=detail,
        branch=branch,
        remote_host=remote_host,
        next_step=next_step_for(state, online=True),
    )


def _remote_host_of(repo: GitRepo) -> str | None:
    """远端 host（不含路径/凭据）。"""
    try:
        url = repo.remote_url("origin")
    except GitError:
        return None
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        from summit_workbench.config.git_credentials import strip_credentials

        stripped = strip_credentials(url).split("/")[2]
        return stripped.split(":")[0] or None
    return None


def _sync_single_repo(path: Path) -> tuple[SyncState, SyncSnapshot | None]:
    """同步单个仓库（只 fetch/ff/push，绝不 force）。返回 (repo 状态, 无)。"""
    repo = GitRepo(path)
    if not repo.has_remote():
        return SyncState.UNCONFIGURED, None
    try:
        repo.fetch()
    except GitAuthError:
        return SyncState.AUTH_REQUIRED, None
    except GitError as exc:
        return classify_repo_error(exc), None
    dirty = repo.is_dirty()
    if not repo.has_upstream():
        return SyncState.UNCONFIGURED, None
    try:
        counts = repo.ahead_behind()
    except GitError as exc:
        return classify_repo_error(exc), None
    try:
        if counts.behind > 0:
            if dirty:
                return SyncState.DIRTY_PROTECTED, None
            try:
                repo.ff_merge_upstream()
            except GitAuthError:
                return SyncState.AUTH_REQUIRED, None
            except GitError as exc:
                if is_offline_error(exc):
                    return SyncState.OFFLINE_LOCAL_AHEAD, None
                # 无法快进（存在分叉，需人工处理）：不 force，本地提交保留
                return SyncState.DIVERGED_PROTECTED, None
        if counts.ahead > 0:
            try:
                repo.push()
            except GitNonFastForward:
                return SyncState.DIVERGED_PROTECTED, None
            except GitAuthError:
                return SyncState.AUTH_REQUIRED, None
            except GitError as exc:
                return classify_repo_error(exc), None
    except GitNonFastForward:
        return SyncState.DIVERGED_PROTECTED, None
    except GitError as exc:
        return classify_repo_error(exc), None
    return SyncState.READY, None


def _discover(work_root: Path) -> list[Path]:
    if not work_root.is_dir():
        return []
    return sorted(
        (p for p in work_root.iterdir() if p.is_dir() and (p / ".git").exists()),
        key=lambda p: p.name,
    )


def sync_workspace(
    vault_dir: Path,
    *,
    work_root: Path | None = None,
    home: Path | None = None,
) -> tuple[SyncState, list[tuple[str, SyncState]], SyncSnapshot | None]:
    """在工作区锁内同步 workspace（vault + work_root 直接子仓库），返回合并状态。

    :param home: ACTIVE profile 的 home（非 None 时持久化 sync-state.json）。
    """
    work_root = work_root or vault_dir.parent
    repo_paths = [vault_dir] + [
        p for p in _discover(work_root) if p != vault_dir and (p / ".git").exists()
    ]
    workspace_id = _workspace_id_of(vault_dir)
    outcomes: list[tuple[str, SyncState]] = []
    try:
        with workspace_lock(vault_dir.parent):
            for path in repo_paths:
                state, _snap = _sync_single_repo(path)
                outcomes.append((path.name, state))
    except LockBusy:
        outcomes.append(("(workspace)", SyncState.ERROR))
    combined = combine_repo_states([state for _, state in outcomes])
    snapshot = _snapshot(workspace_id, state=combined, pending=0)
    if home is not None:
        save_sync_state(snapshot, home=home)
    return combined, outcomes, snapshot


def push_after_commit(
    vault_dir: Path,
    *,
    home: Path | None = None,
    workspace_id: str | None = None,
) -> tuple[SyncState, SyncSnapshot | None]:
    """wb commit 之后的中心推送（锁外、失败不回滚、失败可重试）。

    - 无 remote/upstream → unconfigured（无副作用）；
    - push 成功 → ready；非快进 → diverged-protected（本地提交保留）；
    - auth 失败 → auth-required；离线 → offline-local-ahead（记 pending）；
    - 其它失败 → error（不吞错）。
    """
    ws_id = workspace_id or _workspace_id_of(vault_dir)
    repo = GitRepo(vault_dir)
    if not repo.has_remote() or not repo.has_upstream():
        state = SyncState.UNCONFIGURED
        snapshot = _snapshot(ws_id, state=state, pending=0)
        return state, snapshot
    try:
        repo.push()
        state = SyncState.READY
        snapshot = _snapshot(ws_id, state=state, pending=0)
    except GitAuthError:
        state = SyncState.AUTH_REQUIRED
        snapshot = _snapshot(ws_id, state=state, pending=1, detail="凭据需要重新配置")
    except GitNonFastForward:
        state = SyncState.DIVERGED_PROTECTED
        snapshot = _snapshot(ws_id, state=state, pending=0, detail="远端分叉，本地提交已保留")
    except GitError as exc:
        if is_offline_error(exc):
            state = SyncState.OFFLINE_LOCAL_AHEAD
            snapshot = _snapshot(ws_id, state=state, pending=1, detail="离线，本地提交已保留")
        else:
            state = SyncState.ERROR
            snapshot = _snapshot(ws_id, state=state, pending=1, detail=str(exc))
    if home is not None:
        save_sync_state(snapshot, home=home)
    return state, snapshot


def automation_gate(profile: LocalProfile | None) -> AutomationOutcome:
    """DeviceRole 门控（要求 7）：只有 automation-primary 允许定时 writer。

    env-compat（无 profile）视为允许——保持既有 launchd 开发用法，
    直到 P0-11 设置中心普遍建立 active profile 后接管。
    """
    if profile is None:
        return AutomationOutcome.PRIMARY_OK
    if profile.device_role is DeviceRole.AUTOMATION_PRIMARY:
        return AutomationOutcome.PRIMARY_OK
    return AutomationOutcome.NOT_PRIMARY


def mutation_guard(
    snapshot: SyncSnapshot | None,
) -> tuple[bool, str]:
    """保护态写门（要求 5）：diverged/dirty 下拒绝修改共享 vault 的交互写。"""
    if snapshot is None:
        return True, ""
    if snapshot.state in {SyncState.DIVERGED_PROTECTED, SyncState.DIRTY_PROTECTED}:
        return False, f"workspace 处于 {snapshot.state.value}，修改共享 vault 的操作已被阻止"
    return True, ""


def current_snapshot(
    vault_dir: Path,
    *,
    home: Path | None = None,
    workspace_id: str | None = None,
) -> SyncSnapshot:
    """读取/内存构建当前状态快照（不落盘）。"""
    ws_id = workspace_id or _workspace_id_of(vault_dir)
    if home is not None:
        from summit_workbench.repositories.local_sync_state import load_sync_state

        saved = load_sync_state(ws_id, home=home)
        if saved is not None:
            return saved
    repo = GitRepo(vault_dir)
    if not repo.has_remote():
        return _snapshot(ws_id, state=SyncState.UNCONFIGURED, pending=0, detail="未配置 Git 远端")
    try:
        reachable = True
        ahead = behind = 0
        if repo.has_upstream():
            counts = repo.ahead_behind()
            ahead, behind = counts.ahead, counts.behind
    except GitError:
        reachable = False
        ahead = behind = 0
    pending = 0
    if home is not None:
        from summit_workbench.repositories.local_sync_state import load_sync_state

        saved = load_sync_state(ws_id, home=home)
        if saved is not None:
            pending = saved.pending_commits
    state = state_from_counts(pending=pending, ahead=ahead, behind=behind, reachable=reachable)
    return _snapshot(ws_id, state=state, pending=pending)
