"""会议发现契约测试：list_by_no → 会议摘要（含 note_id），含翻页（MockTransport）。"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.meetings import list_meetings_by_no

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _client(handler) -> FeishuClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("tok"), client=http)


def test_list_parses_meetings_and_note_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/vc/v1/meetings/list_by_no"
        assert request.url.params["meeting_no"] == "123456789"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "meeting_list": [
                        {
                            "id": "m1",
                            "topic": "招生周会",
                            "note_id": "n1",
                            "start_time": "1755",
                            "url": "u",
                        },
                        {"id": "m2", "topic": "无纪要会", "note_id": "", "start_time": "1756"},
                    ],
                    "has_more": False,
                },
            },
        )

    got = list_meetings_by_no(_client(handler), "123456789", 1000, 2000)
    assert [m.meeting_id for m in got] == ["m1", "m2"]
    assert got[0].note_id == "n1"
    assert got[0].topic == "招生周会"
    assert got[1].note_id is None  # 空 note_id → None（无纪要）


def test_list_follows_pagination():
    pages = {
        None: {
            "meeting_list": [{"id": "m1", "note_id": "n1"}],
            "has_more": True,
            "page_token": "p2",
        },
        "p2": {"meeting_list": [{"id": "m2", "note_id": "n2"}], "has_more": False},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("page_token")
        return httpx.Response(200, json={"code": 0, "data": pages[token]})

    got = list_meetings_by_no(_client(handler), "n", 1, 2)
    assert [m.meeting_id for m in got] == ["m1", "m2"]


def test_list_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 0, "data": {"meeting_list": [], "has_more": False}}
        )

    assert list_meetings_by_no(_client(handler), "n", 1, 2) == []
