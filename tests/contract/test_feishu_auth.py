"""飞书 OAuth 授权/刷新契约测试（httpx MockTransport，无真实调用）。"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from summit_workbench.providers.feishu.auth import (
    build_authorize_url,
    exchange_code,
    get_tenant_access_token,
    refresh_token,
)
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError

CFG = FeishuConfig(app_id="cli_test123", redirect_uri="http://localhost:8765/callback")


def _secret(value: str):
    from pydantic import SecretStr

    return SecretStr(value)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_authorize_url_shape():
    url = build_authorize_url(CFG, state="xyz")
    parsed = urlparse(url)
    assert parsed.netloc == "accounts.feishu.cn"
    assert parsed.path == "/open-apis/authen/v1/authorize"
    q = parse_qs(parsed.query)
    assert q["client_id"] == ["cli_test123"]
    assert q["redirect_uri"] == ["http://localhost:8765/callback"]
    assert q["response_type"] == ["code"]
    assert q["state"] == ["xyz"]
    assert "offline_access" in q["scope"][0]


def test_exchange_code_success():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "access_token": "u-access-xyz",
                "expires_in": 7200,
                "refresh_token": "u-refresh-abc",
                "refresh_token_expires_in": 2592000,
                "scope": "calendar:calendar:readonly offline_access",
            },
        )

    tokens = exchange_code(CFG, _secret("app-secret"), "the-code", client=_client(handler))
    assert tokens.access_token.get_secret_value() == "u-access-xyz"
    assert tokens.refresh_token is not None
    assert tokens.expires_in == 7200
    # 请求打到 v2 token 端点，body 用 authorization_code
    assert captured["url"].endswith("/open-apis/authen/v2/oauth/token")
    assert captured["body"]["grant_type"] == "authorization_code"
    assert captured["body"]["client_secret"] == "app-secret"


def test_refresh_success_rotates_refresh_token():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["grant_type"] == "refresh_token"
        return httpx.Response(
            200,
            json={
                "access_token": "u-access-new",
                "expires_in": 7200,
                "refresh_token": "u-refresh-rotated",
                "refresh_token_expires_in": 2592000,
                "scope": "task:task",
            },
        )

    tokens = refresh_token(CFG, _secret("s"), _secret("old-rt"), client=_client(handler))
    assert tokens.access_token.get_secret_value() == "u-access-new"
    assert tokens.refresh_token is not None
    assert tokens.refresh_token.get_secret_value() == "u-refresh-rotated"


def test_refresh_invalid_grant_needs_reauthorize():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})

    with pytest.raises(FeishuAuthError) as ei:
        refresh_token(CFG, _secret("s"), _secret("bad"), client=_client(handler))
    assert ei.value.needs_reauthorize is True


def test_tenant_access_token_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/auth/v3/tenant_access_token/internal"
        body = json.loads(request.content)
        assert body["app_id"] == "cli_test123"
        assert body["app_secret"] == "app-secret"
        return httpx.Response(
            200, json={"code": 0, "msg": "ok", "tenant_access_token": "t-abc", "expire": 7200}
        )

    tok = get_tenant_access_token(CFG, _secret("app-secret"), client=_client(handler))
    assert tok.get_secret_value() == "t-abc"


def test_tenant_access_token_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 10003, "msg": "app secret invalid"})

    with pytest.raises(FeishuAuthError):
        get_tenant_access_token(CFG, _secret("bad"), client=_client(handler))


def test_auth_error_message_has_no_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_client"})

    with pytest.raises(FeishuAuthError) as ei:
        exchange_code(CFG, _secret("top-secret-value"), "c", client=_client(handler))
    assert "top-secret-value" not in str(ei.value)
