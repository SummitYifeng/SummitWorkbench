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

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from summit_workbench.providers._resilient import (
    RetryMode,
    build_client,
    parse_retry_after,
    send_with_retry,
)
from summit_workbench.providers.feishu.config import AUTHORIZE_PATH, TOKEN_PATH, FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError

_DEFAULT_TIMEOUT = 15.0
_MAX_RETRIES = 3  # 保留统一退避配置接口；token POST 当前 RetryMode.NEVER 不重试


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
    return build_client(_DEFAULT_TIMEOUT)


def _post_json(
    http: httpx.Client,
    url: str,
    payload: dict[str, Any],
    what: str,
    *,
    sleep: Callable[[float], None],
) -> httpx.Response:
    """POST 一次 token 端点；返回 HTTP 2xx/4xx 响应交由调用方解析信封。

    token 端点是非幂等 POST，瞬时网络失败也不自动重放；调用方通过
    ``FeishuAuthError.result_unknown`` 得到结果不确定的机器状态。
    """

    def attempt(_n: int) -> httpx.Response:
        try:
            resp = http.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise FeishuAuthError(f"{what}请求超时", result_unknown=True) from exc
        except httpx.HTTPError as exc:
            raise FeishuAuthError(
                f"{what}网络错误：{type(exc).__name__}", result_unknown=True
            ) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise FeishuAuthError(
                f"{what}服务暂时不可用（HTTP {resp.status_code}）",
                retry_after=parse_retry_after(resp),
                result_unknown=True,
            )
        return resp

    return send_with_retry(
        attempt,
        retry_on=(FeishuAuthError,),
        is_retryable=lambda exc: isinstance(exc, FeishuAuthError) and exc.retryable,
        retry_after=lambda exc: getattr(exc, "retry_after", None),
        max_retries=_MAX_RETRIES,
        sleep=sleep,
        retry_mode=RetryMode.NEVER,
    )


# 令牌端点失败码 → 面向用户的可执行提示。
#
# 分发包内置了应用凭据，同事本机没有任何可改的配置，因此失败时必须由这句话给出
# 「去找谁、做什么」；最常见的真实失败是管理员还没把该同事加入应用「可用范围」。
# 键既覆盖 OAuth 风格字符串错误（invalid_grant 等），也覆盖飞书数字码。
_TOKEN_FAILURE_HINTS: dict[str, str] = {
    "invalid_client": "内置的应用凭据无效（可能已轮换）：请联系管理员重新发布安装包",
    "20002": "内置的应用凭据无效（可能已轮换）：请联系管理员重新发布安装包",
    "invalid_grant": "授权码无效或已过期（只能用一次、有效期 5 分钟）：请重新点一次「授权飞书」",
    "20003": "授权码无效或已过期（只能用一次、有效期 5 分钟）：请重新点一次「授权飞书」",
    "20004": "授权码已过期：请重新点一次「授权飞书」",
    "20065": "授权码已被使用过：请重新点一次「授权飞书」",
    "20010": "你的账号还没有这个应用的使用权限：请联系管理员把你加入应用「可用范围」",
    "20009": "应用尚未在你们的飞书里安装：请联系管理员在开放平台启用应用",
    "20069": "应用未启用：请联系管理员在飞书开放平台启用应用",
    "20048": "应用不存在：请联系管理员核对应用状态",
    "20024": "授权码与本应用不匹配：请联系管理员核对应用凭据",
    "20071": "回调地址与发起授权时不一致：请联系管理员核对开放平台的「重定向 URL」",
    "20049": "PKCE 校验失败（本产品未启用 PKCE）：请联系管理员",
}

# 这些失败都表示「当前 grant 已不可用」，重新授权是唯一正确的用户动作。
_REAUTHORIZE_ERRORS = frozenset({"invalid_grant", "invalid_request", "20003", "20004", "20065"})


def token_failure_message(*, error: object, code: object, status: int) -> str:
    """把令牌端点的失败信封翻成一句可执行的中文提示，并保留原始错误码。

    绝不回显请求或响应中可能的敏感字段（凭据、授权码）。
    """
    if error not in (None, ""):
        raw = str(error)
    elif code not in (None, ""):
        raw = str(code)
    else:
        raw = "unknown"
    hint = _TOKEN_FAILURE_HINTS.get(str(code)) or _TOKEN_FAILURE_HINTS.get(str(error))
    if hint:
        return f"令牌端点失败（HTTP {status}，错误码 {raw}）：{hint}"
    return f"令牌端点失败（HTTP {status}，错误码 {raw}）"


def _post_token(
    cfg: FeishuConfig,
    payload: dict[str, str],
    *,
    client: httpx.Client | None,
    on_invalid_grant_reauthorize: bool,
    sleep: Callable[[float], None] = time.sleep,
) -> TokenSet:
    url = f"{cfg.openapi_host}{TOKEN_PATH}"
    owns_client = client is None
    http = client or _default_client()
    try:
        resp = _post_json(http, url, payload, "令牌端点", sleep=sleep)
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

    # 失败：飞书返回 error/error_description 或 code/msg。不回显响应中的敏感字段，
    # 但把失败码翻成一句可执行提示（同事本机没有可改的配置，只能靠这句话自救）。
    err = str(data.get("error") or data.get("code") or "unknown")
    needs_reauth = on_invalid_grant_reauthorize and err in _REAUTHORIZE_ERRORS
    raise FeishuAuthError(
        token_failure_message(
            error=data.get("error"), code=data.get("code"), status=resp.status_code
        ),
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
        resp = _post_json(http, url, payload, "tenant_access_token", sleep=time.sleep)
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
