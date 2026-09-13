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
from typing import TYPE_CHECKING

from summit_workbench.config.locking import LockBusy, workspace_lock
from summit_workbench.domain.sync import (
    AutomationOutcome,
    SyncSnapshot,
    SyncState,
    classify_repo_error,
    combine_repo_states,
    describe_repo_reasons,
    is_offline_error,
    next_step_for,
    repo_error_reason,
    repo_reason_detail,
    state_from_counts,
)
from summit_workbench.domain.workspace import DeviceRole, LocalProfile
from summit_workbench.observability.server_log import log_sync_outcome
from summit_workbench.repositories.automation_primary import AutomationPrimaryClaim
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.git_backend import (
    GitAuthError,
    GitNonFastForward,
    GitRemoteSchemeUnsupported,
    require_https_remote,
)
from summit_workbench.repositories.local_sync_state import save_sync_state
from summit_workbench.workflows.external_actions import workspace_id_for_vault

if TYPE_CHECKING:
    from summit_workbench.config.profiles import ActiveWorkspaceContext


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _workspace_id_of(vault_dir: Path) -> str:
    return workspace_id_for_vault(vault_dir)


def pending_wb_commits(
    vault_dir: Path,
    *,
    backend_kind: str | None = None,
    workspace_id: str | None = None,
    username: str | None = None,
) -> int:
    """返回当前 vault 中实际尚未推送的 ``wb:`` 提交数。"""
    repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    if not repo.is_git_repo():
        return 0
    try:
        return repo.pending_wb_commits()
    except GitError:
        return 0


def _fresh_git_username(context: ActiveWorkspaceContext) -> str | None:
    """取**磁盘上当前**的 git_username。

    profile 是可变的本地状态：「确认并转换」、保存 provider 设置都会改写它；而
    ``ActiveWorkspaceContext`` 在本进程启动时冻结。同步若继续用快照里的值，同一个进程内
    刚写入的 ``git_username`` 永远看不到，凭据查找会退化成空用户名并失败
    （2026-09-13 真机：转换成功后「立即重试」必失败，重启才恢复，见 D2）。
    读不到时退回快照值——不因为一次读取失败让同步崩掉。
    """
    if context.profile is None or context.workspace_id is None:
        return None
    try:
        from summit_workbench.repositories.profile_registry import load_profile

        fresh = load_profile(context.workspace_id, home=context.home)
    except Exception:  # noqa: BLE001 - 读取失败回退快照
        fresh = None
    return (fresh or context.profile).git_username


def _snapshot(
    workspace_id: str,
    *,
    state: SyncState,
    pending: int,
    ahead: int = 0,
    behind: int = 0,
    detail: str = "",
    branch: str | None = None,
    remote_host: str | None = None,
    last_sync_at: str | None = None,
    repo_states: list[str] | None = None,
) -> SyncSnapshot:
    return SyncSnapshot(
        workspace_id=workspace_id,
        state=state,
        last_sync_at=_now() if state is SyncState.READY else last_sync_at,
        pending_commits=pending,
        ahead=ahead,
        behind=behind,
        detail=detail,
        branch=branch,
        remote_host=remote_host,
        repo_states=repo_states or [],
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


def _sync_single_repo(
    path: Path,
    *,
    backend_kind: str | None = None,
    workspace_id: str | None = None,
    username: str | None = None,
) -> tuple[SyncState, str]:
    """同步单个仓库（只 fetch/ff/push，绝不 force）。返回 (repo 状态, 稳定原因码)。

    原因码由异常**类型**决定（见 ``domain.sync.repo_error_reason``），不含任何值，
    供 ``snapshot.detail`` 展示——用户看到的必须是"为什么失败"，不是三选一的猜测。
    """
    repo = GitRepo(
        path,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    if not repo.has_remote():
        return SyncState.UNCONFIGURED, "no-remote"
    try:
        remote_url = repo.remote_url("origin")
        if not remote_url:
            return SyncState.UNCONFIGURED, "no-remote"
        # Development/CLI conformance fixtures may use local-path remotes. The
        # packaged active-workspace path passes Dulwich explicitly and is the
        # production boundary where HTTPS is mandatory.
        if backend_kind == "dulwich":
            require_https_remote(remote_url)
        repo.fetch()
    except GitRemoteSchemeUnsupported:
        return SyncState.REMOTE_SCHEME_UNSUPPORTED, "remote-scheme-unsupported"
    except GitAuthError:
        return SyncState.AUTH_REQUIRED, "auth-rejected"
    except GitError as exc:
        return classify_repo_error(exc), repo_error_reason(exc)
    dirty = repo.is_dirty()
    if dirty:
        # 不自动 stash/rebase/reset，也不把未提交的人工改动混入同步；即使当前只
        # 有 local-ahead 提交，后续 push/写入也无法证明不会覆盖用户工作树。
        return SyncState.DIRTY_PROTECTED, "worktree-dirty"
    if not repo.has_upstream():
        return SyncState.UNCONFIGURED, "no-upstream"
    try:
        counts = repo.ahead_behind()
    except GitError as exc:
        return classify_repo_error(exc), repo_error_reason(exc)
    try:
        if counts.behind > 0:
            if dirty:
                return SyncState.DIRTY_PROTECTED, "worktree-dirty"
            try:
                repo.ff_merge_upstream()
            except GitAuthError:
                return SyncState.AUTH_REQUIRED, "auth-rejected"
            except GitError as exc:
                if is_offline_error(exc):
                    return SyncState.OFFLINE_LOCAL_AHEAD, "offline"
                # 无法快进（存在分叉，需人工处理）：不 force，本地提交保留
                return SyncState.DIVERGED_PROTECTED, "diverged"
        if counts.ahead > 0:
            try:
                repo.push()
            except GitNonFastForward:
                return SyncState.DIVERGED_PROTECTED, "non-fast-forward"
            except GitAuthError:
                return SyncState.AUTH_REQUIRED, "auth-rejected"
            except GitError as exc:
                return classify_repo_error(exc), repo_error_reason(exc)
    except GitNonFastForward:
        return SyncState.DIVERGED_PROTECTED, "non-fast-forward"
    except GitError as exc:
        return classify_repo_error(exc), repo_error_reason(exc)
    return SyncState.READY, ""


_REMOTE_STAGING_PREFIX = ".summit-workbench-remote-"


def _discover(work_root: Path) -> list[Path]:
    if not work_root.is_dir():
        return []
    return sorted(
        (
            p
            for p in work_root.iterdir()
            if p.is_dir()
            and (p / ".git").exists()
            and not p.name.startswith(_REMOTE_STAGING_PREFIX)
        ),
        key=lambda p: p.name,
    )


def sync_workspace(
    vault_dir: Path,
    *,
    work_root: Path | None = None,
    home: Path | None = None,
    workspace_id: str | None = None,
    backend_kind: str | None = None,
    context: ActiveWorkspaceContext | None = None,
    username: str | None = None,
) -> tuple[SyncState, list[tuple[str, SyncState]], SyncSnapshot | None]:
    """在工作区锁内同步 workspace（vault + work_root 直接子仓库），返回合并状态。

    :param home: ACTIVE profile 的 home（非 None 时持久化 sync-state.json）。
    """
    if context is not None:
        if context.paths is None or context.profile is None or not context.can_read:
            raise ValueError("active workspace context 不允许同步")
        vault_dir = context.paths.vault_dir
        work_root = context.paths.work_root
        home = context.home
        workspace_id = context.workspace_id
        backend_kind = backend_kind or "dulwich"
        username = username or _fresh_git_username(context)
    work_root = work_root or vault_dir.parent
    repo_paths = [vault_dir] + [
        p for p in _discover(work_root) if p != vault_dir and (p / ".git").exists()
    ]
    workspace_id = workspace_id or _workspace_id_of(vault_dir)
    previous = load_sync_state_if_available(workspace_id, home)
    outcomes: list[tuple[str, SyncState]] = []
    reasons: list[tuple[str, str]] = []
    try:
        with workspace_lock(vault_dir.parent):
            for path in repo_paths:
                state, reason = _sync_single_repo(
                    path,
                    backend_kind=backend_kind,
                    workspace_id=workspace_id,
                    username=username,
                )
                outcomes.append((path.name, state))
                if state is not SyncState.READY:
                    reasons.append((path.name, reason))
    except LockBusy:
        outcomes.append(("(workspace)", SyncState.ERROR))
        reasons.append(("(workspace)", "lock-busy"))
    combined = combine_repo_states([state for _, state in outcomes])
    if combined is not SyncState.READY and combined is not SyncState.UNCONFIGURED:
        # G3：同步失败/降级落一行本机日志（只写稳定原因码与计数），
        # 否则"昨晚为什么没同步"只能看内存快照。
        log_sync_outcome(state=combined.value, reasons=reasons, home=home)
    primary_repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    pending = pending_wb_commits(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    ahead = behind = 0
    branch = remote_host = None
    try:
        branch = primary_repo.current_branch()
        remote_host = _remote_host_of(primary_repo)
        if primary_repo.has_upstream():
            counts = primary_repo.ahead_behind()
            ahead, behind = counts.ahead, counts.behind
    except GitError:
        pass
    last_sync_at: str | None
    if combined is SyncState.READY:
        pending = 0
        last_sync_at = _now()
    else:
        last_sync_at = previous.last_sync_at if previous is not None else None
    snapshot = _snapshot(
        workspace_id,
        state=combined,
        pending=pending,
        last_sync_at=last_sync_at,
        ahead=ahead,
        behind=behind,
        branch=branch,
        remote_host=remote_host,
        repo_states=[f"{name}:{state.value}" for name, state in outcomes],
        detail=describe_repo_reasons(reasons),
    )
    if home is not None:
        save_sync_state(snapshot, home=home)
    return combined, outcomes, snapshot


def push_after_commit(
    vault_dir: Path,
    *,
    home: Path | None = None,
    workspace_id: str | None = None,
    backend_kind: str | None = None,
    context: ActiveWorkspaceContext | None = None,
    username: str | None = None,
) -> tuple[SyncState, SyncSnapshot | None]:
    """wb commit 之后的中心推送（锁外、失败不回滚、失败可重试）。

    - 无 remote/upstream → unconfigured（无副作用）；
    - push 成功 → ready；非快进 → diverged-protected（本地提交保留）；
    - auth 失败 → auth-required；离线 → offline-local-ahead（记 pending）；
    - 其它失败 → error（不吞错）。
    """
    if context is not None:
        if context.paths is None or context.profile is None or not context.can_read:
            raise ValueError("active workspace context 不允许同步")
        vault_dir = context.paths.vault_dir
        home = context.home
        workspace_id = context.workspace_id
        backend_kind = backend_kind or "dulwich"
        username = username or _fresh_git_username(context)
    ws_id = workspace_id or _workspace_id_of(vault_dir)
    repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    previous = load_sync_state_if_available(ws_id, home)
    if not repo.has_remote() or not repo.has_upstream():
        state = SyncState.UNCONFIGURED
        snapshot = _snapshot(
            ws_id,
            state=state,
            pending=pending_wb_commits(
                vault_dir,
                backend_kind=backend_kind,
                workspace_id=workspace_id,
                username=username,
            ),
            last_sync_at=previous.last_sync_at if previous is not None else None,
        )
        return state, snapshot
    push_reason: str | None = None
    try:
        repo.push()
        state = SyncState.READY
        snapshot = _snapshot(ws_id, state=state, pending=0, last_sync_at=_now())
    except GitAuthError:
        push_reason = "auth-rejected"
        state = SyncState.AUTH_REQUIRED
        snapshot = _snapshot(
            ws_id,
            state=state,
            pending=max(
                1,
                pending_wb_commits(
                    vault_dir,
                    backend_kind=backend_kind,
                    workspace_id=workspace_id,
                    username=username,
                ),
            ),
            detail="凭据需要重新配置（auth-rejected）",
            last_sync_at=previous.last_sync_at if previous is not None else None,
        )
    except GitNonFastForward:
        push_reason = "non-fast-forward"
        state = SyncState.DIVERGED_PROTECTED
        snapshot = _snapshot(
            ws_id,
            state=state,
            pending=max(
                1,
                pending_wb_commits(
                    vault_dir,
                    backend_kind=backend_kind,
                    workspace_id=workspace_id,
                    username=username,
                ),
            ),
            detail="远端分叉，本地提交已保留（non-fast-forward）",
            last_sync_at=previous.last_sync_at if previous is not None else None,
        )
    except GitError as exc:
        if is_offline_error(exc):
            push_reason = "offline"
            state = SyncState.OFFLINE_LOCAL_AHEAD
            snapshot = _snapshot(
                ws_id,
                state=state,
                pending=max(
                    1,
                    pending_wb_commits(
                        vault_dir,
                        backend_kind=backend_kind,
                        workspace_id=workspace_id,
                        username=username,
                    ),
                ),
                detail="离线，本地提交已保留（offline）",
                last_sync_at=previous.last_sync_at if previous is not None else None,
            )
        else:
            push_reason = repo_error_reason(exc)
            state = SyncState.ERROR
            snapshot = _snapshot(
                ws_id,
                state=state,
                pending=max(
                    1,
                    pending_wb_commits(
                        vault_dir,
                        backend_kind=backend_kind,
                        workspace_id=workspace_id,
                        username=username,
                    ),
                ),
                # 稳定原因码 + 短句：绝不把 dulwich/Keychain 的原始文本（可能含 URL、
                # 主机名或路径）写进持久化状态与界面。
                detail=repo_reason_detail(repo_error_reason(exc)),
                last_sync_at=previous.last_sync_at if previous is not None else None,
            )
    if push_reason is not None:
        # G3：wb 提交后的中心推送失败同样落一行（push_after_commit 不经过 sync_workspace）。
        log_sync_outcome(state=state.value, reasons=[("push", push_reason)], home=home)
    if home is not None:
        save_sync_state(snapshot, home=home)
    return state, snapshot


def automation_gate(
    profile: LocalProfile | None,
    *,
    claim: AutomationPrimaryClaim | None = None,
    device_id: str | None = None,
    require_claim: bool = False,
) -> AutomationOutcome:
    """DeviceRole 门控（要求 7）：只有 automation-primary 允许定时 writer。

    env-compat（无 profile）视为允许——保持既有 launchd 开发用法，
    直到 P0-11 设置中心普遍建立 active profile 后接管。
    """
    if profile is None:
        return AutomationOutcome.PRIMARY_OK
    if require_claim and claim is None:
        return AutomationOutcome.NOT_PRIMARY
    if profile.device_role is DeviceRole.AUTOMATION_PRIMARY and (
        claim is None or claim.device_id == device_id
    ):
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
    backend_kind: str | None = None,
    context: ActiveWorkspaceContext | None = None,
    username: str | None = None,
) -> SyncSnapshot:
    """读取/内存构建当前状态快照（不落盘）。"""
    if context is not None:
        if context.paths is None or context.profile is None or not context.can_read:
            raise ValueError("active workspace context 不允许读取同步状态")
        vault_dir = context.paths.vault_dir
        home = context.home
        workspace_id = context.workspace_id
        backend_kind = backend_kind or "dulwich"
        username = username or _fresh_git_username(context)
    ws_id = workspace_id or _workspace_id_of(vault_dir)
    saved = load_sync_state_if_available(ws_id, home)
    repo = GitRepo(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    if saved is not None and saved.state in {
        SyncState.DIVERGED_PROTECTED,
        SyncState.DIRTY_PROTECTED,
        SyncState.AUTH_REQUIRED,
        SyncState.ERROR,
    }:
        pending = pending_wb_commits(
            vault_dir,
            backend_kind=backend_kind,
            workspace_id=workspace_id,
            username=username,
        )
        return saved.model_copy(update={"pending_commits": max(saved.pending_commits, pending)})
    if not repo.is_git_repo():
        return _snapshot(
            ws_id,
            state=SyncState.UNCONFIGURED,
            pending=saved.pending_commits if saved is not None else 0,
            detail="vault 尚未启用 Git",
            last_sync_at=saved.last_sync_at if saved is not None else None,
        )
    if not repo.has_remote():
        return _snapshot(
            ws_id,
            state=SyncState.UNCONFIGURED,
            pending=saved.pending_commits if saved is not None else 0,
            detail="未配置 Git 远端",
            last_sync_at=saved.last_sync_at if saved is not None else None,
        )
    try:
        reachable = True
        ahead = behind = 0
        dirty = repo.is_dirty()
        if repo.has_upstream():
            counts = repo.ahead_behind()
            ahead, behind = counts.ahead, counts.behind
    except GitError:
        reachable = False
        ahead = behind = 0
    pending = pending_wb_commits(
        vault_dir,
        backend_kind=backend_kind,
        workspace_id=workspace_id,
        username=username,
    )
    if home is not None and saved is not None and saved.pending_commits > pending:
        pending = saved.pending_commits
    if dirty:
        return _snapshot(
            ws_id,
            state=SyncState.DIRTY_PROTECTED,
            pending=pending,
            last_sync_at=saved.last_sync_at if saved is not None else None,
            ahead=ahead,
            behind=behind,
            branch=repo.current_branch() if reachable else None,
            remote_host=_remote_host_of(repo) if reachable else None,
            detail="工作树存在未提交改动，已停止同步与共享写入",
        )
    state = state_from_counts(pending=pending, ahead=ahead, behind=behind, reachable=reachable)
    return _snapshot(
        ws_id,
        state=state,
        pending=pending,
        last_sync_at=saved.last_sync_at if saved is not None else None,
        ahead=ahead,
        behind=behind,
        branch=repo.current_branch() if reachable else None,
        remote_host=_remote_host_of(repo) if reachable else None,
        repo_states=saved.repo_states if saved is not None else None,
    )


def load_sync_state_if_available(workspace_id: str, home: Path | None) -> SyncSnapshot | None:
    if home is None:
        return None
    from summit_workbench.repositories.local_sync_state import load_sync_state

    return load_sync_state(workspace_id, home=home)
