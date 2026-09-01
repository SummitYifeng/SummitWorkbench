"""云端模型客户端契约测试（httpx MockTransport，退避 sleep 置空，无真实调用）。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMAPIError, LLMTimeoutError

CFG = ModelConfig(
    capability="meeting",
    model_id="test-model",
    base_url="https://api.example.com/v1",
    credential_account="shared",
    timeout_seconds=5,
)

OK_BODY = {
    "choices": [{"message": {"content": '{"one_minute_summary":"ok"}'}}],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
}


def _client(handler) -> ModelClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ModelClient(CFG, SecretStr("sk-test"), client=http, sleep=lambda _: None)


def test_success_extracts_text_and_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    result = _client(handler).complete("sys", "user")
    assert result.text == '{"one_minute_summary":"ok"}'
    assert result.usage.input_tokens == 1200
    assert result.usage.output_tokens == 300
    assert result.attempts == 1
    assert seen["auth"] == "Bearer sk-test"
    # json_mode 默认开启，走 chat/completions
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["model"] == "test-model"


def test_retries_on_500_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(500, json={"error": "server"})
        return httpx.Response(200, json=OK_BODY)

    result = _client(handler).complete("s", "u")
    assert calls["n"] == 3
    assert result.attempts == 3


def test_exhausts_retries_and_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "down"})

    with pytest.raises(LLMAPIError):
        _client(handler).complete("s", "u")
    # 1 初调 + 3 重试 = 4 次
    assert calls["n"] == 4


def test_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LLMAPIError) as ei:
        _client(handler).complete("s", "u")
    assert calls["n"] == 1
    assert ei.value.retryable is False


def test_timeout_is_retried_then_raised():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("slow")

    with pytest.raises(LLMTimeoutError):
        _client(handler).complete("s", "u")
    assert calls["n"] == 4


def test_retry_after_header_is_honored():
    """429 带 Retry-After：按服务端指定秒数等待（LHF #3）。"""
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "9"}, json={"error": "rate"})
        return httpx.Response(200, json=OK_BODY)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ModelClient(CFG, SecretStr("sk-test"), client=http, sleep=slept.append)
    client.complete("s", "u")
    assert slept == [9.0]


def test_api_key_not_in_error(capfd):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad"})

    with pytest.raises(LLMAPIError) as ei:
        _client(handler).complete("s", "u")
    assert "sk-test" not in str(ei.value)
