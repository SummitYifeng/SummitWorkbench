"""本地 Web 服务的绑定、Host、Origin 与会话边界（P0-05）。"""

from __future__ import annotations

import ipaddress
import os
import warnings
from urllib.parse import urlsplit

from summit_workbench.webapp.build_info import BuildMode

LOOPBACK_BIND_HOSTS = {"127.0.0.1", "::1"}
SESSION_HEADER = "X-WB-Session-Token"
SESSION_COOKIE = "wb_session"


def validate_bind_host(host: str, mode: BuildMode) -> None:
    """校验启动绑定地址；production 只接受计划约定的两个 loopback 地址。"""
    normalized = host.strip().strip("[]")
    if normalized in LOOPBACK_BIND_HOSTS:
        return
    if mode == "production":
        raise ValueError("production 模式只允许绑定 loopback：127.0.0.1 或 ::1")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    warnings.warn(
        "development 模式开放到非 loopback 地址；unsafe 请求仍要求会话认证",
        UserWarning,
        stacklevel=2,
    )


def allowed_hosts(bind_host: str, port: int, *, include_test_alias: bool = True) -> set[str]:
    """生成当前绑定地址与端口的 Host allowlist。

    ``testserver`` 仅供 development 的进程内 TestClient 使用；production 不接受它，
    避免测试别名成为绕过实际 loopback/端口边界的入口。
    """
    normalized = bind_host.strip().strip("[]").lower()
    hosts: set[str] = set()
    if include_test_alias:
        hosts.update({"testserver", f"testserver:{port}"})
    if normalized == "127.0.0.1":
        hosts.update({f"127.0.0.1:{port}", f"localhost:{port}"})
    elif normalized == "::1":
        hosts.update({f"[::1]:{port}", f"::1:{port}"})
    else:
        host = f"[{normalized}]:{port}" if ":" in normalized else f"{normalized}:{port}"
        hosts.add(host)
    return hosts


def origin_matches(origin: str, scheme: str, hosts: set[str]) -> bool:
    parsed = urlsplit(origin)
    return parsed.scheme == scheme and bool(parsed.netloc) and parsed.netloc.lower() in hosts


def session_token_matches(value: str | None, expected: str | None = None) -> bool:
    expected = expected if expected is not None else os.environ.get("WB_SESSION_TOKEN")
    return bool(expected and value and value == expected)


def error_payload(
    *,
    code: str,
    message: str,
    operation_id: str,
    details: object | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": False,
        "code": code,
        "message": message,
        "operation_id": operation_id,
    }
    if details is not None:
        payload["details"] = details
    return payload
