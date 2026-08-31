"""会议发现契约测试：list_by_no(meeting_briefs) + 会议详情(note_id)（MockTransport）。"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.meetings import list_meeting_briefs, list_meetings_by_no

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _client(handler) -> FeishuClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("tok"), client=http)


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/open-apis/vc/v1/meetings/list_by_no":
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "meeting_briefs": [
                        {"id": "m1", "meeting_no": "937075886", "topic": "招生周会"},
                        {"id": "m2", "meeting_no": "937075886", "topic": "无纪要会"},
                    ],
                    "has_more": False,
                },
            },
        )
    if path == "/open-apis/vc/v1/meetings/m1":
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"meeting": {"id": "m1", "note_id": "n1", "start_time": "1755"}},
            },
        )
    if path == "/open-apis/vc/v1/meetings/m2":
        return httpx.Response(200, json={"code": 0, "data": {"meeting": {"id": "m2"}}})
    return httpx.Response(404, json={"code": 1, "msg": "not found"})


def test_briefs_parsed_from_meeting_briefs_key():
    briefs = list_meeting_briefs(_client(_handler), "937075886", 1000, 2000)
    assert [b["id"] for b in briefs] == ["m1", "m2"]
    assert briefs[0]["topic"] == "招生周会"


def test_list_enriches_note_id_from_detail():
    got = list_meetings_by_no(_client(_handler), "937075886", 1000, 2000)
    assert [m.meeting_id for m in got] == ["m1", "m2"]
    assert got[0].note_id == "n1"  # 从会议详情补全
    assert got[0].topic == "招生周会"
    assert got[0].start_time == "1755"
    assert got[1].note_id is None  # 无 note_id 的会议


def test_list_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 0, "data": {"meeting_briefs": [], "has_more": False}}
        )

    assert list_meetings_by_no(_client(handler), "n", 1, 2) == []
