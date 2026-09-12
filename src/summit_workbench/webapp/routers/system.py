"""系统握手与本地会话路由。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

from summit_workbench.webapp.build_info import BuildInfoError, WebBuildInfo
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload
from summit_workbench.webapp.security import SESSION_COOKIE, session_token_matches


def register_system_routes(
    dependencies: RouteDependencies,
    *,
    static_dir: Path,
    server_instance: str,
    started_at: str,
    panel_mode: Any,
    session_token: str | None,
    workspace_id: str | None,
    device_id: str | None,
    build_info: Callable[[], WebBuildInfo] | None = None,
) -> None:
    """注册 version/session 协议；构建信息由 app factory 注入。"""
    app: FastAPI = dependencies.app
    context = dependencies.context
    get_build_info = build_info or (lambda: WebBuildInfo.from_static_dir(static_dir))

    @app.get("/api/version")
    def api_version(request: Request) -> JSONResponse:
        try:
            info = get_build_info()
        except BuildInfoError as exc:
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="invalid_build_manifest",
                    message=str(exc),
                    operation_id=dependencies.operation_id(request),
                ),
                headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
            )
        return JSONResponse(
            content=info.version_payload(
                server_instance=server_instance,
                started_at=started_at,
                mode=panel_mode,
                workspace_id=workspace_id or context.workspace_id,
                device_id=device_id
                or (context.active_workspace.device_id if context.active_workspace else None),
                port=getattr(app.state, "bound_port", None),
            ),
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )

    @app.get("/api/session/bootstrap", include_in_schema=False)
    def session_bootstrap(request: Request, token: str) -> Response:
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        if panel_mode == "production" or not session_token_matches(token, expected_token):
            return JSONResponse(
                status_code=401,
                content=error_payload(
                    code="authentication_required",
                    message="一次性会话令牌无效",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, path="/"
        )
        return response


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def register_restricted_system_routes(
    app: FastAPI,
    *,
    static_dir: Path | None,
    server_instance: str,
    started_at: str,
    panel_mode: Any,
    session_token: str | None,
    workspace_id: str | None,
    device_id: str | None,
) -> None:
    """注册受限（空安装）app 的握手路由（原 ``restricted_app`` 115–162）。

    与完整 app 的 ``/api/version`` / ``/api/session/bootstrap`` **刻意保留两份实现**：
    受限版没有 ``RouteDependencies``、不加 ``Cache-Control`` 头（蓝图 Step 15 明确不合并）。
    handler 函数体逐字搬运，``invalid_build_manifest`` / ``authentication_required``
    仍留在源码里（§6-R1）；``_STATIC_DIR`` 是本模块自有的打包静态资源回退目录。
    """

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def restricted_home() -> HTMLResponse:
        from summit_workbench.webapp.onboarding_view import render_onboarding_wizard

        return HTMLResponse(render_onboarding_wizard())

    @app.get("/api/version")
    def restricted_version(request: Request) -> JSONResponse:
        try:
            info = WebBuildInfo.from_static_dir(static_dir or _STATIC_DIR)
        except BuildInfoError as exc:
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="invalid_build_manifest",
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        return JSONResponse(
            info.version_payload(
                server_instance=server_instance,
                started_at=started_at,
                mode=panel_mode,
                workspace_id=workspace_id,
                device_id=device_id,
                port=getattr(app.state, "bound_port", None),
            )
        )

    @app.get("/api/session/bootstrap", include_in_schema=False)
    def restricted_session_bootstrap(request: Request, token: str) -> Response:
        if panel_mode == "production" or not session_token_matches(
            token, session_token or os.environ.get("WB_SESSION_TOKEN")
        ):
            return JSONResponse(
                status_code=401,
                content=error_payload(
                    code="authentication_required",
                    message="一次性会话令牌无效",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, path="/"
        )
        return response


def register_shutdown_route(dependencies: RouteDependencies) -> None:
    """注册面板退出路由（原 ``legacy_app`` 310–328）。"""
    app: FastAPI = dependencies.app

    @app.post("/api/shutdown")
    def api_shutdown(
        x_wb_shutdown: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """关闭本地面板（网页「退出」按钮调用）。

        只允许面板页面自身触发：自定义头 ``X-WB-Shutdown`` 会强制浏览器先发 CORS
        预检，而本应用未开启跨域，外部网页无法直发——杜绝任意网页把本地服务关掉。
        收到请求后延迟片刻让响应先返回，再从独立线程退出进程。
        """
        if x_wb_shutdown != "1":
            return {"ok": False, "message": "缺少关闭令牌"}

        def _stop() -> None:
            time.sleep(0.3)
            os._exit(0)

        threading.Thread(target=_stop, daemon=True).start()
        return {"ok": True, "message": "工作台正在关闭…"}


__all__ = ["register_restricted_system_routes", "register_shutdown_route", "register_system_routes"]
