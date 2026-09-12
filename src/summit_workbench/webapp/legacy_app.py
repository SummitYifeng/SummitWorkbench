"""本地面板的 FastAPI 应用（只绑定回环地址，服务端渲染 + JSON API）。

领域逻辑全部复用 repositories/workflows：审批读页用 parse_review_page、改条目用
review_edit、应用用 apply_meeting_review；看板状态用 build_status、简报/复盘/问答用
各自 runner。Web 层只做路由与 HTML/JSON。

两种前端形态（同一套 API）：
- 构建了 webapp/static/index.html（npm run build 产物）时，/ 服务 SPA 工作台，
  交互走 /api/* JSON 端点；
- 未构建时回退为服务端渲染看板（views.render_dashboard），保证 wb web 永远可用。
"""
# ruff: noqa: E501

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
)
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    pass

from summit_workbench.observability.status import build_status
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.webapp.ask_view import _ask_html as _ask_html
from summit_workbench.webapp.build_info import (
    WebBuildInfo,
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
from summit_workbench.webapp.views import render_dashboard

_create_restricted_app = create_restricted_app

# Remote normalization is the controlled escape hatch that lets an old-schema
# workspace become migratable.  It only changes the local origin/profile and
# workspace-scoped credential after a temporary-clone validation; it does not
# write vault content, create commits, or push.  Without this exemption the
# migration gate requires HTTPS while the read-only gate prevents the only
# operation that can establish HTTPS (a deadlock).


# Step 1（LEGACY-APP-SPLIT-PLAN）：知识来源白名单与正文展示预算已抽到
# ``webapp/knowledge_sources.py``，并在文件顶部再导出（见那里的注释）。


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

    def _build_info() -> WebBuildInfo:
        return WebBuildInfo.from_static_dir(spa_dir)

    install_cache_policy(app)

    def _dashboard(
        msg: str | None = None, ask_q: str = "", ask_html: str | None = None
    ) -> HTMLResponse:
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=ctx.provider_config_file())
        brief_md = read_brief_block(ctx.vault_dir, day)
        return HTMLResponse(
            render_dashboard(
                status,
                day,
                brief_md,
                ask_question=ask_q,
                ask_answer_html=ask_html,
                message=msg,
            )
        )

    # ---- 首页：SPA（已构建）或 SSR 回退 ----
    spa_index = spa_dir / "index.html"
    if spa_index.is_file():
        app.mount("/static", StaticFiles(directory=str(spa_dir)), name="static")

        @app.get("/", response_class=FileResponse, include_in_schema=False)
        def spa_home() -> FileResponse:
            return FileResponse(spa_index)

    else:

        @app.get("/", response_class=HTMLResponse)
        def home(msg: str | None = None) -> HTMLResponse:
            return _dashboard(msg=msg)

    # ---- JSON API（SPA 工作台） ----

    from summit_workbench.webapp.dependencies import RouteDependencies
    from summit_workbench.webapp.routers.system import (
        register_shutdown_route,
        register_system_routes,
    )

    register_system_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        static_dir=spa_dir,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
        build_info=_build_info,
    )

    register_review_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_review_apply_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        feishu_clients=feishu_clients,
    )

    register_thread_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    from summit_workbench.webapp.routers.projects import register_project_read_routes

    register_project_read_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id)
    )

    register_thread_document_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_capture_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        feishu_clients=feishu_clients,
    )

    register_brief_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_ask_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
    )

    register_meetings_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_undo_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_shutdown_route(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
    )

    # ---- SSR 兼容路由（旧入口与既有测试继续可用） ----

    register_brief_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_ask_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        dashboard=_dashboard,
    )

    register_review_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_review_apply_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        feishu_clients=feishu_clients,
    )

    register_onboarding_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
    )

    # ---- workspace schema migration（P1-02；P1-03 router 接线）----

    from summit_workbench.webapp.routers.workspace import register_workspace_routes

    register_state_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        build_info=_build_info,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
    )
    from summit_workbench.webapp.routers.projects import register_project_write_routes

    register_project_write_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        run_mutation=lambda action, mutation: runtime.run(action, mutation),
    )

    register_settings_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        build_info=_build_info,
    )
    register_workspace_routes(RouteDependencies(app=app, context=ctx, operation_id=_operation_id))

    # ---- 多设备同步（P0-10）----

    register_sync_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    return app
