"""OpenAI 兼容的云端模型客户端（chat/completions）。

这是唯一知道具体 HTTP 形状的地方；上层只见「给消息、拿结构化文本 + 用量」。
失败策略（L41）：瞬时故障（超时 / 429 / 5xx）按指数退避最多重试 3 次（共 4 次调用）；
非重试类错误立即抛出。任何情况都不静默吞错（NFR-6）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMAPIError, LLMTimeoutError

MAX_RETRIES = 3  # 初次失败后最多再重试 3 次
_BACKOFF_BASE = 0.5


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CompletionResult:
    text: str
    usage: Usage
    model_id: str
    attempts: int


class ModelClient:
    def __init__(
        self,
        cfg: ModelConfig,
        api_key: SecretStr,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = cfg
        self._key = api_key
        self._client = client or httpx.Client(timeout=cfg.timeout_seconds)
        self._sleep = sleep

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self.cfg.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.cfg.max_output_tokens,
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.cfg.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._key.get_secret_value()}"}

        for attempt in range(1, MAX_RETRIES + 2):  # 1 次初调 + 最多 3 次重试
            try:
                return self._attempt_once(url, payload, headers, attempt)
            except (LLMTimeoutError, LLMAPIError) as exc:
                if attempt <= MAX_RETRIES and _is_retryable(exc):
                    self._sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                raise
        raise AssertionError("unreachable")  # 循环要么 return 要么 raise

    def _attempt_once(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], attempt: int
    ) -> CompletionResult:
        try:
            resp = self._client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"{self.cfg.model_id} 请求超时（第 {attempt} 次）") from exc
        except httpx.HTTPError as exc:
            raise LLMAPIError(f"网络错误：{type(exc).__name__}", retryable=True) from exc

        if resp.status_code == 429 or resp.status_code >= 500:
            raise LLMAPIError(
                f"{self.cfg.model_id} 服务暂时不可用（HTTP {resp.status_code}，第 {attempt} 次）",
                status=resp.status_code,
                retryable=True,
            )
        if resp.status_code >= 400:
            raise LLMAPIError(
                f"{self.cfg.model_id} 调用被拒（HTTP {resp.status_code}）",
                status=resp.status_code,
                retryable=False,
            )
        return _parse_completion(resp, self.cfg.model_id, attempt)


def _is_retryable(exc: Exception | None) -> bool:
    if isinstance(exc, LLMTimeoutError):
        return True
    return isinstance(exc, LLMAPIError) and exc.retryable


def _parse_completion(resp: httpx.Response, model_id: str, attempt: int) -> CompletionResult:
    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMAPIError(f"{model_id} 返回非 JSON", status=resp.status_code) from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMAPIError(f"{model_id} 响应缺少 choices/message", status=resp.status_code) from exc

    usage_raw = data.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("prompt_tokens", 0)),
        output_tokens=int(usage_raw.get("completion_tokens", 0)),
    )
    return CompletionResult(text=str(text), usage=usage, model_id=model_id, attempts=attempt)
