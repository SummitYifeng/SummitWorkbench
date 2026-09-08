"""显式 AppContext 的兼容工厂（P1-03）。

路由实现暂由 ``legacy_app`` 承载，工厂是唯一公开的应用创建入口；调用方不再依赖
app 模块里的路由实现细节。后续路由按领域迁入 ``routers/`` 时只替换这里的注册组合。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.legacy_app import create_app as _create_legacy_app

AppContext = WebContext


def create_app(
    context: AppContext | None,
    *,
    static_dir: Path | None = None,
    bind_host: str = "127.0.0.1",
    port: int = 8787,
    session_token: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    server_instance: str | None = None,
) -> FastAPI:
    """使用冻结的显式 AppContext 创建 FastAPI 应用。"""
    application = _create_legacy_app(
        context,
        static_dir=static_dir,
        bind_host=bind_host,
        port=port,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
        server_instance=server_instance,
    )
    if context is not None:
        application.state.app_context = context
        from summit_workbench.observability.structured_logging import StructuredLogger
        from summit_workbench.webapp.dependencies import RouteDependencies
        from summit_workbench.webapp.routers.diagnostics import register_diagnostics_routes
        from summit_workbench.webapp.routers.settings import register_settings_connection_routes

        log_path = Path.home() / "Library" / "Logs" / "summitworkbench-panel.log"
        application.state.structured_logger = StructuredLogger(log_path, component="webapp")
        register_diagnostics_routes(
            RouteDependencies(
                app=application,
                context=context,
                operation_id=lambda request: str(getattr(request.state, "operation_id", "unknown")),
            ),
            static_dir=static_dir or Path(__file__).resolve().parent / "static",
            log_path=log_path,
        )
        register_settings_connection_routes(
            RouteDependencies(
                app=application,
                context=context,
                operation_id=lambda request: str(getattr(request.state, "operation_id", "unknown")),
            )
        )
    return application


__all__ = ["AppContext", "WebContext", "create_app"]
