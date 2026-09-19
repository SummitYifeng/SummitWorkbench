"""简报/复盘路由（LEGACY-APP-SPLIT-PLAN Step 13 / R9）。

承载原 ``legacy_app`` 中 L 集群的 2 条 JSON 路由（``/api/run/brief``、``/api/run/weekly``）
与 N 集群的 2 条 SSR 路由（``/run/brief``、``/run/weekly``）。

``register_brief_routes`` 与原 JSON 路由同点注册，``register_brief_page_routes`` 与原 SSR
路由同点注册——两个函数分开，使 ``app.routes`` 顺序与拆分前逐项一致。事务守卫 ``runtime``
由 ``create_app`` 注入。
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_runtime import MutationRuntime


def register_brief_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册简报/复盘 JSON API（原 ``legacy_app`` 501–554）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/api/run/brief", response_model=None)
    def api_run_brief(request: Request) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.brief.runner import run_brief

        blocked = runtime.sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            run = run_brief(
                work_root=ctx.work_root,
                vault_dir=ctx.vault_dir,
                timezone=ctx.timezone,
                day=ctx.today(),
                write=True,
                notify=False,
                config_file=ctx.provider_config_file(),
                workspace_id=ctx.workspace_id,
            )
            commit_note = runtime.commit_suffix(
                run.persisted_paths,
                f"brief {ctx.today()}",
            )
            return {
                "ok": True,
                "message": (
                    f"已生成今日简报（健康度 {run.result.brief.health.level}）{commit_note}"
                ),
            }
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            return {"ok": False, "message": f"生成失败：{type(exc).__name__}: {exc}"}

    @app.post("/api/run/weekly", response_model=None)
    def api_run_weekly(request: Request) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.weekly.weekly import generate_weekly

        blocked = runtime.sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            result = generate_weekly(
                ctx.work_root,
                ctx.vault_dir,
                today=date.fromisoformat(ctx.today()),
                write=True,
                workspace_id=ctx.workspace_id,
            )
            return {"ok": True, "message": f"已生成周复盘 {result.review.week}"}
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            return {"ok": False, "message": f"生成失败：{type(exc).__name__}: {exc}"}


def register_brief_page_routes(
    dependencies: RouteDependencies, *, runtime: MutationRuntime
) -> None:
    """注册简报/复盘 SSR 兼容页（原 ``legacy_app`` 725–769）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/run/brief", response_class=RedirectResponse, response_model=None)
    def run_brief_endpoint(request: Request) -> RedirectResponse | JSONResponse:
        from summit_workbench.workflows.brief.runner import run_brief

        blocked = runtime.sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            run = run_brief(
                work_root=ctx.work_root,
                vault_dir=ctx.vault_dir,
                timezone=ctx.timezone,
                day=ctx.today(),
                write=True,
                notify=False,
                config_file=ctx.provider_config_file(),
                workspace_id=ctx.workspace_id,
            )
            msg = f"已生成今日简报（健康度 {run.result.brief.health.level}）"
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            msg = f"生成失败：{type(exc).__name__}: {exc}"
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)

    @app.post("/run/weekly", response_class=RedirectResponse, response_model=None)
    def run_weekly_endpoint(request: Request) -> RedirectResponse | JSONResponse:
        from summit_workbench.workflows.weekly.weekly import generate_weekly

        blocked = runtime.sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            result = generate_weekly(
                ctx.work_root,
                ctx.vault_dir,
                today=date.fromisoformat(ctx.today()),
                write=True,
                workspace_id=ctx.workspace_id,
            )
            msg = f"已生成周复盘 {result.review.week}"
        except Exception as exc:  # noqa: BLE001
            msg = f"生成失败：{type(exc).__name__}: {exc}"
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)


__all__ = ["register_brief_page_routes", "register_brief_routes"]
