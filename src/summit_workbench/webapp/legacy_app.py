"""面板应用装配 facade（LEGACY-APP-SPLIT-PLAN Step 16）。

只绑定回环地址。领域路由全部由 ``webapp/routers/*`` 的 ``register_*`` 提供；本模块负责
构造 ``FeishuClientPool`` / ``MutationRuntime`` / lifespan，并**按固定顺序**调用各注册
函数——顺序即 ``app.routes`` 顺序，也就是 HTTP 行为（§6-R6 / §6-R7）。

历史导入路径与兼容再导出集中保留在下方，**不得删除**（§7-7）：``WebContext``、
``_ask_html``、``_run_web_import``、``_commit_suffix``、``KNOWLEDGE_SOURCE_ROOTS``、
``SOURCE_BODY_DISPLAY_CHARS``。
"""
# ruff: noqa: E501

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request

from summit_workbench.webapp.app_shell import install_app_shell
from summit_workbench.webapp.ask_view import _ask_html as _ask_html
from summit_workbench.webapp.build_info import (
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.context import WebContext as WebContext
from summit_workbench.webapp.feishu_pool import (
    _FeishuClientPool,
)
from summit_workbench.webapp.knowledge_sources import (
    KNOWLEDGE_SOURCE_ROOTS as KNOWLEDGE_SOURCE_ROOTS,
)
from summit_workbench.webapp.knowledge_sources import (
    SOURCE_BODY_DISPLAY_CHARS as SOURCE_BODY_DISPLAY_CHARS,
)
from summit_workbench.webapp.knowledge_sources import (
    _is_knowledge_source as _is_knowledge_source,
)
from summit_workbench.webapp.meeting_import import _run_web_import as _run_web_import
from summit_workbench.webapp.mutation_runtime import (
    MutationRuntime,
)
from summit_workbench.webapp.mutation_runtime import (
    _commit_suffix as _commit_suffix,
)
from summit_workbench.webapp.request_boundary import (
    _SCHEMA_UPGRADE_WRITE_EXEMPTIONS as _SCHEMA_UPGRADE_WRITE_EXEMPTIONS,
)
from summit_workbench.webapp.request_boundary import (
    install_cache_policy,
    install_exception_handlers,
    install_security_boundary,
)
from summit_workbench.webapp.restricted_app import (
    _STATIC_DIR as _STATIC_DIR,
)
from summit_workbench.webapp.restricted_app import (
    create_restricted_app,
)
from summit_workbench.webapp.routers.ask import (
    register_ask_page_routes,
    register_ask_routes,
)
from summit_workbench.webapp.routers.brief import (
    register_brief_page_routes,
    register_brief_routes,
)
from summit_workbench.webapp.routers.capture import register_capture_routes
from summit_workbench.webapp.routers.meetings import register_meetings_routes
from summit_workbench.webapp.routers.onboarding import register_onboarding_routes
from summit_workbench.webapp.routers.review import (
    register_review_page_routes,
    register_review_routes,
)
from summit_workbench.webapp.routers.review_apply import (
    register_review_apply_page_routes,
    register_review_apply_routes,
)
from summit_workbench.webapp.routers.settings import register_settings_routes
from summit_workbench.webapp.routers.state import register_state_routes
from summit_workbench.webapp.routers.sync import register_sync_routes
from summit_workbench.webapp.routers.threads import (
    register_thread_document_routes,
    register_thread_routes,
)
from summit_workbench.webapp.routers.undo import register_undo_routes
from summit_workbench.webapp.security import (
    allowed_hosts,
    validate_bind_host,
)

_create_restricted_app = create_restricted_app

# 兼容再导出：``_SCHEMA_UPGRADE_WRITE_EXEMPTIONS`` 是只读升级态的写豁免白名单。远程
# 规范化需要它——它只改本地 origin/profile 与工作区凭据，不写 vault、不提交、不推送；
# 没有该豁免，迁移门要求 HTTPS，而只读门又挡住唯一能建立 HTTPS 的操作，形成死锁。
# ``KNOWLEDGE_SOURCE_ROOTS`` / ``SOURCE_BODY_DISPLAY_CHARS`` 见 ``webapp/knowledge_sources.py``。


def create_app(
    ctx: WebContext | None,
    *,
    static_dir: Path | None = None,
    bind_host: str = "127.0.0.1",
    port: int = 8787,
    session_token: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    server_instance: str | None = None,
) -> FastAPI:
    if ctx is None:
        context = getattr(ctx, "active_workspace", None)
        if context is None:
            from summit_workbench.config.profiles import resolve_active_workspace

            context = resolve_active_workspace(allow_env_fallback=False)
        return create_restricted_app(
            context,
            static_dir=static_dir,
            bind_host=bind_host,
            port=port,
            session_token=session_token,
            workspace_id=workspace_id,
            device_id=device_id,
            server_instance=server_instance,
        )

    feishu_clients = _FeishuClientPool(
        lock_root=ctx.lock_root,
        config_file=ctx.config_file,
        workspace_id=ctx.workspace_id,
    )
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))
    validate_bind_host(bind_host, panel_mode)
    normalized_bind_host = bind_host.strip().strip("[]").lower()
    external_bind = normalized_bind_host not in {
        "127.0.0.1",
        "::1",
    }
    host_allowlist = allowed_hosts(bind_host, port, include_test_alias=panel_mode != "production")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            feishu_clients.close()

    app = FastAPI(title="SummitWorkbench 面板", lifespan=lifespan)
    app.state.feishu_clients = feishu_clients
    spa_dir = static_dir or _STATIC_DIR
    server_instance = server_instance or new_server_instance()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _operation_id(request: Request) -> str:
        operation_id = getattr(request.state, "operation_id", None)
        return str(operation_id or "unknown")

    runtime = MutationRuntime(ctx, operation_id=_operation_id)

    install_exception_handlers(app, operation_id=_operation_id)

    install_security_boundary(
        app,
        ctx=ctx,
        port=port,
        host_allowlist=host_allowlist,
        panel_mode=panel_mode,
        external_bind=external_bind,
        session_token=session_token,
    )

    install_cache_policy(app)

    shell = install_app_shell(app, ctx, spa_dir)

    # ---- JSON API（SPA 工作台） ----

    from summit_workbench.webapp.dependencies import RouteDependencies
    from summit_workbench.webapp.routers.system import (
        register_shutdown_route,
        register_system_routes,
    )

    dependencies = RouteDependencies(app=app, context=ctx, operation_id=_operation_id)

    register_system_routes(
        dependencies,
        static_dir=spa_dir,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
        build_info=shell.build_info,
    )

    register_review_routes(dependencies, runtime=runtime)
    register_review_apply_routes(dependencies, runtime=runtime, feishu_clients=feishu_clients)
    register_thread_routes(dependencies, runtime=runtime)

    from summit_workbench.webapp.routers.projects import register_project_read_routes

    register_project_read_routes(dependencies)
    register_thread_document_routes(dependencies, runtime=runtime)
    register_capture_routes(dependencies, runtime=runtime, feishu_clients=feishu_clients)
    register_brief_routes(dependencies, runtime=runtime)
    register_ask_routes(dependencies)
    register_meetings_routes(dependencies, runtime=runtime)
    register_undo_routes(dependencies, runtime=runtime)
    register_shutdown_route(dependencies)

    # ---- SSR 兼容路由（旧入口与既有测试继续可用） ----

    register_brief_page_routes(dependencies, runtime=runtime)
    register_ask_page_routes(dependencies, dashboard=shell.dashboard)
    register_review_page_routes(dependencies, runtime=runtime)
    register_review_apply_page_routes(dependencies, runtime=runtime, feishu_clients=feishu_clients)
    register_onboarding_routes(dependencies)

    # ---- workspace schema migration（P1-02；P1-03 router 接线）----

    from summit_workbench.webapp.routers.projects import register_project_write_routes
    from summit_workbench.webapp.routers.workspace import register_workspace_routes

    register_state_routes(
        dependencies,
        runtime=runtime,
        build_info=shell.build_info,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
    )
    register_project_write_routes(
        dependencies,
        run_mutation=lambda action, mutation: runtime.run(action, mutation),
    )
    register_settings_routes(dependencies, runtime=runtime, build_info=shell.build_info)
    register_workspace_routes(dependencies)

    # ---- 多设备同步（P0-10）----

    register_sync_routes(dependencies, runtime=runtime)

    return app
    return app
