"""飞书 OpenAPI 已鉴权客户端（携带 user_access_token 调用业务接口）。

统一解析飞书响应信封 ``{"code": 0, "msg": "...", "data": {...}}``：code != 0 或 HTTP
非 2xx 一律抛 :class:`FeishuAPIError`，不静默吞错（NFR-6）。

瞬时故障（超时 / 429 / 5xx / 网络抖动）按指数退避重试并尊重 ``Retry-After``（LHF #3，
与 LLM 客户端共用 :func:`providers._resilient.send_with_retry`）；业务失败（code != 0）与
其它 4xx 属语义错误，立即上抛不重试。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

from summit_workbench.providers._resilient import (
    build_client,
    parse_retry_after,
    send_with_retry,
)
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAPIError

_DEFAULT_TIMEOUT = 20.0
MAX_RETRIES = 3  # 初次失败后最多再重试 3 次


class FeishuClient:
    def __init__(
        self,
        cfg: FeishuConfig,
        access_token: SecretStr,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.cfg = cfg
        self._token = access_token
        self._client = client or build_client(_DEFAULT_TIMEOUT)
        self._sleep = sleep
        self._max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params, json=None)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, params=None, json=json)

    def patch(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("PATCH", path, params=None, json=json)

    def delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path, params=None, json=None)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return send_with_retry(
            lambda _attempt: self._attempt_once(method, path, params=params, json=json),
            retry_on=(FeishuAPIError,),
            is_retryable=lambda exc: isinstance(exc, FeishuAPIError) and exc.retryable,
            retry_after=lambda exc: getattr(exc, "retry_after", None),
            max_retries=self._max_retries,
            sleep=self._sleep,
        )

    def _attempt_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{self.cfg.openapi_host}{path}"
        try:
            resp = self._client.request(
                method, url, params=params, json=json, headers=self._headers()
            )
        except httpx.TimeoutException as exc:
            raise FeishuAPIError(f"{method} {path} 请求超时", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise FeishuAPIError(
                f"{method} {path} 网络错误：{type(exc).__name__}", retryable=True
            ) from exc

        # 先判 HTTP 层的瞬时故障：网关 5xx / 限流 429 未必返回 JSON 信封，按可重试处理。
        if resp.status_code == 429 or resp.status_code >= 500:
            raise FeishuAPIError(
                f"{method} {path} 服务暂时不可用（HTTP {resp.status_code}）",
                status=resp.status_code,
                retryable=True,
                retry_after=parse_retry_after(resp),
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise FeishuAPIError(f"{method} {path} 返回非 JSON", status=resp.status_code) from exc

        code = data.get("code")
        if code not in (0, None):
            # msg 是飞书的错误摘要，通常不含敏感正文；保留以便审计。业务失败不重试。
            raise FeishuAPIError(
                f"{method} {path} 业务失败：{data.get('msg', 'unknown')}",
                code=int(code),
                status=resp.status_code,
            )
        if resp.status_code >= 400:
            raise FeishuAPIError(f"{method} {path} HTTP 错误", status=resp.status_code)

        result = data.get("data", data)
        return result if isinstance(result, dict) else {"data": result}
