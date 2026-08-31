"""飞书 OpenAPI 已鉴权客户端（携带 user_access_token 调用业务接口）。

统一解析飞书响应信封 ``{"code": 0, "msg": "...", "data": {...}}``：code != 0 或 HTTP
非 2xx 一律抛 :class:`FeishuAPIError`，不静默吞错（NFR-6）。
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAPIError

_DEFAULT_TIMEOUT = 20.0


class FeishuClient:
    def __init__(
        self,
        cfg: FeishuConfig,
        access_token: SecretStr,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.cfg = cfg
        self._token = access_token
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params, json=None)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, params=None, json=json)

    def _request(
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
        except httpx.HTTPError as exc:
            raise FeishuAPIError(f"{method} {path} 网络错误：{type(exc).__name__}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise FeishuAPIError(f"{method} {path} 返回非 JSON", status=resp.status_code) from exc

        code = data.get("code")
        if code not in (0, None):
            # msg 是飞书的错误摘要，通常不含敏感正文；保留以便审计。
            raise FeishuAPIError(
                f"{method} {path} 业务失败：{data.get('msg', 'unknown')}",
                code=int(code),
                status=resp.status_code,
            )
        if resp.status_code >= 400:
            raise FeishuAPIError(f"{method} {path} HTTP 错误", status=resp.status_code)

        result = data.get("data", data)
        return result if isinstance(result, dict) else {"data": result}
