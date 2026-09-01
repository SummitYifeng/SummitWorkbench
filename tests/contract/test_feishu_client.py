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
    return FeishuClient(CFG, SecretStr("access-tok"), client=http, sleep=lambda _: None)


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


def test_retries_on_500_then_succeeds():
    """瞬时 5xx 抖动不再让整趟拉取报废：退避后重试成功（LHF #3）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"code": 0, "data": {"name": "张三"}})

    data = verify_identity(_client(handler))
    assert data["name"] == "张三"
    assert calls["n"] == 3


def test_exhausts_retries_on_persistent_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down")

    with pytest.raises(FeishuAPIError):
        verify_identity(_client(handler))
    assert calls["n"] == 4  # 1 初调 + 3 重试


def test_business_error_is_not_retried():
    """code != 0 是语义失败（如无权限），立即上抛不重试。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"code": 99991663, "msg": "denied"})

    with pytest.raises(FeishuAPIError):
        verify_identity(_client(handler))
    assert calls["n"] == 1


def test_timeout_is_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("slow")

    with pytest.raises(FeishuAPIError):
        verify_identity(_client(handler))
    assert calls["n"] == 4


def test_retry_after_header_is_honored():
    """429 带 Retry-After：按服务端指定秒数等待，而非盲目指数退避。"""
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, text="slow down")
        return httpx.Response(200, json={"code": 0, "data": {"name": "张三"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = FeishuClient(CFG, SecretStr("access-tok"), client=http, sleep=slept.append)
    verify_identity(client)
    assert slept == [7.0]
