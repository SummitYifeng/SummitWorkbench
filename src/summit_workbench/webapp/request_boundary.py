"""请求边界：异常处理器、安全边界与缓存策略（LEGACY-APP-SPLIT-PLAN Step 4 / D2+D3+D4）。

从 ``legacy_app`` 抽出的请求入口层。有三种安装函数，**调用顺序就是 HTTP 行为**：

1. :func:`install_exception_handlers` —— 统一 error envelope（validation / http /
   sync_diverged / internal_error）；
2. :func:`install_security_boundary` —— host 白名单 → compatibility 写门 → origin →
   会话令牌；**必须先于** 缓存策略安装，见下；
3. :func:`install_cache_policy` —— `/api/version`、`/`、`build-meta.json` no-store，
   `/static/assets/` immutable。

**顺序为什么不能调换**：`@app.middleware("http")` 走 ``user_middleware.insert(0, …)``，
build 时 ``reversed(middleware)`` ⇒ **后注册者在最外层**。当前安全边界在内、缓存策略在外，
因此被安全边界拒绝的响应（如 Host 不在白名单）**仍会带上 ``Cache-Control``**。调换两者
会改变 HTTP 行为而多数测试只断言状态码；`tests/unit/test_request_boundary_order.py`
把顺序冻结成断言，本步必须让它保持绿色。

受限 app（首次使用向导）只安装**校验错误处理器**与 :func:`install_restricted_boundary`
——它没有 compatibility 写门，会话校验与 origin 校验在同一分支内，且 operation id 取自
请求头而非 request.state。两者**不合并**（那是行为变化）。
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from summit_workbench.config.locking import LockBusy
from summit_workbench.config.paths import UserPathError
from summit_workbench.domain.workspace import Compatibility
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.security import (
    SESSION_COOKIE,
    SESSION_HEADER,
    error_payload,
    origin_matches,
    session_token_matches,
)
from summit_workbench.workflows.local_mutation import MutationBlocked, MutationInvariantError

# 工作区 schema 升级期间仍需放行的写接口（服务写门白名单）。原在 legacy_app 模块级，
# 本步随之搬来并在 ``legacy_app`` 再导出，保持既有 import 契约不变。
_SCHEMA_UPGRADE_WRITE_EXEMPTIONS = frozenset(
    {
        "/api/settings/git/remote/preview",
        "/api/settings/git/remote/apply",
        "/api/settings/git/remote/rollback",
        "/api/settings/acceptance-preflight",
    }
)


def install_validation_handler(app: FastAPI, *, operation_id: Callable[[Request], str]) -> None:
    """422 校验错误 + 使用者路径解析错误（**受限 app 用的就是这两个**）。

    为什么把 :class:`UserPathError` 也放在这里：首启向导跑的就是**受限 app**，而它此前
    **只有 422 处理器**。2026-09-14 在 Air 上实测：使用者在「目标文件夹」里填了 ``~用户名``
    而该用户不存在 → ``Path.expanduser()`` 抛 ``RuntimeError`` → 没有任何处理器接住 →
    向导只拿到一个非 JSON 响应，界面显示成 WebKit 的
    「The string did not match the expected pattern.」，**真实原因完全不可见**。
    """

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(error.get("loc", ())), "msg": str(error.get("msg", "输入无效"))}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="validation_error",
                message="请求参数不符合接口约束",
                operation_id=operation_id(request),
                details=details,
            ),
        )

    install_user_path_handler(app, operation_id=operation_id)


def install_user_path_handler(app: FastAPI, *, operation_id: Callable[[Request], str]) -> None:
    """``UserPathError`` → **400**，文案直接来自异常（本就是写给使用者看的）。"""

    @app.exception_handler(UserPathError)
    async def _user_path_error(request: Request, exc: UserPathError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_payload(
                code="invalid_path",
                message=str(exc),
                operation_id=operation_id(request),
            ),
        )


def install_unexpected_handler(app: FastAPI, *, operation_id: Callable[[Request], str]) -> None:
    """兜底 500（JSON）。**受限 app 也必须装**——否则未预期异常会变成不可读的响应。"""

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="internal_error",
                message="服务内部错误，请稍后重试",
                operation_id=operation_id(request),
            ),
        )


def install_exception_handlers(app: FastAPI, *, operation_id: Callable[[Request], str]) -> None:
    """完整 app 的异常处理器：422 / HTTPException / MutationBlocked / 兜底 500。"""
    install_validation_handler(app, operation_id=operation_id)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        code = "http_error"
        message = str(detail)
        details: object | None = None
        if isinstance(detail, dict):
            code = str(detail.get("code", code))
            message = str(detail.get("message", message))
            details = detail.get("details")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=message,
                operation_id=operation_id(request),
                details=details,
            ),
        )

    @app.exception_handler(MutationBlocked)
    async def _mutation_blocked_error(request: Request, exc: MutationBlocked) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="workspace_switch_in_progress",
                message=str(exc),
                operation_id=operation_id(request),
            ),
        )

    @app.exception_handler(MutationInvariantError)
    async def _mutation_invariant_error(
        request: Request, exc: MutationInvariantError
    ) -> JSONResponse:
        details = {
            "committed": exc.committed,
            "commit_sha": exc.commit_sha,
            "paths": list(exc.paths),
        }
        message = str(exc)
        if exc.committed:
            message += "（写入已提交，请勿重复执行）"
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="mutation_invariant",
                message=message,
                operation_id=operation_id(request),
                details=details,
            ),
        )

    @app.exception_handler(LockBusy)
    async def _lock_busy_error(request: Request, _exc: LockBusy) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="workspace_busy",
                message="工作区正被另一个操作使用，请稍后重试",
                operation_id=operation_id(request),
            ),
        )

    install_unexpected_handler(app, operation_id=operation_id)


def install_security_boundary(
    app: FastAPI,
    *,
    ctx: WebContext,
    port: int,
    host_allowlist: set[str],
    panel_mode: str,
    external_bind: bool,
    session_token: str | None,
) -> None:
    """完整 app 的安全边界：host → compatibility 写门 → origin → 会话令牌。"""

    @app.middleware("http")
    async def _security_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from uuid import uuid4

        operation_id = str(uuid4())
        request.state.operation_id = operation_id
        host = request.headers.get("host", "").lower()
        dynamic_loopback_host = (
            port == 0
            and (host.startswith("127.0.0.1:") or host.startswith("localhost:"))
            and host.rsplit(":", 1)[-1].isdigit()
        )
        if host not in host_allowlist and not dynamic_loopback_host:
            return JSONResponse(
                status_code=403,
                content=error_payload(
                    code="host_not_allowed",
                    message="请求 Host 不属于当前本地服务",
                    operation_id=operation_id,
                ),
            )
        session_required = panel_mode == "production" or external_bind or session_token is not None
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        supplied_token = request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER)
        if request.method in {"POST", "PATCH", "DELETE"} or (
            request.url.path.startswith("/api/")
            and session_required
            and request.url.path != "/api/session/bootstrap"
        ):
            if (
                request.method in {"POST", "PATCH", "DELETE"}
                and ctx.compatibility is Compatibility.CANNOT_OPEN
                and not request.url.path.startswith("/api/onboarding")
                and request.url.path != "/api/workspace/migration"
            ):
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        code="workspace_not_found",
                        message="当前工作区无法打开，请升级或重新连接工作区",
                        operation_id=operation_id,
                    ),
                )
            if (
                request.method in {"POST", "PATCH", "DELETE"}
                and ctx.compatibility is Compatibility.READ_ONLY_UPGRADE_REQUIRED
                and not request.url.path.startswith("/api/onboarding")
                and request.url.path != "/api/workspace/migration"
                and request.url.path not in _SCHEMA_UPGRADE_WRITE_EXEMPTIONS
            ):
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        code="workspace_read_only_upgrade_required",
                        message="当前工作区需要升级后才能写入",
                        operation_id=operation_id,
                    ),
                )
            origin = request.headers.get("origin")
            origin_hosts = {host} if dynamic_loopback_host else host_allowlist
            if origin is not None and not origin_matches(origin, request.url.scheme, origin_hosts):
                return JSONResponse(
                    status_code=403,
                    content=error_payload(
                        code="origin_not_allowed",
                        message="请求来源不是当前服务同源地址",
                        operation_id=operation_id,
                    ),
                )
            if session_required:
                if not session_token_matches(supplied_token, expected_token):
                    return JSONResponse(
                        status_code=401,
                        content=error_payload(
                            code="authentication_required",
                            message="写请求需要本地会话令牌",
                            operation_id=operation_id,
                        ),
                    )
        response = await call_next(request)
        response.headers["X-WB-Operation-ID"] = operation_id
        return response


def install_cache_policy(app: FastAPI) -> None:
    """缓存策略：构建身份与首页不缓存、静态资源 immutable。**必须在安全边界之后安装**。"""

    @app.middleware("http")
    async def _cache_policy(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path == "/api/version":
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif path == "/" or path == "/static/build-meta.json":
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/static/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def install_restricted_boundary(
    app: FastAPI,
    *,
    port: int,
    host_allowlist: set[str],
    panel_mode: str,
    external_bind: bool,
    session_token: str | None,
) -> None:
    """受限 app 的边界：host → origin → 会话令牌（无 compatibility 写门）。"""

    @app.middleware("http")
    async def _restricted_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from uuid import uuid4

        operation_id = str(uuid4())
        host = request.headers.get("host", "").lower()
        dynamic_loopback_host = (
            port == 0
            and (host.startswith("127.0.0.1:") or host.startswith("localhost:"))
            and host.rsplit(":", 1)[-1].isdigit()
        )
        if host not in host_allowlist and not dynamic_loopback_host:
            return JSONResponse(
                status_code=403,
                content=error_payload(
                    code="host_not_allowed",
                    message="请求 Host 不属于当前本地服务",
                    operation_id=operation_id,
                ),
            )
        session_required = panel_mode == "production" or external_bind or session_token is not None
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        supplied_token = request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER)
        if request.method in {"POST", "PATCH", "DELETE"} or (
            request.url.path.startswith("/api/")
            and session_required
            and request.url.path != "/api/session/bootstrap"
        ):
            origin = request.headers.get("origin")
            origin_hosts = {host} if dynamic_loopback_host else host_allowlist
            if origin is not None and not origin_matches(origin, request.url.scheme, origin_hosts):
                return JSONResponse(
                    status_code=403,
                    content=error_payload(
                        code="origin_not_allowed",
                        message="请求来源不是当前服务同源地址",
                        operation_id=operation_id,
                    ),
                )
            if session_required and not session_token_matches(supplied_token, expected_token):
                return JSONResponse(
                    status_code=401,
                    content=error_payload(
                        code="authentication_required",
                        message="写请求需要本地会话令牌",
                        operation_id=operation_id,
                    ),
                )
        response = await call_next(request)
        response.headers["X-WB-Operation-ID"] = operation_id
        return response
