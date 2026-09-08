"""Connection routes for the plain-language settings and onboarding steps."""

# Long response messages and route declarations are intentionally kept close to
# their HTTP contract; the formatter still normalizes the surrounding code.
# ruff: noqa: E501

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from summit_workbench.config.app_support import (
    PROFILE_FILE_MODE,
    app_support_dir,
    profile_config_file,
)
from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.domain.workspace import LocalProfile
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuConfigError
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.repositories.profile_registry import load_profile
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
    feishu_config,
    verify_model,
)

_STATE_TTL = 600.0


@dataclass(frozen=True)
class _PendingAuthorization:
    workspace_id: str
    created_at: float
    status: Literal["pending", "connected", "failed"] = "pending"


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
    ) -> bool:
        self._purge()
        item = self._items.get(state)
        if item is None or item.workspace_id != workspace_id or item.status != "pending":
            return False
        self._items[state] = _PendingAuthorization(
            workspace_id=item.workspace_id,
            created_at=item.created_at,
            status=status,
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
                    self._items[state] = _PendingAuthorization(
                        workspace_id, float(created_at), status
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


def _panel_redirect(request: Request, suffix: str) -> HTMLResponse | RedirectResponse:
    """回到随机主面板端口，而不是停留在固定 OAuth 回调端口。"""
    port = getattr(request.app.state, "bound_port", None)
    base = f"http://127.0.0.1:{port}" if isinstance(port, int) and port > 0 else ""
    if not request.cookies.get("wb_session"):
        status = "授权已完成" if "connected" in suffix else "授权未完成"
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>SummitWorkbench</title>"
            f"<main style='font:16px -apple-system,sans-serif;max-width:520px;margin:15vh auto'>"
            f"<h1>{status}</h1><p>请返回 SummitWorkbench 窗口继续操作。</p></main>"
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
    if type(error).__name__ == "CredentialError":
        return "还没有找到对应的 workspace 凭据"
    return "请检查配置后重试"


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
            state = states.issue(context.workspace_id)
            from summit_workbench.providers.feishu.auth import build_authorize_url

            return {
                "ok": True,
                "authorize_url": build_authorize_url(cfg, state),
                "state": state,
                "expires_in": int(_STATE_TTL),
            }
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
        return {"ok": True, "status": item.status}

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
            return _panel_redirect(request, "feishu=failed#settings")
        item = states.lookup(state)
        if item is None or context.workspace_id != item.workspace_id:
            return _panel_redirect(request, "feishu=failed#settings")
        if item.status == "connected":
            return _panel_redirect(request, "feishu=connected#settings")
        if item.status == "failed":
            return _panel_redirect(request, "feishu=failed#settings")
        workspace_id = item.workspace_id
        if error or not code:
            states.finish(state, workspace_id=workspace_id, status="failed")
            return _panel_redirect(request, "feishu=failed#settings")
        try:
            complete_feishu_authorization(
                config_file=context.provider_config_file(),
                workspace_id=workspace_id,
                lock_root=context.lock_root,
                code=code,
            )
        except Exception:
            states.finish(state, workspace_id=workspace_id, status="failed")
            return _panel_redirect(request, "feishu=failed#settings")
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
            state = states.issue(payload.workspace_id)
            from summit_workbench.providers.feishu.auth import build_authorize_url

            return {
                "ok": True,
                "authorize_url": build_authorize_url(cfg, state),
                "state": state,
                "expires_in": int(_STATE_TTL),
            }
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
        return {"ok": True, "status": item.status, "workspace_id": item.workspace_id}

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
            return _panel_redirect(request, "feishu=failed")
        item = states.lookup(state)
        if item is None:
            return _panel_redirect(request, "feishu=failed")
        if item.status == "connected":
            return _panel_redirect(request, "feishu=connected")
        if item.status == "failed":
            return _panel_redirect(request, "feishu=failed")
        workspace_id = item.workspace_id
        if error or not code:
            states.finish(state, workspace_id=workspace_id, status="failed")
            return _panel_redirect(request, "feishu=failed")
        inputs = _workspace_connection_inputs(active_workspace, workspace_id)
        if inputs is None:
            states.finish(state, workspace_id=workspace_id, status="failed")
            return _panel_redirect(request, "feishu=failed")
        config_file, lock_root = inputs
        try:
            complete_feishu_authorization(
                config_file=config_file, workspace_id=workspace_id, lock_root=lock_root, code=code
            )
        except Exception:
            states.finish(state, workspace_id=workspace_id, status="failed")
            return _panel_redirect(request, "feishu=failed")
        states.finish(state, workspace_id=workspace_id, status="connected")
        return _panel_redirect(request, "feishu=connected")


__all__ = ["register_restricted_connection_routes", "register_settings_connection_routes"]
