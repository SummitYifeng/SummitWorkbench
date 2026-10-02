"""受限 app 工厂：首次使用向导（onboarding）用的最小应用（LEGACY-APP-SPLIT-PLAN Step 5 / C1–C4）。

从 ``legacy_app`` 抽出的第二个 app 工厂。受限 app 只在**还没有可用工作区**时使用：它没有
compatibility 写门、没有完整 app 的路由，只承载 onboarding 与账户连接接口，边界由
:func:`~summit_workbench.webapp.request_boundary.install_restricted_boundary` 与
:func:`~summit_workbench.webapp.request_boundary.install_validation_handler` 安装。

Step 15 已按 ``register_restricted_*`` 把路由拆走：握手三件套（``/``、``/api/version``、
``/api/session/bootstrap``）在 ``routers/system.py``，11 条 onboarding 路由在
``routers/onboarding.py``，连接路由仍由 ``routers/settings.py`` 提供。本模块现在只剩
「构造 app + 装边界 + 按原顺序调用 register 函数」，路由注册点与拆分前逐点对应，
因此受限 app 的 ``app.routes`` 顺序保持不变。

``legacy_app`` 保留 ``_create_restricted_app = create_restricted_app`` 别名，调用点不变。
"""

# ruff: noqa: E501

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    pass

from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.webapp.build_info import (
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.context import WebContext as WebContext
from summit_workbench.webapp.knowledge_sources import (
    KNOWLEDGE_SOURCE_ROOTS as KNOWLEDGE_SOURCE_ROOTS,
)
from summit_workbench.webapp.knowledge_sources import (
    SOURCE_BODY_DISPLAY_CHARS as SOURCE_BODY_DISPLAY_CHARS,
)
from summit_workbench.webapp.mutation_runtime import (
    _commit_suffix as _commit_suffix,
)
from summit_workbench.webapp.request_boundary import (
    _SCHEMA_UPGRADE_WRITE_EXEMPTIONS as _SCHEMA_UPGRADE_WRITE_EXEMPTIONS,
)
from summit_workbench.webapp.request_boundary import (
    install_restricted_boundary,
    install_unexpected_handler,
    install_validation_handler,
)
from summit_workbench.webapp.routers.onboarding import (
    register_restricted_onboarding_routes,
)
from summit_workbench.webapp.routers.system import (
    _STATIC_DIR as _STATIC_DIR,
)
from summit_workbench.webapp.routers.system import register_restricted_system_routes
from summit_workbench.webapp.security import (
    allowed_hosts,
    validate_bind_host,
)


def create_restricted_app(
    active_workspace: ActiveWorkspaceContext,
    *,
    static_dir: Path | None = None,
    bind_host: str = "127.0.0.1",
    port: int = 8787,
    session_token: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    server_instance: str | None = None,
) -> FastAPI:
    """Create the empty-install control plane without constructing a vault context."""
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))
    validate_bind_host(bind_host, panel_mode)
    normalized_bind_host = bind_host.strip().strip("[]").lower()
    external_bind = normalized_bind_host not in {"127.0.0.1", "::1"}
    host_allowlist = allowed_hosts(bind_host, port, include_test_alias=panel_mode != "production")
    server_instance = server_instance or new_server_instance()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    app = FastAPI(title="SummitWorkbench onboarding", lifespan=None)
    app.state.active_workspace_context = active_workspace

    install_validation_handler(
        app,
        operation_id=lambda request: request.headers.get("x-wb-operation-id", "unknown"),
    )
    # 受限 app 也要兜底：首启向导的未预期异常不能变成非 JSON 响应（2026-09-14 Air 实测踩到）。
    install_unexpected_handler(
        app,
        operation_id=lambda request: request.headers.get("x-wb-operation-id", "unknown"),
    )

    install_restricted_boundary(
        app,
        port=port,
        host_allowlist=host_allowlist,
        panel_mode=panel_mode,
        external_bind=external_bind,
        session_token=session_token,
    )

    register_restricted_system_routes(
        app,
        static_dir=static_dir,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
    )

    register_restricted_onboarding_routes(app, active_workspace=active_workspace)

    from summit_workbench.webapp.routers.settings import register_restricted_connection_routes

    register_restricted_connection_routes(
        app,
        active_workspace=active_workspace,
        operation_id=lambda request: request.headers.get("x-wb-operation-id", "unknown"),
    )

    return app
