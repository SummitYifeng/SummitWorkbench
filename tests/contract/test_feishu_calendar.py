"""飞书日历契约测试：只读采集原文直取 + 日程写回形状（MockTransport）。"""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.calendar import (
    create_event,
    list_event_instances,
    list_events,
    list_events_between,
    local_iso_to_epoch_seconds,
    primary_calendar_id,
    update_event,
)
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _client(handler) -> FeishuClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("tok"), client=http)


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/open-apis/calendar/v4/calendars/primary":
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"calendars": [{"calendar": {"calendar_id": "cal_main"}}]},
            },
        )
    if path == "/open-apis/calendar/v4/calendars/cal_main/events":
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "event_id": "e2",
                            "summary": "招生周会",
                            "start_time": {"timestamp": "1756~700"},
                            "end_time": {"timestamp": "1756~800"},
                        },
                        {
                            "event_id": "e1",
                            "summary": "全天：招生冲刺",
                            "start_time": {"date": "2026-09-01"},
                        },
                    ],
                    "has_more": False,
                },
            },
        )
    if path == "/open-apis/calendar/v4/calendars/cal_main/events/instance_view":
        # instance_view 展开循环为实例；含一条已取消的应被过滤。
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "event_id": "inst-b",
                            "summary": "钻石三角双周例会",
                            "start_time": {"timestamp": "1788247800"},
                        },
                        {
                            "event_id": "inst-cancelled",
                            "summary": "已取消例会",
                            "status": "cancelled",
                            "start_time": {"timestamp": "1788200000"},
                        },
                    ],
                    "has_more": False,
                },
            },
        )
    return httpx.Response(404, json={"code": 1, "msg": "not found"})


def test_primary_calendar_id_parsed() -> None:
    assert primary_calendar_id(_client(_handler)) == "cal_main"


def test_list_events_takes_raw_fields_and_sorts() -> None:
    events = list_events(_client(_handler), "cal_main", 1, 2)
    # 按 start_time 排序：全天 "2026-09-01" 字符串 < "1756~700" 吗？按字典序数字先。
    titles = [e.title for e in events]
    assert "招生周会" in titles
    all_day = next(e for e in events if e.event_id == "e1")
    assert all_day.is_all_day is True
    assert all_day.start_time == "2026-09-01"
    timed = next(e for e in events if e.event_id == "e2")
    assert timed.is_all_day is False
    assert timed.start_time == "1756~700"  # 原文直取，不改写


def test_list_event_instances_expands_and_filters_cancelled() -> None:
    events = list_event_instances(_client(_handler), "cal_main", 1, 2)
    assert [e.event_id for e in events] == ["inst-b"]  # 已取消实例被过滤
    assert events[0].title == "钻石三角双周例会"


def test_list_events_between_uses_instance_view() -> None:
    # 便捷入口解析主日历后应走 instance_view（今日会议的正确来源）。
    events = list_events_between(_client(_handler), 1, 2)
    assert [e.event_id for e in events] == ["inst-b"]


def test_local_iso_converts_with_timezone() -> None:
    assert local_iso_to_epoch_seconds("2026-09-10T14:00", "Asia/Shanghai") == "1789020000"
    # 带时区的输入按原时区换算
    assert local_iso_to_epoch_seconds("2026-09-10T06:00+00:00", "Asia/Shanghai") == "1789020000"


def _write_client(seen: dict[str, object]) -> FeishuClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        if request.method == "POST" and request.url.path.endswith("/events"):
            return httpx.Response(200, json={"code": 0, "data": {"event": {"event_id": "ev-new"}}})
        return httpx.Response(200, json={"code": 0, "data": {}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("tok"), client=http)


def test_create_event_posts_seconds_timestamps() -> None:
    seen: dict[str, object] = {}
    client = _write_client(seen)
    event_id = create_event(
        client,
        "cal_main",
        "需求对齐会",
        "2026-09-10T14:00",
        "2026-09-10T15:00",
        timezone="Asia/Shanghai",
    )
    assert event_id == "ev-new"
    assert seen["method"] == "POST"
    assert seen["path"] == "/open-apis/calendar/v4/calendars/cal_main/events"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["summary"] == "需求对齐会"
    start = body["start_time"]
    end = body["end_time"]
    assert isinstance(start, dict) and isinstance(end, dict)
    # 官方日历契约：时间戳是 unix 秒的字符串（不是毫秒/数字）。
    assert isinstance(start["timestamp"], str)
    assert start["timestamp"] == local_iso_to_epoch_seconds("2026-09-10T14:00", "Asia/Shanghai")
    assert end["timestamp"] == local_iso_to_epoch_seconds("2026-09-10T15:00", "Asia/Shanghai")


def test_update_event_patches_only_given_fields() -> None:
    seen: dict[str, object] = {}
    client = _write_client(seen)
    update_event(
        client,
        "cal_main",
        "ev-1",
        summary="改标题",
        timezone="Asia/Shanghai",
    )
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/open-apis/calendar/v4/calendars/cal_main/events/ev-1"
    body = seen["body"]
    assert isinstance(body, dict)
    assert set(body) == {"summary"}
    update_event(
        client,
        "cal_main",
        "ev-1",
        start_iso="2026-09-10T09:00",
        end_iso="2026-09-10T10:00",
        timezone="Asia/Shanghai",
    )
    body = seen["body"]
    assert isinstance(body, dict)
    assert set(body) == {"start_time", "end_time"}
    start = body["start_time"]
    assert isinstance(start, dict)
    assert start["timestamp"] == local_iso_to_epoch_seconds("2026-09-10T09:00", "Asia/Shanghai")
