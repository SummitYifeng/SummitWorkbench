"""Web 面板的 JSON API 契约（纯函数，无 IO；供 SPA 前端消费）。

SSR 视图（views.py）与 JSON API（本模块）共用同一套领域逻辑与审批页事实源
（meetings.md / inbox.md / 状态账本），保证 Web 面板永远与 CLI 看到同一份数据。
"""

from __future__ import annotations

from pydantic import BaseModel

from summit_workbench.domain.review import ReviewEntry

# ---- 请求体模型（SPA 以 JSON 提交） ----


class DecidePayload(BaseModel):
    candidate_id: str
    decision: str  # pending | approved | rejected


class BatchDecidePayload(BaseModel):
    candidate_ids: list[str]
    decision: str  # pending | approved | rejected


class EditPayload(BaseModel):
    candidate_id: str
    description: str | None = None
    target_project: str | None = None
    route: str | None = None  # feishu-task | project-main | project-inbox | global-inbox
    due_date: str | None = None


class CapturePayload(BaseModel):
    text: str


class AskHistoryTurn(BaseModel):
    """对话中的一轮历史问答（追问上下文）：只带问题原文 + 当时引用过的来源 id。

    刻意**不带** AI 当时的答案全文——AI 回答不是 vault 事实，不进入下一轮来源集合。
    """

    question: str
    sources: list[str] = []


class AskPayload(BaseModel):
    question: str
    history: list[AskHistoryTurn] = []


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
