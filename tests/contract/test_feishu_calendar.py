"""飞书日历采集契约测试：主日历解析 + 事件列表原文直取（MockTransport）。"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.calendar import (
    list_events,
    list_events_between,
    primary_calendar_id,
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


def test_list_events_between_resolves_primary_then_lists() -> None:
    events = list_events_between(_client(_handler), 1, 2)
    assert len(events) == 2
