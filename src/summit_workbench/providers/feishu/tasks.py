"""飞书 Task v2 适配器：创建（M1-4）+ 列举（M2-1）。接口形状依据飞书官方服务端 SDK。

列举用于晨间简报的**事实区**：任务名 / 截止时间 / 完成状态原样直取，不经模型（PRD 3.4 / G1）。
端点为**预期端点**，确切分页/字段待真机冒烟核实（scope ``task:task`` 已开通）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuAPIError

CREATE_TASK_PATH = "/open-apis/task/v2/tasks"
LIST_TASKS_PATH = "/open-apis/task/v2/tasks"


@dataclass(frozen=True)
class CreatedTask:
    guid: str
    url: str | None = None


@dataclass(frozen=True)
class TaskItem:
    """一条飞书任务（原文直取）。``due_date`` 为 ISO 日期或 None（无截止）。"""

    guid: str
    summary: str
    due_date: str | None
    completed: bool
    completed_at: str | None = None


def _due_iso(due: dict[str, Any] | None, timezone: str) -> str | None:
    """把飞书任务的 due（含毫秒 timestamp）转成本地时区 ISO 日期；无则 None。"""
    if not isinstance(due, dict):
        return None
    ts = due.get("timestamp")
    if ts in (None, "", "0"):
        return None
    try:
        moment = datetime.fromtimestamp(int(ts) / 1000, tz=ZoneInfo(timezone))
    except (ValueError, OSError):
        return None
    return moment.date().isoformat()


def _parse_task(raw: dict[str, Any], timezone: str) -> TaskItem | None:
    guid = str(raw.get("guid") or raw.get("task_id") or "")
    if not guid:
        return None
    completed_at = raw.get("completed_at")
    # 飞书以 completed_at 非空/非 "0" 表示已完成。
    completed = bool(completed_at) and str(completed_at) not in ("", "0")
    return TaskItem(
        guid=guid,
        summary=str(raw.get("summary", "") or "(无标题任务)"),
        due_date=_due_iso(raw.get("due"), timezone),
        completed=completed,
        completed_at=str(completed_at) if completed else None,
    )


def list_tasks(
    client: FeishuClient,
    *,
    timezone: str,
    completed: bool | None = None,
    max_items: int = 100,
) -> list[TaskItem]:
    """列举当前用户任务，逐页翻取。

    ``completed=None`` 取全部；``False`` 只取未完成（简报「需要处理」用）；``True`` 只取已完成
    （「最近完成」用）。飞书侧过滤能力以真机为准，这里同时在客户端按 ``completed`` 兜底过滤。
    """
    items: list[TaskItem] = []
    page_token: str | None = None
    while len(items) < max_items:
        params: dict[str, Any] = {"page_size": 50}
        if completed is not None:
            params["completed"] = "true" if completed else "false"
        if page_token:
            params["page_token"] = page_token
        data = client.get(LIST_TASKS_PATH, params)
        for raw in data.get("items") or []:
            if isinstance(raw, dict):
                parsed = _parse_task(raw, timezone)
                if parsed is not None and (completed is None or parsed.completed is completed):
                    items.append(parsed)
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = str(data["page_token"])
    return items[:max_items]


def _client_token(candidate_id: str) -> str:
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:32]
    return f"swb-{digest}"


def _all_day_due(value: str, timezone: str) -> dict[str, object]:
    day = date.fromisoformat(value)
    moment = datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone))
    return {"timestamp": int(moment.timestamp() * 1000), "is_all_day": True}


def create_task(
    client: FeishuClient,
    summary: str,
    due_date: str | None,
    candidate_id: str,
    *,
    timezone: str,
) -> CreatedTask:
    """创建任务；candidate ID 派生 client_token，让飞书侧也参与幂等防重。"""
    body: dict[str, object] = {
        "summary": summary,
        "description": f"由 SummitWorkbench 会议审批创建（{candidate_id}）",
        "client_token": _client_token(candidate_id),
    }
    if due_date is not None:
        body["due"] = _all_day_due(due_date, timezone)
    data = client.post(CREATE_TASK_PATH, json=body)
    raw = data.get("task")
    if not isinstance(raw, dict):
        raise FeishuAPIError("POST /task/v2/tasks 响应缺少 task")
    guid = str(raw.get("guid") or raw.get("task_id") or "")
    if not guid:
        raise FeishuAPIError("POST /task/v2/tasks 响应缺少 guid/task_id")
    return CreatedTask(guid=guid, url=str(raw["url"]) if raw.get("url") else None)
