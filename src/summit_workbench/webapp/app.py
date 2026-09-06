"""Web 应用公开兼容入口。

P1-03 起应用装配位于 :mod:`app_factory`，本模块只保留历史导入路径，避免 CLI、原生壳
和第三方脚本因模块移动失效。
"""

import os
from pathlib import Path

from fastapi import FastAPI

from summit_workbench.webapp import app_factory
from summit_workbench.webapp.app_factory import AppContext, WebContext
from summit_workbench.webapp.legacy_app import _ask_html, _run_web_import


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
    """旧导入路径兼容层；新代码应从 app_factory 导入。"""
    import summit_workbench.webapp.legacy_app as legacy_app

    legacy_app._ask_html = _ask_html
    legacy_app._run_web_import = _run_web_import
    return app_factory.create_app(
        context,
        static_dir=static_dir,
        bind_host=bind_host,
        port=port,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
        server_instance=server_instance,
    )


__all__ = ["AppContext", "WebContext", "create_app", "os"]
