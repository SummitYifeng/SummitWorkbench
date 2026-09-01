"""飞书日历事实采集（M2-1）：主日历 → 指定时间窗内的会议/日程事件。

事实区硬约束（PRD 3.4 / G1）：这里只把飞书原始响应字段**原样**取出（summary / 起止时间），
不做任何模型改写。上层简报直取这些字段。

端点为**预期端点，依官方文档给出，待真机冒烟核实后固定**（沿用 M0-4/M0-10 范式）：
- 主日历：``POST /open-apis/calendar/v4/calendars/primary``（应用/用户主日历）；
- 事件列表：``GET /open-apis/calendar/v4/calendars/{calendar_id}/events``（起止为 unix 秒）。
所需 scope ``calendar:calendar:readonly`` 已在开放平台开通。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuError

PRIMARY_CALENDAR_PATH = "/open-apis/calendar/v4/calendars/primary"
EVENTS_PATH = "/open-apis/calendar/v4/calendars/{calendar_id}/events"


@dataclass(frozen=True)
class CalendarEvent:
    """一条日历事件（原文直取）。``start_time`` 保留飞书原始表示，不做人类改写。"""

    event_id: str
    title: str
    start_time: str  # 定时事件为 unix 秒字符串；全天事件为 YYYY-MM-DD
    end_time: str | None = None
    is_all_day: bool = False


def primary_calendar_id(client: FeishuClient) -> str:
    """取主日历 calendar_id。响应缺少主日历即显式报错（不猜测）。"""
    data = client.post(PRIMARY_CALENDAR_PATH, json={})
    # 官方响应形如 {"calendars": [{"calendar": {"calendar_id": "..."}}]}
    calendars = data.get("calendars")
    if isinstance(calendars, list):
        for entry in calendars:
            cal = entry.get("calendar") if isinstance(entry, dict) else None
            if isinstance(cal, dict) and cal.get("calendar_id"):
                return str(cal["calendar_id"])
    # 兼容部分租户直接返回 {"calendar": {"calendar_id": ...}}
    cal = data.get("calendar")
    if isinstance(cal, dict) and cal.get("calendar_id"):
        return str(cal["calendar_id"])
    raise FeishuError("主日历响应缺少 calendar_id")


def _parse_event(raw: dict[str, Any]) -> CalendarEvent | None:
    start = raw.get("start_time") or {}
    end = raw.get("end_time") or {}
    if not isinstance(start, dict):
        return None
    is_all_day = "date" in start and "timestamp" not in start
    start_repr = str(start.get("timestamp") or start.get("date") or "")
    if not start_repr:
        return None
    end_repr_raw = end.get("timestamp") or end.get("date") if isinstance(end, dict) else None
    return CalendarEvent(
        event_id=str(raw.get("event_id", "")),
        title=str(raw.get("summary", "") or "(无标题)"),
        start_time=start_repr,
        end_time=str(end_repr_raw) if end_repr_raw else None,
        is_all_day=is_all_day,
    )


def list_events(
    client: FeishuClient,
    calendar_id: str,
    start_unix: int,
    end_unix: int,
    *,
    max_items: int = 100,
) -> list[CalendarEvent]:
    """列出 [start_unix, end_unix]（unix 秒）内的事件，逐页翻取并按起始时间排序。"""
    events: list[CalendarEvent] = []
    page_token: str | None = None
    path = EVENTS_PATH.format(calendar_id=calendar_id)
    while len(events) < max_items:
        params: dict[str, Any] = {
            "start_time": str(start_unix),
            "end_time": str(end_unix),
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        data = client.get(path, params)
        for raw in data.get("items") or []:
            if isinstance(raw, dict):
                parsed = _parse_event(raw)
                if parsed is not None:
                    events.append(parsed)
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = str(data["page_token"])
    events.sort(key=lambda e: e.start_time)
    return events[:max_items]


def list_events_between(
    client: FeishuClient, start_unix: int, end_unix: int, *, max_items: int = 100
) -> list[CalendarEvent]:
    """便捷入口：解析主日历后列出时间窗内事件。"""
    calendar_id = primary_calendar_id(client)
    return list_events(client, calendar_id, start_unix, end_unix, max_items=max_items)
