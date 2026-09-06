"""系统握手与本地会话路由。"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
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


__all__ = ["register_system_routes"]
