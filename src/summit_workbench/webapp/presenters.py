"""Web API 的纯响应编码函数。"""

from __future__ import annotations

from summit_workbench.domain.brief import CATEGORY_LABELS
from summit_workbench.domain.external_action import ExternalAction
from summit_workbench.domain.review import ReviewEntry

_HEALTH_LABELS = {"ok": "正常", "degraded": "降级", "alert": "告警"}


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


__all__ = [
    "brief_payload",
    "external_action_payload",
    "review_entry_payload",
    "review_payload",
]
