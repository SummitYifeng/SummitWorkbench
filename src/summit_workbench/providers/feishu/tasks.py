"""飞书 Task v2 创建适配器。接口形状依据飞书官方服务端 SDK。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuAPIError

CREATE_TASK_PATH = "/open-apis/task/v2/tasks"


@dataclass(frozen=True)
class CreatedTask:
    guid: str
    url: str | None = None


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
