"""Web 面板的 JSON API 契约（纯函数，无 IO；供 SPA 前端消费）。

SSR 视图（views.py）与 JSON API（本模块）共用同一套领域逻辑与审批页事实源
（meetings.md / inbox.md / 状态账本），保证 Web 面板永远与 CLI 看到同一份数据。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from summit_workbench.webapp.presenters import brief_payload as brief_payload
from summit_workbench.webapp.presenters import (
    external_action_payload as external_action_payload,
)
from summit_workbench.webapp.presenters import review_entry_payload as review_entry_payload
from summit_workbench.webapp.presenters import review_payload as review_payload

# ---- 请求体模型（SPA 以 JSON 提交） ----


class DecidePayload(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    decision: Literal["pending", "approved", "rejected"]


class BatchDecidePayload(BaseModel):
    candidate_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=100
    )
    decision: Literal["pending", "approved", "rejected"]


class EditPayload(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    target_project: str | None = Field(default=None, max_length=200)
    route: (
        Literal[
            "feishu-task",
            "feishu-meeting",
            "project-main",
            "project-followup",
            "project-inbox",
            "global-inbox",
            "knowledge-note",
        ]
        | None
    ) = None  # feishu-task|feishu-meeting|project-main|project-inbox|global-inbox|knowledge-note
    due_date: str | None = Field(default=None, max_length=32)
    # 知识沉淀落点：`<vault 相对页面路径>#<区块标题>`；只有 route=knowledge-note 时使用。
    sink_target: str | None = Field(default=None, max_length=512)
    start_at: str | None = Field(default=None, max_length=64)
    end_at: str | None = Field(default=None, max_length=64)


class TaskEditPayload(BaseModel):
    """今日待办任务行内编辑：只改标题与/或截止日期（空 due_date = 清除截止）。"""

    task_id: str = Field(min_length=1, max_length=2048)
    summary: str | None = Field(default=None, max_length=200)
    due_date: str | None = Field(default=None, max_length=32)


class MeetingEditPayload(BaseModel):
    """今日会议行内编辑：只改标题与/或起止时间（本地 naive YYYY-MM-DDTHH:MM）。"""

    event_id: str = Field(min_length=1, max_length=2048)
    summary: str | None = Field(default=None, max_length=200)
    start_at: str | None = Field(default=None, max_length=64)
    end_at: str | None = Field(default=None, max_length=64)


class CapturePayload(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


class TaskCompletePayload(BaseModel):
    """把一条飞书任务标记为已完成（``task_id`` 即简报 ``task_list`` 里的飞书任务 guid）。"""

    task_id: str = Field(min_length=1, max_length=2048)


class ProjectPayload(BaseModel):
    """工作台精选（ADR 0023）：按文件夹名加入/归档项目。"""

    name: str = Field(min_length=1, max_length=200)


class ProjectCreatePayload(BaseModel):
    """新建知识线程项目（无 Work 文件夹的 vault 档案）。"""

    project_id: str = Field(min_length=1, max_length=200)
    aliases: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=100
    )


class ProjectRenamePayload(BaseModel):
    """设置项目/线程的显示名（frontmatter ``title``；不影响规范 ID、别名与文件夹）。"""

    name: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)


class LogAppendPayload(BaseModel):
    """追加一条推进日志：可关联 1..n 个线程/项目；AI 摘要是加分项，模型不可用只存原文。"""

    projects: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=100
    )
    text: str = Field(min_length=1, max_length=100_000)


class ArtifactSavePayload(BaseModel):
    """把一段 AI 产物（阶段总结/PRD/背景包等）存入某个线程档案。"""

    project: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)
    title: str | None = Field(default=None, max_length=200)


class ProjectStatePayload(BaseModel):
    """把主档案「当前状态」区块替换为一段文本（产物摘要 → 状态草案）。"""

    project: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)


class JournalLogPayload(BaseModel):
    """写一条「日常手记」（契约 §4.10 的五区块形态）：四段**至少填一段**，关联项目可选。

    四段按使用者的话术采集，落盘换成标准区块名（`did`→`## 今天 / 本周做了什么`、
    `remaining`→`## 下一步`、`reflection`→`## 进展与变化`、`blockers`→`## 卡点与需要谁`）；
    空段不生成区块。「至少填一段」由路由给出点名提示（不用 422 挡）。
    """

    did: str = Field(default="", max_length=200_000)
    remaining: str = Field(default="", max_length=200_000)
    reflection: str = Field(default="", max_length=200_000)
    blockers: str = Field(default="", max_length=200_000)
    projects: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=100
    )


class JournalThoughtPayload(BaseModel):
    """写一篇工作思考：三段正文都必填（`long-form-thought` 的三个固定区块）。

    三段**不用** pydantic 的 `min_length` 卡：缺段要由路由回点名的提示
    （「缺少必填段落：## 思考展开」），而不是笼统的 422。
    """

    problem: str = Field(default="", max_length=200_000)
    thinking: str = Field(default="", max_length=200_000)
    conclusion: str = Field(default="", max_length=200_000)
    projects: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=100
    )
    summary: str | None = Field(default=None, max_length=2_000)
    title: str | None = Field(default=None, max_length=200)
    workstream: str | None = Field(default=None, max_length=32)


class UndoRevertPayload(BaseModel):
    """撤销一次系统自动提交（``wb:`` 前缀的 vault 提交）。"""

    sha: str = Field(max_length=40)


class ExternalActionReconcilePayload(BaseModel):
    """外部创建结果核对：recheck | succeeded | not-found | retry。"""

    decision: Literal["recheck", "succeeded", "not-found", "retry"]
    remote_id: str | None = Field(default=None, max_length=2048)
    confirm_retry: bool = False


class ProfileSwitchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=8, max_length=64)


class ProfileSwitchCommitPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=8, max_length=100)


class ProfileRemovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=8, max_length=64)
    confirmed: bool = False


class GitRemoteNormalizationPayload(BaseModel):
    """Candidate HTTPS origin and one-time PAT (never persisted by the API)."""

    model_config = ConfigDict(extra="forbid")

    candidate_url: str = Field(min_length=1, max_length=2_048)
    git_username: str = Field(min_length=1, max_length=200)
    pat: str = Field(min_length=1, max_length=100_000)


class GitRemoteNormalizationPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=8, max_length=100)
    git_username: str = Field(min_length=1, max_length=200)
    pat: str = Field(min_length=1, max_length=100_000)


class GitRemoteRollbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class SyncConflictSelectionPayload(BaseModel):
    """Current revision snapshot plus explicit manual conflict choices; validation only."""

    model_config = ConfigDict(extra="forbid")

    base_revision: str = Field(min_length=40, max_length=64)
    local_revision: str = Field(min_length=40, max_length=64)
    remote_revision: str = Field(min_length=40, max_length=64)
    selections: dict[
        str,
        Literal["keep-local", "keep-remote", "preserve-both"],
    ] = Field(default_factory=dict, max_length=1000)


class SyncConflictRecoveryPayload(BaseModel):
    """Revision-bound recovery request; confirmation is explicit and local-only."""

    model_config = ConfigDict(extra="forbid")

    base_revision: str = Field(min_length=40, max_length=64)
    local_revision: str = Field(min_length=40, max_length=64)
    remote_revision: str = Field(min_length=40, max_length=64)
    selections: dict[
        str,
        Literal["keep-local", "keep-remote", "preserve-both"],
    ] = Field(default_factory=dict, max_length=1000)
    confirmed: bool = False


class AcceptancePreflightPayload(BaseModel):
    """Read-only release/dual-device acceptance gate request."""

    model_config = ConfigDict(extra="forbid")


class ProviderSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["model", "feishu", "git"]
    settings: dict[str, object] = Field(default_factory=dict)
    secret: str | None = Field(default=None, max_length=100_000)


class ProviderVerifyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["model"] = "model"
    secret: str | None = Field(default=None, max_length=100_000)


class FeishuCompletePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=4_096)
    state: str | None = Field(default=None, min_length=8, max_length=256)


class OnboardingConnectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=8, max_length=64)


class OnboardingModelVerifyPayload(OnboardingConnectionPayload):
    secret: str | None = Field(default=None, max_length=100_000)


class OnboardingModelSavePayload(OnboardingModelVerifyPayload):
    model_id: str = Field(default="deepseek-flash", min_length=1, max_length=200)
    base_url: str = Field(default="https://api.deepseek.com/v1", min_length=1, max_length=2_048)


class DoctorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    online: bool = False


class WorkspaceMigrationPayload(BaseModel):
    """显式确认当前设备执行 workspace schema 迁移。"""

    model_config = ConfigDict(extra="forbid")

    confirmed_device_id: str = Field(min_length=8, max_length=200)


class AutomationSettingsPayload(BaseModel):
    """更新 workspace 本机自动化的一项调度设置。"""

    model_config = ConfigDict(extra="forbid")

    job: Literal["brief", "weekly", "meeting-sync"]
    enabled: bool = False
    hour: Annotated[int, Field(ge=0, le=23)]
    minute: Annotated[int, Field(ge=0, le=59)]
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(max_length=7)


class AutomationRunPayload(BaseModel):
    """手动运行一项自动化任务。"""

    model_config = ConfigDict(extra="forbid")

    job: Literal["brief", "weekly", "meeting-sync"]


# ---- onboarding 服务 API（P0-08，无 UI；服务在 workflows/onboarding.py） ----


class OnboardingPreflightPayload(BaseModel):
    flow: Literal["create-new", "upgrade-existing", "connect-local", "connect-remote"]
    path: str = Field(min_length=1, max_length=2_048)


class OnboardingCreatePayload(BaseModel):
    work_root: str = Field(min_length=1, max_length=2_048)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_role: Literal["automation-primary", "secondary"] = "automation-primary"


class OnboardingVaultPayload(BaseModel):
    """upgrade-existing / connect-local 的目标 vault。"""

    vault_dir: str = Field(min_length=1, max_length=2_048)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_role: Literal["automation-primary", "secondary"] = "automation-primary"


class OnboardingDraftPayload(BaseModel):
    """安装级向导草稿；明确拒绝 api key/token 等秘密字段。"""

    model_config = ConfigDict(extra="forbid")

    flow: Literal["create-new", "connect-existing", "upgrade-existing", "model", "feishu"] = (
        "create-new"
    )
    step: str = Field(default="welcome", min_length=1, max_length=64)
    work_root: str | None = Field(default=None, max_length=2_048)
    vault_dir: str | None = Field(default=None, max_length=2_048)
    display_name: str | None = Field(default=None, max_length=200)
    device_name: str | None = Field(default=None, max_length=200)
    git_mode: Literal["local", "remote", "skipped"] | None = None
    remote_url: str | None = Field(default=None, max_length=2_048)
    expected_workspace_id: str | None = Field(default=None, max_length=200)
    git_username: str | None = Field(default=None, max_length=200)
    model_provider: str | None = Field(default=None, max_length=100)
    model_id: str | None = Field(default=None, max_length=200)
    model_base_url: str | None = Field(default=None, max_length=2_048)
    model_credential_account: str | None = Field(default=None, max_length=200)
    feishu_app_id: str | None = Field(default=None, max_length=200)
    feishu_redirect_uri: str | None = Field(default=None, max_length=2_048)
    provider_status: Literal["pending", "skipped", "ready"] = "pending"
    automation_role: Literal["primary", "secondary"] = "secondary"


class OnboardingRemoteStagePayload(BaseModel):
    remote_url: str = Field(min_length=1, max_length=2_048)
    target_vault: str = Field(min_length=1, max_length=2_048)
    expected_workspace_id: str | None = Field(default=None, max_length=200)
    git_username: str = Field(min_length=1, max_length=200)
    pat: str | None = Field(default=None, max_length=100_000)


class OnboardingRemoteConfirmPayload(BaseModel):
    stage_id: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    user_email: str | None = Field(default=None, max_length=320)
    pat: str | None = Field(default=None, max_length=100_000)


class AutomationPrimaryPayload(BaseModel):
    """显式声明/接管 workspace 的 automation-primary。"""

    device_id: str = Field(min_length=1, max_length=200)
    expected_generation: int | None = Field(default=None, ge=1)
    takeover: bool = False
