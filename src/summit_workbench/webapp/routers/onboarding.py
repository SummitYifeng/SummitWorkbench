"""onboarding 路由（LEGACY-APP-SPLIT-PLAN Step 15 / R3）。

同时承载两套向导接口：

- ``register_onboarding_routes``：完整 app 的 5 条 ``/api/onboarding/*`` 路由；
- ``register_restricted_onboarding_routes``：受限（空安装）app 的 11 条路由
  （status / draft / remote stage|confirm|cancel / preflight / create / upgrade / connect）。

受限侧的暂存表 ``remote_stages`` 在 ``register_restricted_onboarding_routes`` **函数体内**
创建，保持 per-app 语义（§6-R8），严禁提升为模块级可变对象。

两套 ``onboarding_rejected`` envelope helper 都嵌套在各自的 register 函数里，使 handler
的调用点与函数体逐字不变（§6-R1）；payload 模型全部模块顶层 import（§6-R2）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from summit_workbench.config.paths import resolve_user_path
from summit_workbench.config.profiles import ActiveWorkspaceContext, resolve_workspace
from summit_workbench.domain.onboarding import OnboardingFlow
from summit_workbench.webapp.api import (
    OnboardingCreatePayload,
    OnboardingDraftPayload,
    OnboardingPreflightPayload,
    OnboardingVaultPayload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.security import error_payload
from summit_workbench.workflows import onboarding as onboarding_service


def register_onboarding_routes(dependencies: RouteDependencies) -> None:
    """注册完整 app 的 onboarding API（原 ``legacy_app`` 353–457）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context
    _operation_id = dependencies.operation_id

    def _onboarding_rejected(
        request: Request, exc: onboarding_service.OnboardingError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="onboarding_rejected",
                message=str(exc),
                operation_id=_operation_id(request),
                details={"reasons": exc.reasons},
            ),
        )

    @app.get("/api/onboarding/status", response_model=None)
    def api_onboarding_status() -> dict[str, object]:
        """当前 workspace 解析状态：active / env-compat / onboarding-required。"""
        from summit_workbench.config.profiles import resolve_workspace

        resolution = resolve_workspace()
        return {
            "ok": True,
            "state": resolution.state.value,
            "workspace_id": resolution.profile.workspace_id if resolution.profile else None,
            "reason": resolution.reason,
        }

    @app.post("/api/onboarding/preflight", response_model=None)
    def api_onboarding_preflight(
        request: Request, payload: Annotated[OnboardingPreflightPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """只读预演：返回结构化预检报告（不写任何文件）。"""
        try:
            report = onboarding_service.preflight(
                OnboardingFlow(payload.flow),
                resolve_user_path(payload.path),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        return {"ok": True, "report": report.model_dump(mode="json")}

    @app.post("/api/onboarding/create", response_model=None)
    def api_onboarding_create(
        request: Request, payload: Annotated[OnboardingCreatePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """create-new：全新工作区（staging + 原子改名 + marker + profile，失败回滚）。"""
        try:
            result = onboarding_service.create_workspace(
                resolve_user_path(payload.work_root),
                display_name=payload.display_name,
                device_name=payload.device_name,
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/connect", response_model=None)
    def api_onboarding_connect(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """connect-local：连接已 clone/拷贝的带 marker vault（建档 + 置 active）。"""
        try:
            result = onboarding_service.connect_workspace(
                resolve_user_path(payload.vault_dir),
                display_name=payload.display_name,
                device_name=payload.device_name,
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}


def register_restricted_onboarding_routes(
    app: FastAPI, *, active_workspace: ActiveWorkspaceContext
) -> None:
    """注册受限 app 的 onboarding API（原 ``restricted_app`` 164–422）。

    受限 handler 直接读 ``x-wb-operation-id`` 头，因此本函数不接受 operation_id 回调
    （与蓝图签名清单的差异：多一个死参数只会误导）。
    """

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

    @app.post("/api/onboarding/preflight", response_model=None)
    def restricted_preflight(
        request: Request, payload: Annotated[OnboardingPreflightPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            report = onboarding_service.preflight(
                OnboardingFlow(payload.flow),
                resolve_user_path(payload.path),
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
                resolve_user_path(payload.work_root),
                display_name=payload.display_name,
                device_name=payload.device_name,
                templates_dir=onboarding_service.default_vault_templates_dir(),
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
                resolve_user_path(payload.vault_dir),
                display_name=payload.display_name,
                device_name=payload.device_name,
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}


__all__ = ["register_onboarding_routes", "register_restricted_onboarding_routes"]
