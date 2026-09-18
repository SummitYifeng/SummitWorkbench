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


def test_completion_exposes_finish_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4096},
            },
        )

    result = _client(handler).complete("s", "u", max_retries=0)
    assert result.finish_reason == "length"


def test_completion_reports_reasoning_tokens_and_content_length():
    """诊断三件套：推理吃掉多少、真正写出多少。

    2026-09-18 真机：思考模式把 output 预算全用在 reasoning 上，content 为空，
    而账本只留了一句"不符合 schema"，无法诊断。这里锁住这两个字段必须被解析出来。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": ""}, "finish_reason": None}],
                "usage": {
                    "prompt_tokens": 18000,
                    "completion_tokens": 4096,
                    "completion_tokens_details": {"reasoning_tokens": 4096},
                },
            },
        )

    result = _client(handler).complete("s", "u", max_retries=0)

    assert result.usage.reasoning_tokens == 4096
    assert result.usage.output_tokens == 4096
    assert result.content_chars == 0
    assert result.finish_reason is None


def test_completion_handles_null_content_and_missing_reasoning_details():
    """content 为 null 时不得变成字符串 "None"；缺失 reasoning 明细时为 None。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    result = _client(handler).complete("s", "u", max_retries=0)

    assert result.text == ""
    assert result.usage.reasoning_tokens is None
    assert result.content_chars == 0


def _client_with_config(handler, **overrides) -> ModelClient:
    cfg = ModelConfig(
        capability="meeting",
        model_id="test-model",
        base_url="https://api.example.com/v1",
        credential_account="shared",
        timeout_seconds=5,
        **overrides,
    )
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ModelClient(cfg, SecretStr("sk-test"), client=http, sleep=lambda _: None)


def _capture_payload() -> tuple[dict[str, object], object]:
    import json as _json

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(_json.loads(request.content))
        return httpx.Response(200, json=OK_BODY)

    return seen, handler


def test_thinking_disabled_sends_explicit_flag():
    """思考模式默认打开且 effort=high，且与答案共用输出预算；抽取任务要能显式关掉。"""
    seen, handler = _capture_payload()

    _client_with_config(handler, thinking="disabled").complete("s", "u", max_retries=0)

    assert seen["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen


def test_thinking_default_sends_no_flag():
    """默认策略必须完全不改请求体（供应商默认行为，不是我们硬编的）。"""
    seen, handler = _capture_payload()

    _client_with_config(handler).complete("s", "u", max_retries=0)

    assert "thinking" not in seen
    assert "reasoning_effort" not in seen


def test_thinking_effort_is_forwarded():
    seen, handler = _capture_payload()

    _client_with_config(handler, thinking="low").complete("s", "u", max_retries=0)

    assert seen["reasoning_effort"] == "low"
    assert "thinking" not in seen


def test_api_key_not_in_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad"})

    with pytest.raises(LLMAPIError) as ei:
        _client(handler).complete("s", "u")
    assert "sk-test" not in str(ei.value)
