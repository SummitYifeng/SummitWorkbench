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

from typing import Annotated, cast

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from summit_workbench.config.paths import resolve_user_path
from summit_workbench.config.profiles import ActiveWorkspaceContext, resolve_workspace
from summit_workbench.domain.onboarding import OnboardingFlow
from summit_workbench.domain.workspace import DeviceRole
from summit_workbench.webapp.api import (
    OnboardingCreatePayload,
    OnboardingDraftPayload,
    OnboardingPreflightPayload,
    OnboardingRemoteConfirmPayload,
    OnboardingRemoteStagePayload,
    OnboardingVaultPayload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.security import error_payload
from summit_workbench.workflows import onboarding as onboarding_service


def _pat_secret(raw: str | None) -> SecretStr | None:
    """把使用者粘贴的 PAT 去空白后包成 ``SecretStr``；**全空白视为「没给」**。

    为什么要 strip：从 GitHub 复制 token 常带尾随换行/空格，而它随后要当 git 密码用。
    2026-09-14 实测：向导里 url/target/username 三个字段都 ``.trim()`` 了，**只有 PAT 没有**，
    服务端也没 strip——那种 token 一定认证失败，且报错很难看出是这个原因。
    """
    if raw is None:
        return None
    text = raw.strip()
    return SecretStr(text) if text else None


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
                device_role=DeviceRole(payload.device_role),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/upgrade", response_model=None)
    def api_onboarding_upgrade(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """upgrade-existing：旧 vault 升级（备份 + marker + profile，内容不动）。"""
        try:
            result = onboarding_service.upgrade_workspace(
                resolve_user_path(payload.vault_dir),
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
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
    remote_stages: dict[str, object] = {}

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

        pat = _pat_secret(payload.pat)
        credential_resolver = None
        if pat is not None:
            from summit_workbench.config.git_credentials import GitCredentials

            def resolve(_ws: str, host: str, _username: str) -> GitCredentials:
                return GitCredentials(_ws, host, payload.git_username, pat)

            credential_resolver = resolve

        try:
            staged = stage_remote_clone(
                payload.remote_url,
                resolve_user_path(payload.target_vault),
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
            confirm_pat = _pat_secret(payload.pat)
            if confirm_pat is not None:
                from urllib.parse import urlsplit

                from summit_workbench.config.git_credentials import store_git_credentials
                from summit_workbench.workflows.remote_onboarding import RemoteCloneStage

                staged_info = cast(RemoteCloneStage, staged)
                host = urlsplit(staged_info.remote_url).hostname or ""
                store_git_credentials(
                    staged_info.workspace_id, host, staged_info.username, confirm_pat
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
                resolve_user_path(payload.vault_dir),
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
