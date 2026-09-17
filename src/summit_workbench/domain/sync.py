"""多设备同步状态机（P0-10 领域层，纯模型无 IO）。

状态（计划 §P0-10）：

    unconfigured          本机/仓库尚未配置远端
    ready                 与远端一致
    syncing               正在同步（瞬时）
    offline-local-ahead   离线且本地有未推送提交（允许本地写，联网后推送清零）
    remote-ahead          远端领先（等待快进）
    local-ahead           本地领先（等待推送）
    diverged-protected    双方分叉：禁止会修改共享 vault 的操作，不 force、不丢文件
    dirty-protected       工作树脏且无法安全快进（不自动 stash）
    auth-required         凭据/认证失败（与离线明确区分）
    error                 其它不可解释失败

规则（P0-10）：
- 写路径绝不使用 force/rebase/stash/reset；
- offline 允许本地写，pending 计数与最后同步时间持久化；
- diverged/dirty 默认阻止会修改共享 vault 的写操作，读/问答/浏览照常。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from summit_workbench.repositories.git_backend import (
    GitAuthError,
    GitConflictError,
    GitCredentialsUnavailable,
    GitNonFastForward,
    GitProxyError,
    GitRemoteSchemeUnsupported,
    GitRemoteUnavailable,
    GitTlsError,
)

_SCHEMA_VERSION = 1

# 远端不可用错误里表示「离线」的关键词（区别于仓库不存在/权限等）
_OFFLINE_MARKERS = (
    "offline",
    "连接超时",
    "timed out",
    "connection refused",
    "network is unreachable",
    "getaddrinfo failed",
    "超时",
    "unreachable",
)


class SyncState(StrEnum):
    """workspace 同步状态（与计划状态表一致）。"""

    UNCONFIGURED = "unconfigured"
    READY = "ready"
    SYNCING = "syncing"
    OFFLINE_LOCAL_AHEAD = "offline-local-ahead"
    REMOTE_AHEAD = "remote-ahead"
    LOCAL_AHEAD = "local-ahead"
    DIVERGED_PROTECTED = "diverged-protected"
    DIRTY_PROTECTED = "dirty-protected"
    AUTH_REQUIRED = "auth-required"
    REMOTE_SCHEME_UNSUPPORTED = "remote-scheme-unsupported"
    ERROR = "error"


class RemoteCheckStatus(StrEnum):
    """本机最近一次明确核对远端的结果。"""

    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAILED = "failed"


class AutomationOutcome(StrEnum):
    """automation（定时 writer）入口的角色门结果。"""

    PRIMARY_OK = "primary-ok"
    NOT_PRIMARY = "not-primary"
    NO_WORKSPACE = "no-workspace"


class SyncSnapshot(BaseModel):
    """本机对某 workspace 的持久化同步状态（不同步；仅 ACTIVE profile 落盘）。"""

    model_config = {"extra": "ignore"}

    schema_version: int = _SCHEMA_VERSION
    workspace_id: str
    state: SyncState = SyncState.UNCONFIGURED
    last_sync_at: str | None = None
    remote_checked_at: str | None = None
    remote_check_status: RemoteCheckStatus = RemoteCheckStatus.UNKNOWN
    pending_commits: int = 0  # 离线/失败未推送的本地 wb 提交数
    ahead: int = 0
    behind: int = 0
    branch: str | None = None
    remote_host: str | None = None  # 仅 host，不含任何凭据/路径细节
    repo_states: list[str] = []
    detail: str = ""
    next_step: str = ""


def is_offline_error(error: BaseException) -> bool:
    """把远端错误区分成「离线」与其它（auth/TLS/仓库不存在…）。"""
    if isinstance(error, GitAuthError | GitTlsError):
        return False
    if isinstance(error, GitNonFastForward | GitConflictError):
        return False
    text = f"{type(error).__name__}: {error}".casefold()
    return any(marker in text for marker in _OFFLINE_MARKERS)


def classify_repo_error(error: BaseException) -> SyncState:
    """单个仓库同步失败 → workspace 级状态类别。"""
    if isinstance(error, GitAuthError | GitTlsError | GitCredentialsUnavailable):
        # 本机缺少 workspace 级凭据同样属于"必须由人修凭据"，而不是不可解释的 error
        # （2026-09-13 真机复跑：它曾落成裸 error，界面上什么也看不出来）。
        return SyncState.AUTH_REQUIRED
    if isinstance(error, GitRemoteSchemeUnsupported):
        return SyncState.REMOTE_SCHEME_UNSUPPORTED
    if is_offline_error(error):
        return SyncState.OFFLINE_LOCAL_AHEAD
    if isinstance(error, GitNonFastForward):
        return SyncState.DIVERGED_PROTECTED
    if isinstance(error, GitRemoteUnavailable):
        return SyncState.ERROR
    return SyncState.ERROR


_REPO_REASON_LABELS: dict[str, str] = {
    "no-remote": "未配置远端",
    "no-upstream": "未设置 upstream",
    "worktree-dirty": "工作树有未提交改动",
    "credentials-missing": "本机缺少该工作区的 Git 凭据",
    "auth-rejected": "远端拒绝认证（凭据无效或权限不足）",
    "proxy-unreachable": "本机代理无法连接远端",
    "tls-failed": "远端 TLS/证书校验失败",
    "remote-unavailable": "远端不可达或仓库不存在",
    "remote-scheme-unsupported": "远端地址不是受支持的 HTTPS 或 SSH",
    "non-fast-forward": "远端已有新提交，需要处理分叉",
    "conflict": "合并冲突",
    "offline": "当前处于离线",
    "diverged": "双方分叉，已进入保护态",
    "lock-busy": "另一个同步正在进行",
    "unclassified": "未分类的同步失败",
}


def repo_error_reason(error: BaseException) -> str:
    """把一个仓库的同步失败压成**稳定原因码**。

    原因码只由异常**类型**决定，绝不携带异常文本——dulwich/Keychain 的消息里可能出现
    URL、主机名或路径。原因码进 ``snapshot.detail``，用于排障与支持。
    """
    if isinstance(error, GitCredentialsUnavailable):
        return "credentials-missing"
    if isinstance(error, GitProxyError):
        return "proxy-unreachable"
    if isinstance(error, GitTlsError):
        return "tls-failed"
    if isinstance(error, GitAuthError):
        return "auth-rejected"
    if isinstance(error, GitRemoteSchemeUnsupported):
        return "remote-scheme-unsupported"
    if isinstance(error, GitNonFastForward):
        return "non-fast-forward"
    if isinstance(error, GitConflictError):
        return "conflict"
    if isinstance(error, GitRemoteUnavailable):
        return "offline" if is_offline_error(error) else "remote-unavailable"
    return "unclassified"


def repo_reason_label(code: str) -> str:
    """原因码 → 人类可读短句（未知码回落到通用文案）。"""
    return _REPO_REASON_LABELS.get(code, _REPO_REASON_LABELS["unclassified"])


def repo_reason_detail(code: str) -> str:
    """组合成 "短句（稳定码）"，让界面与支持都能用。"""
    return f"{repo_reason_label(code)}（{code}）"


def describe_repo_reasons(entries: list[tuple[str, str]]) -> str:
    """把 [(仓库名, 原因码)] 压成一行 detail；全部正常时返回空串。"""
    parts = [f"{name}：{repo_reason_detail(code)}" for name, code in entries if code]
    return "；".join(parts)


def combine_repo_states(states: list[SyncState]) -> SyncState:
    """把各仓库状态合并成 workspace 状态（优先级：auth > diverged > dirty > offline > …）。"""
    if not states:
        return SyncState.UNCONFIGURED
    priorities = {
        SyncState.REMOTE_SCHEME_UNSUPPORTED: 10,
        SyncState.AUTH_REQUIRED: 9,
        SyncState.DIVERGED_PROTECTED: 8,
        SyncState.DIRTY_PROTECTED: 7,
        SyncState.OFFLINE_LOCAL_AHEAD: 6,
        SyncState.ERROR: 5,
        SyncState.LOCAL_AHEAD: 4,
        SyncState.REMOTE_AHEAD: 3,
        SyncState.SYNCING: 2,
        SyncState.READY: 1,
        SyncState.UNCONFIGURED: 0,
    }
    return max(states, key=lambda state: priorities.get(state, 0))


def state_from_counts(*, pending: int, ahead: int, behind: int, reachable: bool) -> SyncState:
    """未执行同步时的即时状态（用于 status 展示；reachable=False 视为离线）。"""
    if not reachable:
        return SyncState.OFFLINE_LOCAL_AHEAD if pending or ahead else SyncState.ERROR
    if behind > 0:
        return SyncState.DIVERGED_PROTECTED if ahead > 0 else SyncState.REMOTE_AHEAD
    if ahead > 0 or pending > 0:
        return SyncState.LOCAL_AHEAD
    return SyncState.READY


def next_step_for(state: SyncState, *, online: bool) -> str:
    """给用户/UI 的下一步建议（不含凭据/路径）。"""
    guidance = {
        SyncState.UNCONFIGURED: "为该 workspace 配置 Git 远端（onboarding 后设置）",
        SyncState.READY: "无需操作",
        SyncState.SYNCING: "正在同步…",
        SyncState.OFFLINE_LOCAL_AHEAD: "联网后执行一次同步即可推送本地提交",
        SyncState.REMOTE_AHEAD: "执行同步做快进合并",
        SyncState.LOCAL_AHEAD: "执行同步推送本地提交",
        SyncState.DIVERGED_PROTECTED: "已分叉：不自动覆盖任一侧，请人工核对后处理",
        SyncState.DIRTY_PROTECTED: "工作树有未提交改动：先本地提交或确认后再同步",
        SyncState.AUTH_REQUIRED: "需要重新配置 Git 凭据（workspace 作用域 Keychain）",
        SyncState.REMOTE_SCHEME_UNSUPPORTED: (
            "生产同步支持 HTTPS 或 SSH；请在设置中心配置受支持的 remote"
        ),
        SyncState.ERROR: "同步失败，请查看错误详情",
    }
    if not online and state in {
        SyncState.READY,
        SyncState.REMOTE_AHEAD,
        SyncState.LOCAL_AHEAD,
    }:
        return "当前离线：可继续本地工作，联网后再同步"
    return guidance.get(state, "请查看错误详情")
