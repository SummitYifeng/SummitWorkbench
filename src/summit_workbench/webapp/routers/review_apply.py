"""审批应用与外部动作路由（LEGACY-APP-SPLIT-PLAN Step 10 / R6）。

承载原 ``legacy_app`` 中 I 集群的 3 条 JSON 路由（外部动作读取、对账、审批应用）
与 N 集群的 1 条 SSR 应用路由。

``register_review_apply_routes`` 与原 JSON 路由同点注册，``register_review_apply_page_routes``
与原 SSR 路由同点注册——两个函数分开，使 ``app.routes`` 顺序与拆分前逐项一致。
飞书写回器工厂所需的 ``feishu_clients`` 与事务守卫 ``runtime`` 由 ``create_app`` 作为
关键字参数注入，本模块不自行读取全局状态（§6-R10）。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from summit_workbench.repositories.external_action_outbox import latest_action, latest_actions
from summit_workbench.webapp.api import (
    ExternalActionReconcilePayload,
    external_action_payload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.feishu_pool import (
    _build_task_creator,
    _FeishuClientPool,
)
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.review_view import _plan_text
from summit_workbench.webapp.views import render_plan
from summit_workbench.workflows.external_actions import (
    authorize_retry,
    reconcile_not_found,
    reconcile_succeeded,
    workspace_id_for_vault,
)
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.review_apply import apply_meeting_review


def register_review_apply_routes(
    dependencies: RouteDependencies,
    *,
    runtime: MutationRuntime,
    feishu_clients: _FeishuClientPool,
) -> None:
    """注册外部动作与审批应用 JSON API（原 ``legacy_app`` 537–631）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.get("/api/external-actions")
    def api_external_actions() -> dict[str, object]:
        workspace_id = workspace_id_for_vault(ctx.vault_dir)
        actions = latest_actions(ctx.vault_dir, workspace_id=workspace_id)
        return {"ok": True, "actions": [external_action_payload(action) for action in actions]}

    @app.post("/api/external-actions/{operation_id}/reconcile")
    def api_reconcile_external_action(
        operation_id: str, payload: ExternalActionReconcilePayload
    ) -> dict[str, object]:
        action = latest_action(ctx.vault_dir, operation_id)
        if action is None or action.workspace_id != workspace_id_for_vault(ctx.vault_dir):
            return {"ok": False, "message": "外部动作不存在或不属于当前工作区"}
        current_action = action
        try:
            if payload.decision == "recheck":
                return {
                    "ok": True,
                    "action": external_action_payload(action),
                    "message": "当前适配器不支持可靠远端检索，请人工确认是否已创建",
                }
            if payload.decision == "succeeded":
                result = runtime.run(
                    "external-actions/reconcile",
                    lambda _operation_id: LocalMutationOutcome(
                        reconcile_succeeded(ctx.vault_dir, current_action, payload.remote_id or ""),
                        (ctx.vault_dir / "_signals" / "external-actions" / "log.jsonl",),
                    ),
                )
                action = result.business_return
            elif payload.decision == "not-found":
                result = runtime.run(
                    "external-actions/reconcile",
                    lambda _operation_id: LocalMutationOutcome(
                        reconcile_not_found(ctx.vault_dir, current_action),
                        (ctx.vault_dir / "_signals" / "external-actions" / "log.jsonl",),
                    ),
                )
                action = result.business_return
            elif payload.decision == "retry":
                result = runtime.run(
                    "external-actions/reconcile",
                    lambda _operation_id: LocalMutationOutcome(
                        authorize_retry(
                            ctx.vault_dir, current_action, confirm=payload.confirm_retry
                        ),
                        (ctx.vault_dir / "_signals" / "external-actions" / "log.jsonl",),
                    ),
                )
                action = result.business_return
            else:
                return {
                    "ok": False,
                    "message": ("decision 必须是 recheck、succeeded、not-found 或 retry"),
                }
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "action": external_action_payload(action)}

    @app.post("/api/review/apply", response_model=None)
    def api_apply(request: Request) -> dict[str, object] | JSONResponse:
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            report = apply_meeting_review(
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx, feishu_clients),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"应用失败：{type(exc).__name__}: {exc}"}
        # 自动留痕：工作流返回真实 touched paths；库外路径由 commit 层过滤。
        git_note = runtime.commit_suffix(report.touched_paths or [], "审批应用写回")
        external_actions = latest_actions(
            ctx.vault_dir, workspace_id=workspace_id_for_vault(ctx.vault_dir)
        )
        return {
            "ok": True,
            "plan_text": _plan_text(report),
            "executed": True,
            "applied": report.applied,
            "rejected": report.rejected,
            "failed": report.failed,
            "git_note": git_note,
            "external_actions": [external_action_payload(action) for action in external_actions],
        }


def register_review_apply_page_routes(
    dependencies: RouteDependencies,
    *,
    runtime: MutationRuntime,
    feishu_clients: _FeishuClientPool,
) -> None:
    """注册审批应用 SSR 兼容页（原 ``legacy_app`` 1340–1356）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/review/apply", response_class=HTMLResponse, response_model=None)
    def apply(request: Request) -> HTMLResponse | JSONResponse:
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            report = apply_meeting_review(
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx, feishu_clients),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            detail = f"应用失败：{type(exc).__name__}: {exc}"
            return HTMLResponse(render_plan(detail, executed=True))
        git_note = runtime.commit_suffix(report.touched_paths or [], "审批应用写回")
        return HTMLResponse(render_plan(_plan_text(report) + git_note, executed=True))


__all__ = ["register_review_apply_page_routes", "register_review_apply_routes"]
