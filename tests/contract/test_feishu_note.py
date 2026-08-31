"""飞书 Note 主链路契约测试：note_id → 逐字稿文档 → 正文（MockTransport，无真实调用）。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuError
from summit_workbench.providers.feishu.meetings import FeishuNoteSource

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")

NOTE_BODY = {
    "code": 0,
    "data": {
        "note": {
            "creator_id": "ou_x",
            "artifacts": [
                {"artifact_type": 1, "doc_token": "MINUTES_TOKEN"},
                {"artifact_type": 2, "doc_token": "TRANSCRIPT_TOKEN"},
            ],
        }
    },
}


def _source(handler) -> FeishuNoteSource:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuNoteSource(FeishuClient(CFG, SecretStr("tok"), client=http))


def test_fetch_transcript_picks_type2_and_reads_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/open-apis/vc/v1/notes/NID":
            return httpx.Response(200, json=NOTE_BODY)
        if path == "/open-apis/docx/v1/documents/TRANSCRIPT_TOKEN/raw_content":
            seen["read"] = path
            return httpx.Response(200, json={"code": 0, "data": {"content": "张三 00:01 大家好"}})
        return httpx.Response(404, json={"code": 1, "msg": "not found"})

    result = _source(handler).fetch_transcript("NID")
    assert result.source == "feishu-note"
    assert result.note_id == "NID"
    assert result.doc_token == "TRANSCRIPT_TOKEN"  # 选了 artifact_type=2，而非纪要 token
    assert "张三" in result.text
    assert seen["read"].endswith("TRANSCRIPT_TOKEN/raw_content")


def test_fetch_transcript_no_transcript_artifact_raises():
    body = {
        "code": 0,
        "data": {"note": {"artifacts": [{"artifact_type": 1, "doc_token": "ONLY_MINUTES"}]}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(FeishuError) as ei:
        _source(handler).fetch_transcript("NID")
    assert "逐字稿产物" in str(ei.value)


def test_get_note_missing_entity_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "data": {}})

    with pytest.raises(FeishuError):
        _source(handler).get_note("NID")
