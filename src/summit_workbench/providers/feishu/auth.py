"""飞书用户身份授权与 token 刷新（OAuth 2.0，authen v2）。

端点已对官方文档核实（2026-08）：
- 授权：GET  {authorize_host}/open-apis/authen/v1/authorize
- 令牌：POST {openapi_host}/open-apis/authen/v2/oauth/token  （授权码换取与刷新共用）

要点：
- 只有 scope 含 ``offline_access`` 才会返回 refresh_token。
- **refresh_token 单次有效**：每次刷新都会返回新的 refresh_token，旧的立即失效，
  因此刷新后必须把新值回写 Keychain（见 client / CLI 层）。
- 任何失败都抛出显式错误，绝不静默重试（NFR-4 / NFR-6）。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from summit_workbench.providers.feishu.config import AUTHORIZE_PATH, TOKEN_PATH, FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError

_DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True)
class TokenSet:
    """一次令牌换取/刷新的结果。access_token 与 refresh_token 以 SecretStr 承载。"""

    access_token: SecretStr
    expires_in: int
    refresh_token: SecretStr | None
    refresh_token_expires_in: int | None
    scope: str | None


def build_authorize_url(cfg: FeishuConfig, state: str) -> str:
    """构造用户授权 URL（用户在浏览器打开并同意后回调携带 code）。"""
    params = {
        "client_id": cfg.app_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope_param,
        "state": state,
        "response_type": "code",
    }
    return f"{cfg.authorize_host}{AUTHORIZE_PATH}?{urlencode(params)}"


def _default_client() -> httpx.Client:
    return httpx.Client(timeout=_DEFAULT_TIMEOUT)


def _post_token(
    cfg: FeishuConfig,
    payload: dict[str, str],
    *,
    client: httpx.Client | None,
    on_invalid_grant_reauthorize: bool,
) -> TokenSet:
    url = f"{cfg.openapi_host}{TOKEN_PATH}"
    owns_client = client is None
    http = client or _default_client()
    try:
        resp = http.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise FeishuAuthError(f"令牌端点网络错误：{type(exc).__name__}") from exc
    finally:
        if owns_client:
            http.close()

    try:
        data = resp.json()
    except ValueError as exc:
        raise FeishuAuthError(f"令牌端点返回非 JSON（HTTP {resp.status_code}）") from exc

    if "access_token" in data:
        return TokenSet(
            access_token=SecretStr(str(data["access_token"])),
            expires_in=int(data.get("expires_in", 0)),
            refresh_token=(
                SecretStr(str(data["refresh_token"])) if data.get("refresh_token") else None
            ),
            refresh_token_expires_in=data.get("refresh_token_expires_in"),
            scope=data.get("scope"),
        )

    # 失败：飞书返回 error/error_description 或 code/msg。不回显响应中的敏感字段。
    err = str(data.get("error") or data.get("code") or "unknown")
    needs_reauth = on_invalid_grant_reauthorize and err in {"invalid_grant", "invalid_request"}
    raise FeishuAuthError(
        f"令牌端点失败（HTTP {resp.status_code}，error={err}）",
        needs_reauthorize=needs_reauth,
    )


def exchange_code(
    cfg: FeishuConfig,
    app_secret: SecretStr,
    code: str,
    *,
    client: httpx.Client | None = None,
) -> TokenSet:
    """用一次性授权码换取 access_token 与 refresh_token。"""
    payload = {
        "grant_type": "authorization_code",
        "client_id": cfg.app_id,
        "client_secret": app_secret.get_secret_value(),
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    return _post_token(cfg, payload, client=client, on_invalid_grant_reauthorize=False)


def get_tenant_access_token(
    cfg: FeishuConfig,
    app_secret: SecretStr,
    *,
    client: httpx.Client | None = None,
) -> SecretStr:
    """用 app_id + app_secret 换取 tenant_access_token（应用身份，短期有效，用完即弃）。

    用于读取 tenant 侧授权的资源（会议纪要/逐字稿文档），避开用户态未授予的 scope。
    """
    url = f"{cfg.openapi_host}/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": cfg.app_id, "app_secret": app_secret.get_secret_value()}
    owns_client = client is None
    http = client or _default_client()
    try:
        resp = http.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise FeishuAuthError(f"tenant_access_token 网络错误：{type(exc).__name__}") from exc
    finally:
        if owns_client:
            http.close()

    try:
        data = resp.json()
    except ValueError as exc:
        raise FeishuAuthError(
            f"tenant_access_token 返回非 JSON（HTTP {resp.status_code}）"
        ) from exc

    token = data.get("tenant_access_token")
    if data.get("code") not in (0, None) or not token:
        raise FeishuAuthError(f"获取 tenant_access_token 失败（code={data.get('code')}）")
    return SecretStr(str(token))


def refresh_token(
    cfg: FeishuConfig,
    app_secret: SecretStr,
    current_refresh_token: SecretStr,
    *,
    client: httpx.Client | None = None,
) -> TokenSet:
    """用 refresh_token 刷新出新的 access_token（并轮换出新的 refresh_token）。

    失效时抛出 ``needs_reauthorize=True`` 的 :class:`FeishuAuthError`，提示需重新授权。
    """
    payload = {
        "grant_type": "refresh_token",
        "client_id": cfg.app_id,
        "client_secret": app_secret.get_secret_value(),
        "refresh_token": current_refresh_token.get_secret_value(),
    }
    return _post_token(cfg, payload, client=client, on_invalid_grant_reauthorize=True)
