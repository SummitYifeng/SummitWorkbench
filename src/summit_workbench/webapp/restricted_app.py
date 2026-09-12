"""受限 app 工厂：首次使用向导（onboarding）用的最小应用（LEGACY-APP-SPLIT-PLAN Step 5 / C1–C4）。

从 ``legacy_app`` 抽出的第二个 app 工厂。受限 app 只在**还没有可用工作区**时使用：它没有
compatibility 写门、没有完整 app 的路由，只承载 onboarding / 远程引导相关的接口，边界由
:func:`~summit_workbench.webapp.request_boundary.install_restricted_boundary` 与
:func:`~summit_workbench.webapp.request_boundary.install_validation_handler` 安装。

**本步只搬工厂，不拆它内部的路由**（蓝图 Step 5 的"一次只动一件事"）：路由仍以嵌套函数
形式随工厂一起搬来，等 Step 15 再按 `register_restricted_*` 拆分。

``legacy_app`` 保留 ``_create_restricted_app = create_restricted_app`` 别名，调用点不变。
"""

# ruff: noqa: E501

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Body, FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from starlette.responses import Response

if TYPE_CHECKING:
    pass

from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.domain.workspace import DeviceRole
from summit_workbench.webapp.api import (
    OnboardingCreatePayload,
    OnboardingDraftPayload,
    OnboardingPreflightPayload,
    OnboardingRemoteConfirmPayload,
    OnboardingRemoteStagePayload,
    OnboardingVaultPayload,
)
from summit_workbench.webapp.build_info import (
    BuildInfoError,
    WebBuildInfo,
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
    install_validation_handler,
)
from summit_workbench.webapp.security import (
    SESSION_COOKIE,
    allowed_hosts,
    error_payload,
    session_token_matches,
    validate_bind_host,
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    remote_stages: dict[str, object] = {}

    install_validation_handler(
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

    from summit_workbench.config.profiles import resolve_workspace
    from summit_workbench.domain.onboarding import OnboardingFlow
    from summit_workbench.workflows import onboarding as onboarding_service

    def _rejected(request: Request, exc: onboarding_service.OnboardingError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="onboarding_rejected",
                message=str(exc),
                operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                details={"reasons": exc.reasons},
            ),
        )

    @app.get("/api/onboarding/status", response_model=None)
    def restricted_onboarding_status() -> dict[str, object]:
        resolution = resolve_workspace(allow_env_fallback=False)
        return {
            "ok": True,
            "state": resolution.state.value,
            "workspace_id": resolution.profile.workspace_id if resolution.profile else None,
            "reason": resolution.reason,
        }

    @app.get("/api/onboarding/draft", response_model=None)
    def restricted_draft() -> dict[str, object]:
        from summit_workbench.repositories.onboarding_draft import load_onboarding_draft

        draft = load_onboarding_draft(home=active_workspace.home)
        return {"ok": True, "draft": draft.model_dump(mode="json") if draft else None}

    @app.put("/api/onboarding/draft", response_model=None)
    def restricted_save_draft(
        request: Request, payload: Annotated[OnboardingDraftPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.repositories.onboarding_draft import (
            OnboardingDraft,
            save_onboarding_draft,
        )

        try:
            draft = OnboardingDraft.model_validate(payload.model_dump())
            path = save_onboarding_draft(draft, home=active_workspace.home)
        except (OSError, ValueError):
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="onboarding_draft_failed",
                    message="向导进度暂时无法保存",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        return {"ok": True, "step": draft.step, "path": str(path)}

    @app.delete("/api/onboarding/draft", response_model=None)
    def restricted_clear_draft() -> dict[str, object]:
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True}

    @app.post("/api/onboarding/remote/stage", response_model=None)
    def restricted_remote_stage(
        request: Request, payload: Annotated[OnboardingRemoteStagePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from uuid import uuid4

        from summit_workbench.workflows.remote_onboarding import (
            RemoteCloneError,
            stage_remote_clone,
        )

        credential_resolver = None
        if payload.pat:
            from pydantic import SecretStr

            from summit_workbench.config.git_credentials import GitCredentials

            pat = SecretStr(payload.pat)

            def resolve(_ws: str, host: str, _username: str) -> GitCredentials:
                return GitCredentials(_ws, host, payload.git_username, pat)

            credential_resolver = resolve

        try:
            staged = stage_remote_clone(
                payload.remote_url,
                Path(payload.target_vault).expanduser(),
                workspace_id=payload.expected_workspace_id,
                username=payload.git_username,
                home=active_workspace.home,
                credential_resolver=credential_resolver,
            )
        except RemoteCloneError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code,
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                    details={"reasons": exc.reasons},
                ),
            )
        stage_id = str(uuid4())
        remote_stages[stage_id] = staged
        return {
            "ok": True,
            "stage_id": stage_id,
            "workspace_id": staged.workspace_id,
            "remote_url": staged.remote_url,
            "compatibility": staged.compatibility.value,
        }

    @app.post("/api/onboarding/remote/confirm", response_model=None)
    def restricted_remote_confirm(
        request: Request, payload: Annotated[OnboardingRemoteConfirmPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.remote_onboarding import (
            RemoteCloneError,
            confirm_remote_clone,
        )

        staged = remote_stages.get(payload.stage_id)
        if staged is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="staging_missing",
                    message="连接准备已失效，请重新开始",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        try:
            result = confirm_remote_clone(
                staged,  # type: ignore[arg-type]
                home=active_workspace.home,
                display_name=payload.display_name,
                device_name=payload.device_name,
                user_email=payload.user_email,
            )
            if payload.pat:
                from urllib.parse import urlsplit

                from pydantic import SecretStr

                from summit_workbench.config.git_credentials import store_git_credentials
                from summit_workbench.workflows.remote_onboarding import RemoteCloneStage

                staged_info = cast(RemoteCloneStage, staged)
                host = urlsplit(staged_info.remote_url).hostname or ""
                store_git_credentials(
                    staged_info.workspace_id, host, staged_info.username, SecretStr(payload.pat)
                )
        except RemoteCloneError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code,
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        remote_stages.pop(payload.stage_id, None)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/remote/cancel", response_model=None)
    def restricted_remote_cancel(
        request: Request, payload: Annotated[OnboardingRemoteConfirmPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.remote_onboarding import cancel_remote_clone

        staged = remote_stages.pop(payload.stage_id, None)
        if staged is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="staging_missing",
                    message="连接准备已失效",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        cancel_remote_clone(staged)  # type: ignore[arg-type]
        return {"ok": True}

    @app.post("/api/onboarding/preflight", response_model=None)
    def restricted_preflight(
        request: Request, payload: Annotated[OnboardingPreflightPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            report = onboarding_service.preflight(
                OnboardingFlow(payload.flow),
                Path(payload.path).expanduser(),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        return {"ok": True, "report": report.model_dump(mode="json")}

    @app.post("/api/onboarding/create", response_model=None)
    def restricted_create(
        request: Request, payload: Annotated[OnboardingCreatePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.create_workspace(
                Path(payload.work_root).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/upgrade", response_model=None)
    def restricted_upgrade(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.upgrade_workspace(
                Path(payload.vault_dir).expanduser(),
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/connect", response_model=None)
    def restricted_connect(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.connect_workspace(
                Path(payload.vault_dir).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    from summit_workbench.webapp.routers.settings import register_restricted_connection_routes

    register_restricted_connection_routes(
        app,
        active_workspace=active_workspace,
        operation_id=lambda request: request.headers.get("x-wb-operation-id", "unknown"),
    )

    return app
