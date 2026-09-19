"""同步冲突处理路由。

本模块只承载冲突解释、预演、详情、验证、导出与恢复；注册函数由 ``sync.py`` 在原有
位置调用，以保持 HTTP 路由注册顺序不变。
"""

from __future__ import annotations

from fastapi.responses import Response

from summit_workbench.domain.sync_conflict import explain_conflict, plan_conflict_recovery
from summit_workbench.repositories.git import GitError
from summit_workbench.webapp.api import SyncConflictRecoveryPayload, SyncConflictSelectionPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_runtime import MutationRuntime


def register_sync_conflict_routes(
    dependencies: RouteDependencies, *, runtime: MutationRuntime
) -> None:
    """注册同步冲突处理路由。"""
    app = dependencies.app
    ctx = dependencies.context

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


__all__ = ["register_sync_conflict_routes"]
