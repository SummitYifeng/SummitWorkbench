"""同步路由（LEGACY-APP-SPLIT-PLAN Step 6 / Q）。

从 ``legacy_app`` 抽出的最大单块：11 条 ``/api/sync*`` 路由 + ``_sync_payload``。
``runtime: MutationRuntime`` 由 ``create_app`` 注入（蓝图 §4.3：运行时不得做成模块级单例），
``ctx`` 取自 ``dependencies.context``。

**handler 函数体逐字搬运**：``route_contract.py`` 用 ``inspect.getsource`` + 正则从 handler
源码里抽 error code，其中 11 个 code 只由单条 route 的源码承载（蓝图 §6-R1）——改字符串、
抽共用 helper、加装饰器包装都会让快照变化。payload 模型必须在模块顶层 import（§6-R2）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import (
    JSONResponse,
)
from starlette.responses import Response

if TYPE_CHECKING:
    pass

from summit_workbench.domain.sync_conflict import explain_conflict, plan_conflict_recovery
from summit_workbench.repositories.automation_primary import load_automation_primary
from summit_workbench.repositories.git import GitError
from summit_workbench.webapp.api import (
    AutomationPrimaryPayload,
    SyncConflictRecoveryPayload,
    SyncConflictSelectionPayload,
)
from summit_workbench.webapp.context import WebContext as WebContext
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.knowledge_sources import (
    KNOWLEDGE_SOURCE_ROOTS as KNOWLEDGE_SOURCE_ROOTS,
)
from summit_workbench.webapp.knowledge_sources import (
    SOURCE_BODY_DISPLAY_CHARS as SOURCE_BODY_DISPLAY_CHARS,
)
from summit_workbench.webapp.mutation_response import (
    _mutation_fields,
)
from summit_workbench.webapp.mutation_runtime import (
    MutationRuntime,
)
from summit_workbench.webapp.mutation_runtime import (
    _commit_suffix as _commit_suffix,
)
from summit_workbench.webapp.request_boundary import (
    _SCHEMA_UPGRADE_WRITE_EXEMPTIONS as _SCHEMA_UPGRADE_WRITE_EXEMPTIONS,
)
from summit_workbench.webapp.restricted_app import (
    _STATIC_DIR as _STATIC_DIR,
)
from summit_workbench.webapp.security import (
    error_payload,
)
from summit_workbench.workflows import sync_coordinator
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
)


def register_sync_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册同步领域路由。"""
    app = dependencies.app
    ctx = dependencies.context

    def _sync_payload() -> dict[str, object]:
        snapshot = runtime.snapshot()
        claim = load_automation_primary(ctx.vault_dir)
        return {
            "ok": True,
            "workspace_id": snapshot.workspace_id,
            "state": snapshot.state.value,
            "pending_commits": snapshot.pending_commits,
            "last_sync_at": snapshot.last_sync_at,
            "remote_checked_at": snapshot.remote_checked_at,
            "remote_check_status": snapshot.remote_check_status.value,
            "next_step": snapshot.next_step,
            "detail": snapshot.detail,
            "ahead": snapshot.ahead,
            "behind": snapshot.behind,
            "branch": snapshot.branch,
            "remote_host": snapshot.remote_host,
            "repo_states": snapshot.repo_states,
            "automation_primary_device_id": claim.device_id if claim is not None else None,
            "automation_primary_generation": claim.generation if claim is not None else None,
        }

    def _sync_local_role(claimed_device_id: str) -> str | None:
        """G1：声明成功后把本机 profile 的角色同步为 automation-primary。

        只在本机就是被声明的设备时改（绝不因为"别人声明成功"而改本机角色）；profile 属于
        本机 Application Support，不进 vault、不产生提交。
        """
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return None
        from summit_workbench.domain.workspace import DeviceRole
        from summit_workbench.repositories.profile_registry import load_profile, save_profile

        home = ctx.active_workspace.home
        profile = load_profile(ctx.workspace_id, home=home)
        if profile is None:
            return None
        if claimed_device_id != ctx.active_workspace.device_id:
            return profile.device_role.value
        if profile.device_role is DeviceRole.AUTOMATION_PRIMARY:
            return profile.device_role.value
        save_profile(
            profile.model_copy(update={"device_role": DeviceRole.AUTOMATION_PRIMARY}), home=home
        )
        return DeviceRole.AUTOMATION_PRIMARY.value

    @app.get("/api/sync/status", response_model=None)
    def api_sync_status() -> dict[str, object]:
        """当前 workspace 同步状态（供 UI banner；不执行任何 git 写）。"""
        return _sync_payload()

    @app.get("/api/sync/conflict/explain", response_model=None)
    def api_sync_conflict_explain(paths: str | None = None) -> dict[str, object]:
        """Explain conflict handling without fetching, merging, or writing anything."""
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        explanation = explain_conflict(runtime.snapshot().state, raw_paths)
        return {"ok": True, "conflict": explanation.as_dict()}

    @app.get("/api/sync/conflict/plan", response_model=None)
    def api_sync_conflict_plan(paths: str | None = None) -> dict[str, object]:
        """Return a safe recovery plan; preparation/apply are separate later steps."""
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        plan = plan_conflict_recovery(runtime.snapshot().state, raw_paths)
        return {"ok": True, "recovery_plan": plan.as_dict()}

    @app.get("/api/sync/conflict/details", response_model=None)
    def api_sync_conflict_details(paths: str | None = None) -> dict[str, object]:
        """Return safe structured details from already-fetched divergence refs."""
        snapshot = runtime.snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": True,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        from summit_workbench.workflows.sync_conflict_recovery import inspect_divergence

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
                paths=raw_paths or None,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "分叉详情暂时无法读取，请保留当前保护态并导出诊断",
            }
        return {
            "ok": True,
            "available": True,
            "state": snapshot.state.value,
            "details": details.as_dict(),
        }

    @app.get("/api/sync/conflict/validate", response_model=None)
    def api_sync_conflict_validate(paths: str | None = None) -> dict[str, object]:
        """Validate automatic event recovery in an ephemeral, non-git directory."""
        snapshot = runtime.snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": True,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            validate_automatic_recovery,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
                paths=raw_paths or None,
            )
            if not ctx.workspace_id:
                raise GitError("workspace 未配置")
            validation = validate_automatic_recovery(
                ctx.vault_dir,
                details,
                workspace_id=ctx.workspace_id,
                backend_kind=ctx.git_backend_kind,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "临时验证暂时无法执行，请保留当前保护态并导出诊断",
            }
        return {
            "ok": validation.status == "validated",
            "available": True,
            "state": snapshot.state.value,
            "validation": validation.as_dict(),
        }

    @app.get("/api/sync/conflict/export", response_model=None)
    def api_sync_conflict_export() -> Response:
        """Export a body-free recovery manifest; never export vault content or credentials."""
        snapshot = runtime.snapshot()
        raw_paths = ()
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            recovery_manifest_bytes,
        )

        plan = plan_conflict_recovery(snapshot.state, raw_paths)
        details = None
        if snapshot.state.value == "diverged-protected":
            try:
                details = inspect_divergence(
                    ctx.vault_dir,
                    backend_kind=ctx.git_backend_kind,
                    workspace_id=ctx.workspace_id,
                )
            except (ValueError, GitError):
                details = None
            if details is not None:
                plan = plan_conflict_recovery(
                    snapshot.state, tuple(path.path for path in details.paths)
                )
        return Response(
            content=recovery_manifest_bytes(snapshot.state, plan, details),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="summitworkbench-sync-recovery.zip"',
                "Cache-Control": "no-store, max-age=0",
            },
        )

    @app.post("/api/sync/conflict/selection/validate", response_model=None)
    def api_sync_conflict_selection_validate(
        payload: SyncConflictSelectionPayload,
    ) -> dict[str, object]:
        """Validate explicit choices against the current read-only divergence snapshot."""
        snapshot = runtime.snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            validate_manual_selections,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
            )
            result = validate_manual_selections(
                details,
                base_revision=payload.base_revision,
                local_revision=payload.local_revision,
                remote_revision=payload.remote_revision,
                selections=payload.selections,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前分叉快照暂时无法读取，请重新打开冲突详情",
            }
        return {
            "ok": result.status == "validated",
            "available": True,
            "state": snapshot.state.value,
            "selection": result.as_dict(),
        }

    @app.post("/api/sync/conflict/recover", response_model=None)
    def api_sync_conflict_recover(
        payload: SyncConflictRecoveryPayload,
    ) -> dict[str, object]:
        """Prepare or explicitly apply a revision-bound local recovery merge."""
        snapshot = runtime.snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        if not ctx.workspace_id:
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "workspace 未配置",
            }
        from summit_workbench.workflows.sync_conflict_recovery import (
            apply_prepared_recovery,
            inspect_divergence,
            prepare_automatic_recovery,
            prepare_manual_recovery,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
            )
            if (
                details.base_revision != payload.base_revision
                or details.local.revision != payload.local_revision
                or details.remote.revision != payload.remote_revision
            ):
                return {
                    "ok": False,
                    "available": True,
                    "state": snapshot.state.value,
                    "recovery": {
                        "status": "stale",
                        "error_code": "conflict_snapshot_stale",
                    },
                }
            if details.manual_path_count or payload.selections:
                prepared = prepare_manual_recovery(
                    ctx.vault_dir,
                    details,
                    workspace_id=ctx.workspace_id,
                    selections=payload.selections,
                    backend_kind=ctx.git_backend_kind,
                )
            else:
                prepared = prepare_automatic_recovery(
                    ctx.vault_dir,
                    details,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                )
            with prepared:
                if not payload.confirmed:
                    return {
                        "ok": False,
                        "available": True,
                        "state": snapshot.state.value,
                        "preparation": prepared.as_dict(),
                        "recovery": {
                            "status": "confirmation-required"
                            if prepared.ready
                            else "preparation-not-ready",
                            "error_code": "explicit_confirmation"
                            if prepared.ready
                            else prepared.error_code,
                        },
                    }
                result = apply_prepared_recovery(
                    ctx.vault_dir,
                    prepared,
                    workspace_id=ctx.workspace_id,
                    confirm=True,
                    backend_kind=ctx.git_backend_kind,
                )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": True,
                "state": snapshot.state.value,
                "reason": "恢复准备暂时无法执行，请保留当前保护态并重新读取分叉详情",
            }
        push: dict[str, object] | None = None
        if result.status == "committed":
            from summit_workbench.workflows.sync_coordinator import push_after_commit

            try:
                push_state, push_snapshot = push_after_commit(
                    ctx.vault_dir,
                    home=ctx.active_workspace.home if ctx.active_workspace else None,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                    context=ctx.active_workspace,
                )
                push = {
                    "ok": push_state.value == "ready",
                    "state": push_state.value,
                    "detail": push_snapshot.detail if push_snapshot is not None else None,
                }
            except (ValueError, GitError):
                push = {
                    "ok": False,
                    "state": "error",
                    "detail": "恢复提交已保留，但普通同步暂未完成",
                }
        current = runtime.snapshot()
        return {
            "ok": result.status == "committed",
            "available": True,
            "state": current.state.value,
            "recovery": result.as_dict(),
            "push": push,
        }

    @app.get("/api/sync/export", response_model=None)
    def api_sync_export() -> dict[str, object]:
        """导出脱敏的本机同步状态副本，不读 token、不修改共享 vault。"""
        return _sync_payload()

    @app.post("/api/sync/primary/claim", response_model=None)
    def api_claim_primary(
        request: Request, payload: AutomationPrimaryPayload
    ) -> dict[str, object] | JSONResponse:
        """显式声明/接管 automation-primary，并作为 wb 提交同步。"""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active profile 可以声明 workspace 主设备",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        from summit_workbench.repositories.automation_primary import claim_automation_primary

        try:
            result = runtime.run(
                "sync/primary",
                lambda _operation_id: LocalMutationOutcome(
                    claim_automation_primary(
                        ctx.vault_dir,
                        ctx.workspace_id or "",
                        payload.device_id,
                        expected_generation=payload.expected_generation,
                        takeover=payload.takeover,
                    ),
                    (ctx.vault_dir / ".summit-workbench" / "automation-primary.json",),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - stable API envelope
            code = getattr(exc, "code", "primary_claim_failed")
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=code, message=str(exc), operation_id=dependencies.operation_id(request)
                ),
            )
        return {
            "ok": True,
            "claim": result.business_return.model_dump(mode="json"),
            "device_role": _sync_local_role(result.business_return.device_id),
            **_mutation_fields(result),
        }

    @app.post("/api/sync/primary/downgrade", response_model=None)
    def api_downgrade_primary(request: Request) -> dict[str, object] | JSONResponse:
        """把本机角色降为 secondary（只改本机 profile，**不动** vault 内的主设备声明）。

        没有这个入口时角色只能升不能降：另一台机器要接手，本机必须先放弃 automation-primary。
        声明本身保持不变，接管仍由对方通过 /api/sync/primary/claim（takeover）完成。
        """
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active profile 可以调整本机角色",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        from summit_workbench.domain.workspace import DeviceRole
        from summit_workbench.repositories.profile_registry import load_profile, save_profile

        home = ctx.active_workspace.home
        profile = load_profile(ctx.workspace_id, home=home)
        if profile is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="profile_missing",
                    message="本机没有该工作台的 profile",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        if profile.device_role is not DeviceRole.SECONDARY:
            save_profile(
                profile.model_copy(update={"device_role": DeviceRole.SECONDARY}), home=home
            )
        return {
            "ok": True,
            "device_role": DeviceRole.SECONDARY.value,
            "device_id": ctx.active_workspace.device_id,
        }

    @app.post("/api/sync/run", response_model=None)
    def api_sync_run(request: Request) -> dict[str, object] | JSONResponse:
        """手动触发一次同步（fetch → ff → push，绝不 force）。"""
        state, outcomes, _ = sync_coordinator.sync_workspace(
            ctx.vault_dir,
            work_root=ctx.work_root,
            home=ctx.active_workspace.home if ctx.active_workspace else None,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )
        return {
            "ok": True,
            "state": state.value,
            "repos": [{"name": name, "state": repo_state.value} for name, repo_state in outcomes],
        }
