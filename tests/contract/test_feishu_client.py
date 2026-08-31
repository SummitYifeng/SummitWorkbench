"""飞书已鉴权客户端信封解析契约测试。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAPIError
from summit_workbench.providers.feishu.meetings import verify_identity

CFG = FeishuConfig(app_id="app1", redirect_uri="http://localhost/cb")


def _client(handler) -> FeishuClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FeishuClient(CFG, SecretStr("access-tok"), client=http)


def test_envelope_success_returns_data_and_sends_bearer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"name": "张三"}})

    data = verify_identity(_client(handler))
    assert data["name"] == "张三"
    assert seen["auth"] == "Bearer access-tok"


def test_envelope_business_error_raises_with_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 99991663, "msg": "permission denied"})

    with pytest.raises(FeishuAPIError) as ei:
        verify_identity(_client(handler))
    assert ei.value.code == 99991663


def test_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    with pytest.raises(FeishuAPIError):
        verify_identity(_client(handler))
