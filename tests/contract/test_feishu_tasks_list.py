"""飞书任务列举契约测试：截止日期换算 + 完成状态 + 客户端兜底过滤（MockTransport）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.tasks import list_tasks

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")
TZ = "Asia/Shanghai"


def _client(handler) -> FeishuClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("tok"), client=http)


def _due_ms(iso: str) -> str:
    moment = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(TZ))
    return str(int(moment.timestamp() * 1000))


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/open-apis/task/v2/tasks":
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "guid": "t1",
                            "summary": "交招生周报",
                            "due": {"timestamp": _due_ms("2026-09-02T00:00:00")},
                            "completed_at": "0",
                        },
                        {
                            "guid": "t2",
                            "summary": "无截止的任务",
                            "completed_at": "0",
                        },
                        {
                            "guid": "t3",
                            "summary": "已完成的任务",
                            "completed_at": "1756700000000",
                        },
                    ],
                    "has_more": False,
                },
            },
        )
    return httpx.Response(404, json={"code": 1, "msg": "not found"})


def test_list_tasks_parses_due_and_completion() -> None:
    items = list_tasks(_client(_handler), timezone=TZ)
    by_id = {t.guid: t for t in items}
    assert by_id["t1"].due_date == "2026-09-02"
    assert by_id["t1"].completed is False
    assert by_id["t2"].due_date is None
    assert by_id["t3"].completed is True


def test_list_tasks_client_side_filter_incomplete() -> None:
    items = list_tasks(_client(_handler), timezone=TZ, completed=False)
    assert {t.guid for t in items} == {"t1", "t2"}


def test_list_tasks_client_side_filter_completed() -> None:
    items = list_tasks(_client(_handler), timezone=TZ, completed=True)
    assert {t.guid for t in items} == {"t3"}
