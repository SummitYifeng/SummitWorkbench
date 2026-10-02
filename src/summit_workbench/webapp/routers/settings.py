"""Connection routes for the plain-language settings and onboarding steps."""

# Long response messages and route declarations are intentionally kept close to
# their HTTP contract; the formatter still normalizes the surrounding code.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException

from summit_workbench.webapp import feishu_authorization as _feishu_authorization
from summit_workbench.webapp.api import (
    DoctorPayload,
    ProfileRemovePayload,
    ProfileSwitchCommitPayload,
    ProfileSwitchPayload,
    ProviderSettingsPayload,
)
from summit_workbench.webapp.build_info import WebBuildInfo
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.routers import settings_connections as _settings_connections
from summit_workbench.webapp.routers.settings_connections import (
    register_restricted_connection_routes,
    register_settings_connection_routes,
)
from summit_workbench.workflows.profile_settings import (
    ProfileSettingsError,
    ProfileSwitchPlan,
    commit_profile_switch,
    list_profile_summaries,
    prepare_profile_switch,
    remove_local_profile,
    update_provider_settings,
)

_AuthorizationStates = _feishu_authorization.AuthorizationStates
_PendingAuthorization = _feishu_authorization.PendingAuthorization
_STATE_TTL = _feishu_authorization.STATE_TTL
_authorization_state_file = _feishu_authorization.authorization_state_file
_denied_reason = _feishu_authorization.denied_reason
_panel_redirect = _feishu_authorization.panel_redirect
_credential_error_code = _settings_connections._credential_error_code


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

    _CAPABILITY_PURPOSE: dict[str, str] = {
        "meeting": "上传逐字稿 → 结构化笔记",
        "ranking": "晨间简报 / 每周复盘的行动排序",
        "capture": "显式整理输入",
        "digest": "显式整理日志 / 产物",
        "review": "审批内容整理",
    }

    @app.get("/api/settings/model-parameters", response_model=None)
    def settings_model_parameters() -> dict[str, object]:
        from summit_workbench.providers.llm.config import CAPABILITIES
        from summit_workbench.workflows.settings_connections import model_config

        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        items: list[dict[str, object]] = []
        for capability in CAPABILITIES:
            try:
                cfg = model_config(
                    capability=capability,
                    config_file=ctx.provider_config_file(),
                    workspace_id=ctx.workspace_id,
                )
            except Exception:  # noqa: BLE001 - keep the settings page available.
                items.append(
                    {
                        "capability": capability,
                        "purpose": _CAPABILITY_PURPOSE.get(capability, ""),
                        "configured": False,
                    }
                )
                continue
            items.append(
                {
                    "capability": capability,
                    "purpose": _CAPABILITY_PURPOSE.get(capability, ""),
                    "configured": True,
                    "model_id": cfg.model_id,
                    "thinking": cfg.thinking,
                    "max_output_tokens": cfg.max_output_tokens,
                    "context_window_tokens": cfg.context_window_tokens,
                    "timeout_seconds": cfg.timeout_seconds,
                    "pricing_configured": bool(
                        cfg.pricing.input_per_mtok or cfg.pricing.output_per_mtok
                    ),
                }
            )
        return {
            "ok": True,
            "workspace_id": ctx.workspace_id,
            "note": "思考模式的推理 token 与最终答案共用 max_output_tokens；"
            "抽取/摘要/分类类任务建议 thinking=disabled。",
            "items": items,
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
