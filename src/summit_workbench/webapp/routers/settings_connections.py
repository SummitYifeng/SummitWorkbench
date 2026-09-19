"""完整与受限工作台的模型/飞书连接路由。"""

# Long response messages and route declarations are intentionally kept close to
# their HTTP contract; the formatter still normalizes the surrounding code.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from summit_workbench.config.app_support import profile_config_file
from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.config.secrets import CredentialError
from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuConfigError
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.repositories.profile_registry import load_profile
from summit_workbench.webapp import feishu_authorization as _feishu_authorization
from summit_workbench.webapp.api import (
    FeishuCompletePayload,
    OnboardingConnectionPayload,
    OnboardingModelSavePayload,
    OnboardingModelVerifyPayload,
    ProviderVerifyPayload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload
from summit_workbench.webapp.onboarding_view import render_onboarding_wizard
from summit_workbench.workflows.settings_connections import (
    complete_feishu_authorization,
    ensure_feishu_credentials,
    feishu_config,
    verify_model,
)

_AuthorizationStates = _feishu_authorization.AuthorizationStates
_STATE_TTL = _feishu_authorization.STATE_TTL
_authorization_state_file = _feishu_authorization.authorization_state_file
_denied_reason = _feishu_authorization.denied_reason
_failure = _feishu_authorization.failure
_invalidate_feishu_client = _feishu_authorization.invalidate_feishu_client
_panel_redirect = _feishu_authorization.panel_redirect


def _verify_route(
    dependencies: RouteDependencies,
    request: Request,
    payload: ProviderVerifyPayload,
) -> dict[str, object] | JSONResponse:
    context = dependencies.context
    if context.workspace_id is None:
        return _failure(
            dependencies,
            request,
            status_code=409,
            code="workspace_not_found",
            message="请先选择工作区，再验证模型",
        )
    try:
        return {
            "ok": True,
            **verify_model(
                config_file=context.provider_config_file(),
                workspace_id=context.workspace_id,
                secret=payload.secret,
            ),
        }
    except Exception as exc:  # provider boundary: redact provider/keychain details
        return _failure(
            dependencies,
            request,
            status_code=502,
            code="provider_verification_failed",
            message=f"模型现场验证失败：{_plain_provider_error(exc)}",
        )


def _plain_provider_error(error: Exception) -> str:
    if isinstance(error, LLMError):
        return str(error)
    if isinstance(error, (FeishuAuthError, FeishuConfigError)):
        return str(error)
    if isinstance(error, CredentialError):
        return _credential_error_message(error)
    return "请检查配置后重试"


def _credential_error_message(error: CredentialError) -> str:
    return {
        "missing": "此安装包缺少飞书授权组件或工作区凭据",
        "denied": "钥匙串访问被拒绝，请在系统设置中允许访问后重试",
        "timeout": "钥匙串访问超时，请稍后重试",
        "unavailable": "钥匙串当前不可用，请检查系统状态后重试",
    }[error.reason]


def _credential_error_code(error: CredentialError) -> str:
    return "credential_timeout" if error.reason == "timeout" else "feishu_credentials_unavailable"


def _workspace_connection_inputs(
    active_workspace: ActiveWorkspaceContext,
    workspace_id: str,
) -> tuple[Path, Path | None] | None:
    profile: LocalProfile | None = load_profile(workspace_id, home=active_workspace.home)
    if profile is None:
        return None
    paths = resolve_work_paths(work_root=profile.work_root, vault_dir=profile.vault_dir)
    return profile_config_file(workspace_id, home=active_workspace.home), paths.lock_root


def register_settings_connection_routes(dependencies: RouteDependencies) -> None:
    """Register full-app provider verification and Feishu OAuth callback routes."""
    context = dependencies.context
    states = _AuthorizationStates(
        _authorization_state_file(
            context.active_workspace.home if context.active_workspace else None
        )
    )
    _register_full_routes(dependencies, states)


def _register_full_routes(dependencies: RouteDependencies, states: _AuthorizationStates) -> None:
    app = dependencies.app
    context = dependencies.context

    @app.get("/onboarding", response_class=HTMLResponse, include_in_schema=False)
    def full_onboarding() -> HTMLResponse:
        return HTMLResponse(render_onboarding_wizard(full_app=True))

    @app.post("/api/settings/provider/verify", response_model=None)
    def settings_provider_verify(
        request: Request, payload: ProviderVerifyPayload
    ) -> dict[str, object] | JSONResponse:
        return _verify_route(dependencies, request, payload)

    @app.post("/api/settings/feishu/authorize-url", response_model=None)
    def settings_feishu_authorize_url(request: Request) -> dict[str, object] | JSONResponse:
        if context.workspace_id is None:
            return _failure(
                dependencies,
                request,
                status_code=409,
                code="workspace_not_found",
                message="请先选择工作区，再授权飞书",
            )
        if not getattr(request.app.state, "feishu_callback_ready", True):
            return _failure(
                dependencies,
                request,
                status_code=503,
                code="feishu_callback_unavailable",
                message="飞书回调端口暂时不可用；工作台仍可正常使用，请关闭占用端口的程序后重试",
            )
        try:
            cfg = feishu_config(
                config_file=context.provider_config_file(), workspace_id=context.workspace_id
            )
            ensure_feishu_credentials(config=cfg, lock_root=context.lock_root)
            state = states.issue(context.workspace_id)
            from summit_workbench.providers.feishu.auth import build_authorize_url

            return {
                "ok": True,
                "authorize_url": build_authorize_url(cfg, state),
                "state": state,
                "expires_in": int(_STATE_TTL),
            }
        except CredentialError as exc:
            return _failure(
                dependencies,
                request,
                status_code=409,
                code=_credential_error_code(exc),
                message=f"飞书授权暂时不可用：{_credential_error_message(exc)}",
            )
        except Exception as exc:
            return _failure(
                dependencies,
                request,
                status_code=409,
                code="feishu_authorization_unavailable",
                message=f"飞书授权暂时不可用：{_plain_provider_error(exc)}",
            )

    @app.get("/api/settings/feishu/status", response_model=None)
    def settings_feishu_status(request: Request, state: str) -> dict[str, object] | JSONResponse:
        item = states.lookup(state)
        if item is None or item.workspace_id != context.workspace_id:
            return _failure(
                dependencies,
                request,
                status_code=404,
                code="feishu_state_expired",
                message="授权状态已失效，请重新点击授权",
            )
        return {"ok": True, "status": item.status, "reason": item.reason}

    @app.post("/api/settings/feishu/complete", response_model=None)
    def settings_feishu_complete(
        request: Request, payload: FeishuCompletePayload
    ) -> dict[str, object] | JSONResponse:
        workspace_id = context.workspace_id
        if workspace_id is None:
            return _failure(
                dependencies,
                request,
                status_code=409,
                code="workspace_not_found",
                message="请先选择工作区，再完成飞书授权",
            )
        if payload.state is not None and states.consume(payload.state, workspace_id) is None:
            return _failure(
                dependencies,
                request,
                status_code=400,
                code="feishu_state_invalid",
                message="授权链接已失效，请重新点击授权",
            )
        try:
            complete_feishu_authorization(
                config_file=context.provider_config_file(),
                workspace_id=workspace_id,
                lock_root=context.lock_root,
                code=payload.code,
                home=context.active_workspace.home if context.active_workspace else None,
            )
            _invalidate_feishu_client(app)
            return {"ok": True, "message": "飞书已连接 ✓"}
        except Exception as exc:
            return _failure(
                dependencies,
                request,
                status_code=502,
                code="feishu_authorization_failed",
                message=f"飞书授权失败：{_plain_provider_error(exc)}",
            )

    @app.get("/callback", response_model=None)
    @app.get("/callback/feishu", response_model=None)
    def feishu_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> HTMLResponse | RedirectResponse:
        if not state:
            return _panel_redirect(
                request, "feishu=failed#settings", reason="没有收到授权状态：请重新点击「授权飞书」"
            )
        item = states.lookup(state)
        if item is None or context.workspace_id != item.workspace_id:
            return _panel_redirect(
                request, "feishu=failed#settings", reason="授权链接已失效：请重新点击「授权飞书」"
            )
        if item.status == "connected":
            return _panel_redirect(request, "feishu=connected#settings")
        if item.status == "failed":
            return _panel_redirect(request, "feishu=failed#settings", reason=item.reason)
        workspace_id = item.workspace_id
        if error or not code:
            reason = _denied_reason(error)
            states.finish(state, workspace_id=workspace_id, status="failed", reason=reason)
            return _panel_redirect(request, "feishu=failed#settings", reason=reason)
        try:
            complete_feishu_authorization(
                config_file=context.provider_config_file(),
                workspace_id=workspace_id,
                lock_root=context.lock_root,
                code=code,
                home=context.active_workspace.home if context.active_workspace else None,
            )
        except Exception as exc:
            reason = _plain_provider_error(exc)
            states.finish(state, workspace_id=workspace_id, status="failed", reason=reason)
            return _panel_redirect(request, "feishu=failed#settings", reason=reason)
        states.finish(state, workspace_id=workspace_id, status="connected")
        _invalidate_feishu_client(app)
        return _panel_redirect(request, "feishu=connected#settings")


def register_restricted_connection_routes(
    app: FastAPI,
    *,
    active_workspace: ActiveWorkspaceContext,
    operation_id: Callable[[Request], str],
) -> None:
    """Expose the same connection service while the three-step wizard is restricted.

    The wizard has no active context yet, so every call carries the workspace id created
    by step one.  The implementation still goes through the shared connection service.
    """
    states = _AuthorizationStates(_authorization_state_file(active_workspace.home))
    application = app

    @application.post("/api/onboarding/model/verify", response_model=None)
    def onboarding_model_verify(
        request: Request, payload: OnboardingModelVerifyPayload
    ) -> dict[str, object] | JSONResponse:
        inputs = _workspace_connection_inputs(active_workspace, payload.workspace_id)
        if inputs is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_found",
                    message="工作区还没有准备好",
                    operation_id=operation_id(request),
                ),
            )
        config_file, _lock_root = inputs
        try:
            return {
                "ok": True,
                **verify_model(
                    config_file=config_file,
                    workspace_id=payload.workspace_id,
                    secret=payload.secret,
                ),
            }
        except Exception as exc:
            return JSONResponse(
                status_code=502,
                content=error_payload(
                    code="provider_verification_failed",
                    message=f"模型现场验证失败：{_plain_provider_error(exc)}",
                    operation_id=operation_id(request),
                ),
            )

    @application.post("/api/onboarding/model/save", response_model=None)
    def onboarding_model_save(
        request: Request, payload: OnboardingModelSavePayload
    ) -> dict[str, object] | JSONResponse:
        inputs = _workspace_connection_inputs(active_workspace, payload.workspace_id)
        if inputs is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_found",
                    message="工作区还没有准备好",
                    operation_id=operation_id(request),
                ),
            )
        try:
            from summit_workbench.workflows.profile_settings import update_provider_settings

            update_provider_settings(
                home=active_workspace.home,
                workspace_id=payload.workspace_id,
                provider="model",
                settings={
                    "capability": "shared",
                    "credential_capability": "shared",
                    "model_id": payload.model_id,
                    "base_url": payload.base_url,
                    "credential_account": "shared",
                },
                secret=payload.secret,
            )
            return {"ok": True, "message": "模型设置已保存"}
        except Exception as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="provider_settings_failed",
                    message=f"模型设置暂时无法保存：{_plain_provider_error(exc)}",
                    operation_id=operation_id(request),
                ),
            )

    @application.post("/api/onboarding/feishu/authorize-url", response_model=None)
    def onboarding_feishu_authorize_url(
        request: Request, payload: OnboardingConnectionPayload
    ) -> dict[str, object] | JSONResponse:
        inputs = _workspace_connection_inputs(active_workspace, payload.workspace_id)
        if inputs is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_found",
                    message="工作区还没有准备好",
                    operation_id=operation_id(request),
                ),
            )
        if not getattr(request.app.state, "feishu_callback_ready", True):
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="feishu_callback_unavailable",
                    message="飞书回调端口暂时不可用；工作台仍可正常使用，请关闭占用端口的程序后重试",
                    operation_id=operation_id(request),
                ),
            )
        config_file, _lock_root = inputs
        try:
            cfg = feishu_config(config_file=config_file, workspace_id=payload.workspace_id)
            ensure_feishu_credentials(config=cfg, lock_root=_lock_root)
            state = states.issue(payload.workspace_id)
            from summit_workbench.providers.feishu.auth import build_authorize_url

            return {
                "ok": True,
                "authorize_url": build_authorize_url(cfg, state),
                "state": state,
                "expires_in": int(_STATE_TTL),
            }
        except CredentialError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=_credential_error_code(exc),
                    message=f"飞书授权暂时不可用：{_credential_error_message(exc)}",
                    operation_id=operation_id(request),
                ),
            )
        except Exception as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="feishu_authorization_unavailable",
                    message=f"飞书授权暂时不可用：{_plain_provider_error(exc)}",
                    operation_id=operation_id(request),
                ),
            )

    @application.get("/api/onboarding/feishu/status", response_model=None)
    def onboarding_feishu_status(request: Request, state: str) -> dict[str, object] | JSONResponse:
        item = states.lookup(state)
        if item is None:
            return JSONResponse(
                status_code=404,
                content=error_payload(
                    code="feishu_state_expired",
                    message="授权状态已失效，请重新点击授权",
                    operation_id=operation_id(request),
                ),
            )
        return {
            "ok": True,
            "status": item.status,
            "workspace_id": item.workspace_id,
            "reason": item.reason,
        }

    @application.post("/api/onboarding/feishu/complete", response_model=None)
    def onboarding_feishu_complete(
        request: Request, payload: FeishuCompletePayload
    ) -> dict[str, object] | JSONResponse:
        workspace_id = states.consume(payload.state or "") if payload.state else None
        if workspace_id is None:
            return JSONResponse(
                status_code=400,
                content=error_payload(
                    code="feishu_state_invalid",
                    message="授权链接已失效，请重新点击授权",
                    operation_id=operation_id(request),
                ),
            )
        inputs = _workspace_connection_inputs(active_workspace, workspace_id)
        if inputs is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_found",
                    message="工作区还没有准备好",
                    operation_id=operation_id(request),
                ),
            )
        config_file, lock_root = inputs
        try:
            complete_feishu_authorization(
                config_file=config_file,
                workspace_id=workspace_id,
                lock_root=lock_root,
                code=payload.code,
                home=active_workspace.home,
            )
            return {"ok": True, "message": "飞书已连接 ✓"}
        except Exception as exc:
            return JSONResponse(
                status_code=502,
                content=error_payload(
                    code="feishu_authorization_failed",
                    message=f"飞书授权失败：{_plain_provider_error(exc)}",
                    operation_id=operation_id(request),
                ),
            )

    @application.get("/callback", response_model=None)
    @application.get("/callback/feishu", response_model=None)
    def restricted_feishu_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> HTMLResponse | RedirectResponse:
        if not state:
            return _panel_redirect(
                request, "feishu=failed", reason="没有收到授权状态：请重新点击「授权飞书」"
            )
        item = states.lookup(state)
        if item is None:
            return _panel_redirect(
                request, "feishu=failed", reason="授权链接已失效：请重新点击授权"
            )
        if item.status == "connected":
            return _panel_redirect(request, "feishu=connected")
        if item.status == "failed":
            return _panel_redirect(request, "feishu=failed", reason=item.reason)
        workspace_id = item.workspace_id
        if error or not code:
            reason = _denied_reason(error)
            states.finish(state, workspace_id=workspace_id, status="failed", reason=reason)
            return _panel_redirect(request, "feishu=failed", reason=reason)
        inputs = _workspace_connection_inputs(active_workspace, workspace_id)
        if inputs is None:
            reason = "工作区还没有准备好：请先回到第一步选择或创建工作区，再重新授权"
            states.finish(state, workspace_id=workspace_id, status="failed", reason=reason)
            return _panel_redirect(request, "feishu=failed", reason=reason)
        config_file, lock_root = inputs
        try:
            complete_feishu_authorization(
                config_file=config_file,
                workspace_id=workspace_id,
                lock_root=lock_root,
                code=code,
                home=active_workspace.home,
            )
        except Exception as exc:
            reason = _plain_provider_error(exc)
            states.finish(state, workspace_id=workspace_id, status="failed", reason=reason)
            return _panel_redirect(request, "feishu=failed", reason=reason)
        states.finish(state, workspace_id=workspace_id, status="connected")
        return _panel_redirect(request, "feishu=connected")


__all__ = [
    "_credential_error_code",
    "_credential_error_message",
    "_plain_provider_error",
    "_verify_route",
    "_workspace_connection_inputs",
    "register_restricted_connection_routes",
    "register_settings_connection_routes",
]
