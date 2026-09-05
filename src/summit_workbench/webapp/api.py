"""Web 面板的 JSON API 契约（纯函数，无 IO；供 SPA 前端消费）。

SSR 视图（views.py）与 JSON API（本模块）共用同一套领域逻辑与审批页事实源
（meetings.md / inbox.md / 状态账本），保证 Web 面板永远与 CLI 看到同一份数据。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from summit_workbench.domain.brief import CATEGORY_LABELS
from summit_workbench.domain.external_action import ExternalAction
from summit_workbench.domain.review import ReviewEntry

_HEALTH_LABELS = {"ok": "正常", "degraded": "降级", "alert": "告警"}

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
        ]
        | None
    ) = None  # feishu-task | feishu-meeting | project-main | project-inbox | global-inbox
    due_date: str | None = Field(default=None, max_length=32)
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


class UndoRevertPayload(BaseModel):
    """撤销一次系统自动提交（``wb:`` 前缀的 vault 提交）。"""

    sha: str = Field(max_length=40)


class ExternalActionReconcilePayload(BaseModel):
    """外部创建结果核对：recheck | succeeded | not-found | retry。"""

    decision: Literal["recheck", "succeeded", "not-found", "retry"]
    remote_id: str | None = Field(default=None, max_length=2048)
    confirm_retry: bool = False


class AskHistoryTurn(BaseModel):
    """对话中的一轮历史问答（追问上下文）：只带问题原文 + 当时引用过的来源 id。

    刻意**不带** AI 当时的答案全文——AI 回答不是 vault 事实，不进入下一轮来源集合。
    """

    question: str = Field(min_length=1, max_length=2_000)
    sources: list[Annotated[str, Field(max_length=2048)]] = Field(
        default_factory=list, max_length=100
    )


class AskPayload(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[AskHistoryTurn] = Field(default_factory=list, max_length=100)
    # 可选的检索范围：限定到某个项目/线程（其档案+日志+产物+关联会议）。
    project: str | None = Field(default=None, max_length=200)


# ---- onboarding 服务 API（P0-08，无 UI；服务在 workflows/onboarding.py） ----


class OnboardingPreflightPayload(BaseModel):
    flow: Literal["create-new", "upgrade-existing", "connect-local"]
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


class OnboardingRemoteConfirmPayload(BaseModel):
    stage_id: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    user_email: str | None = Field(default=None, max_length=320)


class AutomationPrimaryPayload(BaseModel):
    """显式声明/接管 workspace 的 automation-primary。"""

    device_id: str = Field(min_length=1, max_length=200)
    expected_generation: int | None = Field(default=None, ge=1)
    takeover: bool = False


# ---- 序列化 ----


def review_entry_payload(entry: ReviewEntry) -> dict[str, object]:
    """把一条审批条目序列化为前端可直接渲染的 JSON。"""
    c = entry.candidate
    return {
        "candidate_id": c.candidate_id,
        "kind": c.kind.value,
        "description": c.description,
        "target_project": c.target_project,
        "route": c.route.value if c.route else None,
        "due_date": c.due_date,
        "start_at": c.start_at,
        "end_at": c.end_at,
        "evidence": c.evidence.anchor if c.evidence else None,
        "decision": c.decision.value,
        "historical": c.historical,
        "actionable": c.is_actionable(),
        "ai_original": entry.ai_original,
        "meeting_date": entry.meeting_date,
        "meeting_title": entry.meeting_title,
        "note_link": entry.note_link,
        "transcript_link": entry.transcript_link,
        "apply_error": entry.apply_error,
    }


def review_payload(entries: list[ReviewEntry], errors: list[str]) -> dict[str, object]:
    """审批页整体载荷：按会议分组 + 错误列表。"""
    groups: list[dict[str, object]] = []
    buckets: dict[tuple[str, str], list[dict[str, object]]] = {}
    for entry in entries:
        payload = review_entry_payload(entry)
        buckets.setdefault((entry.meeting_date, entry.meeting_title), []).append(payload)
    for (meeting_date, meeting_title), items in sorted(buckets.items()):
        groups.append(
            {
                "meeting_date": meeting_date,
                "meeting_title": meeting_title,
                "entries": items,
            }
        )
    return {"groups": groups, "errors": errors}


def external_action_payload(action: ExternalAction) -> dict[str, object]:
    """外部动作状态载荷；不向浏览器暴露请求 body 或凭据。"""
    return {
        "operation_id": action.operation_id,
        "candidate_id": action.candidate_id,
        "workspace_id": action.workspace_id,
        "kind": action.kind.value,
        "request_fingerprint": action.request_fingerprint,
        "target_account_ref": action.target_account_ref,
        "state": action.state.value,
        "attempt": action.attempt,
        "timestamp": action.timestamp,
        "remote_id": action.remote_id,
        "error": action.error,
        "retry_allowed": action.retry_allowed,
    }


# ---- 晨间简报（结构化明细，供「今日」页组件化渲染） ----

_CATEGORY_VALUE_LABELS: dict[str, str] = {c.value: CATEGORY_LABELS[c] for c in CATEGORY_LABELS}


def _action_item(raw: dict[str, object], rank: int | None = None) -> dict[str, object]:
    category_key = str(raw.get("category", ""))
    item: dict[str, object] = {
        "signal_id": str(raw.get("signal_id", "")),
        "title": str(raw.get("title", "")),
        "category_key": category_key,
        "category": _CATEGORY_VALUE_LABELS.get(category_key, category_key),
        "evidence": str(raw.get("evidence", "")),
        "source_ref": str(raw.get("source_ref", "")),
        "project": raw.get("project"),
        "due_date": raw.get("due_date"),
        "detail": str(raw.get("detail", "")),
    }
    if rank is not None:
        item["rank"] = rank
    return item


def brief_payload(snapshot: dict[str, object] | None) -> dict[str, object] | None:
    """把当日信号快照转成前端可渲染的结构化简报；缺明细（旧格式）返回 None。

    旧格式快照（仅计数）无法支撑组件化渲染，返回 None 由前端回退到既有
    Markdown 视图；重新生成当日简报后即写入带 ``*_list`` 明细的新快照。
    """
    if not isinstance(snapshot, dict):
        return None
    task_list = snapshot.get("task_list")
    if not isinstance(task_list, list):
        return None  # 旧格式：无结构化明细

    health_level = str(snapshot.get("health", "ok"))
    actions = snapshot.get("actions")
    selected: list[dict[str, object]] = []
    if isinstance(actions, list):
        selected = [
            _action_item(raw, rank=idx + 1)
            for idx, raw in enumerate(actions)
            if isinstance(raw, dict)
        ]

    proposals = snapshot.get("proposal_list")
    completions = snapshot.get("completion_list")
    health_reasons = snapshot.get("health_reasons")
    meeting_list = snapshot.get("meeting_list")
    pending_raw = snapshot.get("pending_review")
    if isinstance(pending_raw, int):
        pending_review = pending_raw
    elif isinstance(pending_raw, str) and pending_raw.isdigit():
        pending_review = int(pending_raw)
    else:
        pending_review = 0
    return {
        "date": str(snapshot.get("date", "")),
        "health": {
            "level": health_level,
            "label": _HEALTH_LABELS.get(health_level, health_level),
            "reasons": [str(r) for r in health_reasons] if isinstance(health_reasons, list) else [],
        },
        "meetings": [
            {
                "title": str(m.get("title", "")),
                "start_time": str(m.get("start_time", "")),
                "event_id": m.get("event_id"),
                "start_ts": m.get("start_ts"),
                "end_ts": m.get("end_ts"),
            }
            for m in meeting_list
            if isinstance(m, dict)
        ]
        if isinstance(meeting_list, list)
        else [],
        "tasks": [
            {
                "summary": str(t.get("summary", "")),
                "due_date": t.get("due_date"),
                "task_id": t.get("task_id"),
            }
            for t in task_list
            if isinstance(t, dict)
        ],
        "actions": selected,
        "proposals": [_action_item(raw) for raw in proposals if isinstance(raw, dict)]
        if isinstance(proposals, list)
        else [],
        "completions": [
            {"text": str(c.get("text", "")), "source_ref": str(c.get("source_ref", ""))}
            for c in completions
            if isinstance(c, dict)
        ]
        if isinstance(completions, list)
        else [],
        "pending_review": pending_review,
        "ranking_model": snapshot.get("ranking_model"),
    }
