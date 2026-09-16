"""Connection routes for the plain-language settings and onboarding steps."""

# Long response messages and route declarations are intentionally kept close to
# their HTTP contract; the formatter still normalizes the surrounding code.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from summit_workbench import __version__
from summit_workbench.config.app_support import (
    PROFILE_FILE_MODE,
    app_support_dir,
    profile_config_file,
)
from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.config.secrets import CredentialError
from summit_workbench.domain.automation import AutomationJob
from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuConfigError
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.repositories.profile_registry import load_profile
from summit_workbench.webapp.api import (
    AcceptancePreflightPayload,
    AutomationRunPayload,
    AutomationSettingsPayload,
    DoctorPayload,
    FeishuCompletePayload,
    GitRemoteNormalizationPayload,
    GitRemoteNormalizationPlanPayload,
    GitRemoteRollbackPayload,
    OnboardingConnectionPayload,
    OnboardingModelSavePayload,
    OnboardingModelVerifyPayload,
    ProfileRemovePayload,
    ProfileSwitchCommitPayload,
    ProfileSwitchPayload,
    ProviderSettingsPayload,
    ProviderVerifyPayload,
)
from summit_workbench.webapp.build_info import BuildInfoError, WebBuildInfo, discover_build_number
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.onboarding_view import render_onboarding_wizard
from summit_workbench.workflows.acceptance_preflight import acceptance_preflight
from summit_workbench.workflows.profile_settings import (
    ProfileSettingsError,
    ProfileSwitchPlan,
    commit_profile_switch,
    list_profile_summaries,
    prepare_profile_switch,
    remove_local_profile,
    update_provider_settings,
)
from summit_workbench.workflows.remote_normalization import (
    RemoteNormalizationError,
    RemoteNormalizationPlan,
    apply_remote_normalization,
    preview_remote_normalization,
    rollback_remote_normalization,
)
from summit_workbench.workflows.settings_connections import (
    complete_feishu_authorization,
    ensure_feishu_credentials,
    feishu_config,
    verify_model,
)

_STATE_TTL = 600.0


@dataclass(frozen=True)
class _PendingAuthorization:
    workspace_id: str
    created_at: float
    status: Literal["pending", "connected", "failed"] = "pending"
    #: 失败原因（面向用户的白话，已脱敏）——分发包内置凭据后同事本机无可改配置，
    #: 唯一能自救的方式就是界面把原因说清楚。
    reason: str | None = None


class _AuthorizationStates:
    def __init__(self, state_file: Path | None = None) -> None:
        self._items: dict[str, _PendingAuthorization] = {}
        self._state_file = state_file
        self._load()

    def issue(self, workspace_id: str) -> str:
        self._purge()
        state = secrets.token_urlsafe(32)
        self._items[state] = _PendingAuthorization(workspace_id, time.time())
        self._persist()
        return state

    def consume(self, state: str, workspace_id: str | None = None) -> str | None:
        self._purge()
        item = self._items.pop(state, None)
        if item is None or (workspace_id is not None and item.workspace_id != workspace_id):
            return None
        self._persist()
        return item.workspace_id

    def lookup(self, state: str) -> _PendingAuthorization | None:
        self._purge()
        return self._items.get(state)

    def finish(
        self,
        state: str,
        *,
        workspace_id: str,
        status: Literal["connected", "failed"],
        reason: str | None = None,
    ) -> bool:
        self._purge()
        item = self._items.get(state)
        if item is None or item.workspace_id != workspace_id or item.status != "pending":
            return False
        self._items[state] = _PendingAuthorization(
            workspace_id=item.workspace_id,
            created_at=item.created_at,
            status=status,
            reason=reason if status == "failed" else None,
        )
        self._persist()
        return True

    def _purge(self) -> None:
        now = time.time()
        active = {
            key: value for key, value in self._items.items() if now - value.created_at < _STATE_TTL
        }
        if active != self._items:
            self._items = active
            self._persist()

    def _load(self) -> None:
        if self._state_file is None or not self._state_file.is_file():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            items = raw.get("items", {}) if isinstance(raw, dict) else {}
            if not isinstance(items, dict):
                return
            for state, item in items.items():
                if not isinstance(state, str) or not isinstance(item, dict):
                    continue
                workspace_id = item.get("workspace_id")
                created_at = item.get("created_at")
                status = item.get("status", "pending")
                if (
                    isinstance(workspace_id, str)
                    and isinstance(created_at, (int, float))
                    and status in {"pending", "connected", "failed"}
                ):
                    reason = item.get("reason")
                    self._items[state] = _PendingAuthorization(
                        workspace_id,
                        float(created_at),
                        status,
                        reason if isinstance(reason, str) and reason else None,
                    )
            self._purge()
        except (OSError, ValueError, TypeError):
            self._items.clear()

    def _persist(self) -> None:
        if self._state_file is None:
            return
        from summit_workbench.repositories._atomic import atomic_write_text

        payload = {
            "schema_version": 1,
            "items": {
                state: {
                    "workspace_id": item.workspace_id,
                    "created_at": item.created_at,
                    "status": item.status,
                    **({"reason": item.reason} if item.reason else {}),
                }
                for state, item in self._items.items()
            },
        }
        atomic_write_text(
            self._state_file,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            ensure_parents=True,
            new_mode=PROFILE_FILE_MODE,
        )


def _authorization_state_file(home: Path | None) -> Path | None:
    return app_support_dir(home) / "feishu-auth-state.json" if home is not None else None


def _denied_reason(error: str | None) -> str:
    """飞书侧直接拒绝、或回调没带授权码时的原因文案（面向用户，可执行）。"""
    if error == "access_denied":
        return "你取消了授权；需要时可以重新点一次「授权飞书」"
    if error:
        return f"飞书返回了授权错误（{error}）：请重新点一次「授权飞书」"
    return "没有收到授权码：请重新点一次「授权飞书」"


def _failure(
    dependencies: RouteDependencies,
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            code=code,
            message=message,
            operation_id=dependencies.operation_id(request),
        ),
    )


def _panel_redirect(
    request: Request, suffix: str, *, reason: str | None = None
) -> HTMLResponse | RedirectResponse:
    """回到随机主面板端口，而不是停留在固定 OAuth 回调端口。

    ``reason`` 只在「拿不到 wb_session cookie」这条分支用到：此时无法把用户带回面板
    （例如授权是在外部浏览器里完成的），返回的静态页必须自己说明失败原因，
    否则又是「只说失败」。文案做了 HTML 转义——它会拼进页面。
    """
    port = getattr(request.app.state, "bound_port", None)
    base = f"http://127.0.0.1:{port}" if isinstance(port, int) and port > 0 else ""
    if not request.cookies.get("wb_session"):
        status = "授权已完成" if "connected" in suffix else "授权未完成"
        detail = f"<p>{html.escape(reason)}</p>" if reason else ""
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>SummitWorkbench</title>"
            f"<main style='font:16px -apple-system,sans-serif;max-width:520px;margin:15vh auto'>"
            f"<h1>{status}</h1>{detail}<p>请返回 SummitWorkbench 窗口继续操作。</p></main>"
        )
    return RedirectResponse(url=f"{base}/?{suffix}", status_code=303)


def _invalidate_feishu_client(app: FastAPI) -> None:
    clients = getattr(app.state, "feishu_clients", None)
    invalidate = getattr(clients, "invalidate", None)
    if callable(invalidate):
        invalidate("user")


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
                code="feishu_credentials_unavailable",
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
                    code="feishu_credentials_unavailable",
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
                request, "feishu=failed", reason="授权链接已失效：请重新点击「授权飞书」"
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


__all__ = ["register_restricted_connection_routes", "register_settings_connection_routes"]


def register_settings_routes(
    dependencies: RouteDependencies,
    *,
    runtime: MutationRuntime,
    build_info: Callable[[], WebBuildInfo],
) -> None:
    """注册设置领域路由（LEGACY-APP-SPLIT-PLAN Step 7 / F）。

    ``switch_plans`` / ``remote_normalization_plans`` **在函数体内创建**：提升为模块级 dict
    会让同进程的多个 app 实例共享切换计划与远端方案，改变现有语义并污染测试（蓝图 §6-R8）。
    """
    app = dependencies.app
    ctx = dependencies.context
    switch_plans: dict[str, object] = {}
    remote_normalization_plans: dict[str, RemoteNormalizationPlan] = {}

    def _settings_home() -> Path:
        return ctx.active_workspace.home if ctx.active_workspace else Path.home()

    @app.get("/api/settings/profiles", response_model=None)
    def settings_profiles() -> dict[str, object]:
        from summit_workbench.repositories.profile_registry import active_profile_id

        summaries = list_profile_summaries(home=_settings_home())
        return {
            "ok": True,
            "active_workspace_id": active_profile_id(home=_settings_home()),
            "current_device_id": (
                ctx.active_workspace.device_id if ctx.active_workspace is not None else None
            ),
            "profiles": [item.as_dict() for item in summaries],
        }

    @app.post("/api/settings/acceptance-preflight", response_model=None)
    def settings_acceptance_preflight(
        request: Request, _payload: AcceptancePreflightPayload
    ) -> dict[str, object] | JSONResponse:
        """Run the read-only P1-07D gate and return a copyable redacted report."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以运行验收预检",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        try:
            try:
                web_info = build_info()
                frontend_build = web_info.frontend_build
                git_revision = web_info.git_revision
            except BuildInfoError:
                frontend_build = None
                git_revision = None
            report = acceptance_preflight(
                ctx.vault_dir,
                home=ctx.active_workspace.home,
                workspace_id=ctx.workspace_id,
                app_version=__version__,
                backend_kind=ctx.git_backend_kind or "dulwich",
                build_number=discover_build_number(),
                frontend_build=frontend_build,
                git_revision=git_revision,
            )
        except Exception:  # noqa: BLE001 - report boundary must stay redacted
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="acceptance_preflight_failed",
                    message="验收预检无法完成；请查看本机诊断，不会显示凭据或远端密钥",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        return {
            "ok": report.ok,
            "workspace_id": report.workspace_id,
            "app_version": report.app_version,
            "checks": [item.__dict__ for item in report.checks],
            "report": report.text,
        }

    @app.post("/api/settings/git/remote/preview", response_model=None)
    def settings_git_remote_preview(
        request: Request, payload: GitRemoteNormalizationPayload
    ) -> dict[str, object] | JSONResponse:
        """Validate a candidate HTTPS origin in a temporary clone; no local mutation."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以规范化 Git remote",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        try:
            from pydantic import SecretStr

            plan = preview_remote_normalization(
                ctx.vault_dir,
                workspace_id=ctx.workspace_id,
                username=payload.git_username,
                pat=SecretStr(payload.pat),
                candidate_url=payload.candidate_url,
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=dependencies.operation_id(request)
                ),
            )
        remote_normalization_plans[plan.plan_id] = plan
        return {
            "ok": True,
            "plan_id": plan.plan_id,
            "workspace_id": plan.workspace_id,
            "old_url": plan.old_url,
            "candidate_url": plan.candidate_url,
            "branch": plan.branch,
            "candidate_fetched": plan.candidate.fetched,
            "candidate_ahead": plan.candidate.ahead,
            "candidate_behind": plan.candidate.behind,
            "note": "预览未修改 origin、profile、vault、提交、推送或 Keychain",
        }

    @app.post("/api/settings/git/remote/apply", response_model=None)
    def settings_git_remote_apply(
        request: Request, payload: GitRemoteNormalizationPlanPayload
    ) -> dict[str, object] | JSONResponse:
        """Revalidate a preview then atomically apply origin/profile/keychain."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以规范化 Git remote",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        plan = remote_normalization_plans.get(payload.plan_id)
        if plan is None or plan.workspace_id != ctx.workspace_id:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="normalization_plan_missing",
                    message="转换预览已失效，请重新预览",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        try:
            from pydantic import SecretStr

            transaction = apply_remote_normalization(
                ctx.vault_dir,
                plan,
                username=payload.git_username,
                pat=SecretStr(payload.pat),
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=dependencies.operation_id(request)
                ),
            )
        remote_normalization_plans.pop(payload.plan_id, None)
        return {
            "ok": True,
            "transaction_id": transaction.transaction_id,
            "old_url": transaction.old_url,
            "new_url": transaction.new_url,
            "note": "origin/profile/Keychain 已更新；未提交、未推送、未修改 vault 内容",
        }

    @app.post("/api/settings/git/remote/rollback", response_model=None)
    def settings_git_remote_rollback(
        request: Request, payload: GitRemoteRollbackPayload
    ) -> dict[str, object] | JSONResponse:
        """Rollback the last applied remote normalization transaction."""
        if not payload.confirmed or ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="confirmation_required",
                    message="请明确确认回滚当前 remote 转换",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        try:
            transaction = rollback_remote_normalization(
                ctx.vault_dir,
                workspace_id=ctx.workspace_id,
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=dependencies.operation_id(request)
                ),
            )
        return {
            "ok": True,
            "transaction_id": transaction.transaction_id,
            "restored_url": transaction.old_url,
            "note": "origin/profile 已恢复；未提交、未推送、未修改 vault 内容",
        }

    @app.post("/api/settings/git/remote/publish", response_model=None)
    def settings_git_remote_publish(
        request: Request, payload: GitRemoteNormalizationPayload
    ) -> dict[str, object] | JSONResponse:
        """G2：把还没有 origin 的本地工作台首次发布到一个空的 HTTPS 远端。

        与「预览 HTTPS 转换」互补：那条路径要求工作台**已有** origin+upstream；
        这条路径用于"本地已存在、远端尚未创建"的工作台。校验远端为空且可推送后，
        add origin → 首次 push → 写 profile/Keychain；push 之前失败会移除 origin。
        """
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以首次发布到远端",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        try:
            from pydantic import SecretStr

            from summit_workbench.workflows.remote_publish import publish_workspace_to_remote

            result = publish_workspace_to_remote(
                ctx.vault_dir,
                workspace_id=ctx.workspace_id,
                username=payload.git_username,
                pat=SecretStr(payload.pat),
                candidate_url=payload.candidate_url,
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=dependencies.operation_id(request)
                ),
            )
        return {
            "ok": True,
            "remote_url": result.remote_url,
            "branch": result.branch,
            "head": result.head,
            "note": "origin 与 upstream 已绑定并完成首次推送；未修改 vault 内容",
        }

    @app.post("/api/settings/profile/prepare", response_model=None)
    def settings_profile_prepare(payload: ProfileSwitchPayload) -> dict[str, object]:
        try:
            plan = prepare_profile_switch(
                home=_settings_home(), target_workspace_id=payload.workspace_id
            )
        except ProfileSettingsError as exc:
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        switch_plans[plan.plan_id] = plan
        runtime.begin_profile_switch()
        return {"ok": True, "plan_id": plan.plan_id, "workspace_id": plan.target_workspace_id}

    @app.post("/api/settings/profile/commit", response_model=None)
    def settings_profile_commit(payload: ProfileSwitchCommitPayload) -> dict[str, object]:
        plan = switch_plans.pop(payload.plan_id, None)
        if plan is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "switch_plan_missing", "message": "切换计划已失效，请重新准备"},
            )
        assert isinstance(plan, ProfileSwitchPlan)
        try:
            return commit_profile_switch(home=_settings_home(), plan=plan)
        except ProfileSettingsError as exc:
            runtime.end_profile_switch()
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @app.post("/api/settings/profile/remove", response_model=None)
    def settings_profile_remove(payload: ProfileRemovePayload) -> dict[str, object]:
        try:
            return remove_local_profile(
                home=_settings_home(),
                workspace_id=payload.workspace_id,
                confirmed=payload.confirmed,
            )
        except ProfileSettingsError as exc:
            if exc.code == "confirmation_required":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": exc.code,
                        "message": str(exc),
                        "details": {
                            "workspace_id": payload.workspace_id,
                            "deletes": ["local_profile", "runtime", "onboarding_draft"],
                            "preserves": ["vault", "remote", "keychain"],
                        },
                    },
                ) from exc
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @app.post("/api/settings/provider", response_model=None)
    def settings_provider(payload: ProviderSettingsPayload) -> dict[str, object]:
        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        try:
            return update_provider_settings(
                home=_settings_home(),
                workspace_id=ctx.workspace_id,
                provider=payload.provider,
                settings=payload.settings,
                secret=payload.secret,
            )
        except ProfileSettingsError as exc:
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    def _automation_settings_payload() -> dict[str, object]:
        from summit_workbench.repositories.automation_settings import load_automation_settings

        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        try:
            settings = load_automation_settings(ctx.workspace_id, home=_settings_home())
        except ValueError as exc:
            raise HTTPException(
                status_code=409, detail={"code": "automation_settings_invalid", "message": str(exc)}
            ) from exc
        return {
            "ok": True,
            "workspace_id": settings.workspace_id,
            "jobs": {
                job.value: schedule.model_dump(mode="json")
                for job, schedule in ((job, settings.for_job(job)) for job in AutomationJob)
            },
        }

    @app.get("/api/settings/automation", response_model=None)
    def settings_automation() -> dict[str, object]:
        return _automation_settings_payload()

    @app.put("/api/settings/automation", response_model=None)
    def update_settings_automation(payload: AutomationSettingsPayload) -> dict[str, object]:
        from summit_workbench.repositories.automation_settings import (
            load_automation_settings,
            save_automation_settings,
        )

        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        job = AutomationJob(payload.job)
        try:
            settings = load_automation_settings(ctx.workspace_id, home=_settings_home())
            current = settings.for_job(job)
            settings.jobs[job] = current.model_copy(
                update={
                    "enabled": payload.enabled,
                    "hour": payload.hour,
                    "minute": payload.minute,
                    "weekdays": sorted(set(payload.weekdays)),
                    "next_run_at": None,
                }
            )
            save_automation_settings(settings, home=_settings_home())
        except ValueError as exc:
            raise HTTPException(
                status_code=409, detail={"code": "automation_settings_invalid", "message": str(exc)}
            ) from exc
        return {"ok": True, "job": settings.jobs[job].model_dump(mode="json")}

    @app.post("/api/settings/automation/run", response_model=None)
    def run_settings_automation(
        request: Request, payload: AutomationRunPayload
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.automation_worker import run_automation_job

        if ctx.active_workspace is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        # 「立即运行」是人工触发，不应被当天已执行过的调度记录拦截；
        # 定时 worker 仍使用默认的 schedule due 门控。
        result = run_automation_job(ctx.active_workspace, AutomationJob(payload.job), force=True)
        # secondary/未启用的「跳过」是预期结果，不是错误：返回 ok=true 让前端以提示而非
        # 报错呈现（P1-07D 要求 Air 自动化安全跳过，绝不运行定时 writer）。
        return {
            "ok": result.status.value in {"success", "degraded", "skipped", "not-primary"},
            **result.as_dict(),
        }

    @app.post("/api/settings/doctor", response_model=None)
    def settings_doctor(payload: DoctorPayload) -> dict[str, object]:
        from summit_workbench.cli.doctor import CheckStatus, run_checks
        from summit_workbench.config.settings import load_settings

        active = ctx.active_workspace
        settings = load_settings(
            work_root=ctx.work_root, vault_dir=ctx.vault_dir, timezone=ctx.timezone
        )
        checks = run_checks(
            settings,
            config_file=ctx.provider_config_file(),
            online=payload.online,
            context=active,
        )
        return {
            "ok": not any(item.status is CheckStatus.FAIL for item in checks),
            "online": payload.online,
            "checks": [item.as_dict() for item in checks],
        }
