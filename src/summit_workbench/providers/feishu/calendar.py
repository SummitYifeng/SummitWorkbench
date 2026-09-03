"""飞书日历适配：事实采集（M2-1 只读）+ 日程写回（审批新建会议 / 工作台行内编辑）。

事实区硬约束（PRD 3.4 / G1）：只读部分把飞书原始响应字段**原样**取出（summary / 起止时间），
不做任何模型改写。上层简报直取这些字段。

写回部分（Web 工作台「新建会议 / 编辑会议」）：创建/更新主日历日程事件。日历事件的时间戳
按官方契约使用 **unix 秒的字符串**（``start_time.timestamp``）；创建事件不支持直接传参会人
（如需邀请走 attendees 二次调用，MVP 不做）。写 scope ``calendar:calendar`` 已开通并重新授权，
2026-09-03 真机核实：创建 / 更新（标题与起止时间）均可写回且可回读一致（读 scope
``calendar:calendar:readonly`` 随写 scope 一并授予）。

端点已经真机冒烟核实后固定（沿用 M0-4/M0-10 范式）：
- 主日历：``POST /open-apis/calendar/v4/calendars/primary``（应用/用户主日历）；
- 事件列表：``GET /open-apis/calendar/v4/calendars/{calendar_id}/events``（起止为 unix 秒）；
- 创建事件：``POST /open-apis/calendar/v4/calendars/{calendar_id}/events``；
- 更新事件：``PATCH /open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}``。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuAPIError, FeishuError

PRIMARY_CALENDAR_PATH = "/open-apis/calendar/v4/calendars/primary"
EVENTS_PATH = "/open-apis/calendar/v4/calendars/{calendar_id}/events"
# instance_view 会**展开循环事件**为窗口内的实例（真机核实：普通 events 列表返回循环主体的
# 原始 start_time，不是当天实例；「今日会议」必须用 instance_view）。
INSTANCES_PATH = "/open-apis/calendar/v4/calendars/{calendar_id}/events/instance_view"


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


def list_event_instances(
    client: FeishuClient,
    calendar_id: str,
    start_unix: int,
    end_unix: int,
    *,
    max_items: int = 100,
) -> list[CalendarEvent]:
    """列出 [start_unix, end_unix] 内的**事件实例**（展开循环），按起始时间排序。

    这是「今日会议」的正确来源：instance_view 返回窗口内实际发生的实例，而非循环主体。
    已取消的实例（status=cancelled）被过滤。
    """
    events: list[CalendarEvent] = []
    page_token: str | None = None
    path = INSTANCES_PATH.format(calendar_id=calendar_id)
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
            if not isinstance(raw, dict) or raw.get("status") == "cancelled":
                continue
            parsed = _parse_instance(raw)
            if parsed is not None:
                events.append(parsed)
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = str(data["page_token"])
    events.sort(key=lambda e: e.start_time)
    return events[:max_items]


def _parse_instance(raw: dict[str, Any]) -> CalendarEvent | None:
    """instance_view 项：start_time/end_time 直接是 {timestamp} 或 {date}（无 dict 包裹时兜底）。"""
    start = raw.get("start_time")
    if isinstance(start, dict):
        return _parse_event(raw)
    # 部分响应把实例时间放平铺字段。
    start_repr = str(start or raw.get("start_timestamp") or "")
    if not start_repr:
        return None
    end_raw = raw.get("end_time")
    if isinstance(end_raw, dict):
        end_repr = str(end_raw.get("timestamp") or end_raw.get("date") or "")
    elif end_raw:
        end_repr = str(end_raw)
    else:
        end_repr = ""
    return CalendarEvent(
        event_id=str(raw.get("event_id", "")),
        title=str(raw.get("summary", "") or "(无标题)"),
        start_time=start_repr,
        end_time=end_repr or None,
    )


def list_events_between(
    client: FeishuClient, start_unix: int, end_unix: int, *, max_items: int = 100
) -> list[CalendarEvent]:
    """便捷入口：解析主日历后列出时间窗内**实例**（今日会议）。"""
    calendar_id = primary_calendar_id(client)
    return list_event_instances(client, calendar_id, start_unix, end_unix, max_items=max_items)


# ---- 日程写回（Web 工作台：审批新建会议 / 行内编辑会议） ----


def local_iso_to_epoch_seconds(value: str, timezone: str) -> str:
    """把本地无时区的 ``YYYY-MM-DDTHH:MM`` 转成 unix 秒字符串（日历事件时间戳用秒）。

    非法输入抛出 ValueError，让上层把不可执行的写回显式拒绝（不猜测）。
    """
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(timezone))
    return str(int(moment.timestamp()))


def _event_id_from(data: dict[str, Any], verb: str) -> str:
    raw = data.get("event")
    if not isinstance(raw, dict):
        raise FeishuAPIError(f"{verb} 响应缺少 event")
    event_id = str(raw.get("event_id") or "")
    if not event_id:
        raise FeishuAPIError(f"{verb} 响应缺少 event_id")
    return event_id


def create_event(
    client: FeishuClient,
    calendar_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    *,
    timezone: str,
) -> str:
    """在主日历创建一条定时日程事件，返回 event_id（幂等键由上层 candidate_id 派生）。

    起止时间用本地 naive ``YYYY-MM-DDTHH:MM``，本函数按 ``timezone`` 换算成秒级时间戳。
    """
    body: dict[str, object] = {
        "summary": summary,
        "start_time": {"timestamp": local_iso_to_epoch_seconds(start_iso, timezone)},
        "end_time": {"timestamp": local_iso_to_epoch_seconds(end_iso, timezone)},
    }
    data = client.post(EVENTS_PATH.format(calendar_id=calendar_id), json=body)
    return _event_id_from(data, "POST /calendar/v4/events")


def update_event(
    client: FeishuClient,
    calendar_id: str,
    event_id: str,
    *,
    summary: str | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    timezone: str,
) -> None:
    """更新日历事件（只改显式给出的字段）；起止为本地 naive ``YYYY-MM-DDTHH:MM``。"""
    body: dict[str, object] = {}
    if summary is not None:
        body["summary"] = summary
    if start_iso is not None:
        body["start_time"] = {"timestamp": local_iso_to_epoch_seconds(start_iso, timezone)}
    if end_iso is not None:
        body["end_time"] = {"timestamp": local_iso_to_epoch_seconds(end_iso, timezone)}
    if not body:
        raise ValueError("没有需要更新的字段")
    path = f"{EVENTS_PATH.format(calendar_id=calendar_id)}/{event_id}"
    client.patch(path, json=body)
