"""看板状态路由（LEGACY-APP-SPLIT-PLAN Step 8 / G 前半）。

从 ``legacy_app`` 抽出 ``GET /api/state``：看板数据（日期、状态速览、今日简报、inbox 积压）。
``runtime`` / ``build_info`` / 版本与模式信息全部由 ``create_app`` 注入，注入方式与
``routers/system.py`` 一致；本模块不自行读取全局状态。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI

from summit_workbench.observability.status import build_status
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.repositories.project_scan import count_inbox_pending, scan_all_projects
from summit_workbench.repositories.signal_snapshot import read_snapshot
from summit_workbench.webapp.api import brief_payload
from summit_workbench.webapp.build_info import BuildInfoError, WebBuildInfo
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_runtime import MutationRuntime


def register_state_routes(
    dependencies: RouteDependencies,
    *,
    runtime: MutationRuntime,
    build_info: Callable[[], WebBuildInfo],
    server_instance: str,
    started_at: str,
    panel_mode: Literal["production", "development-managed", "development-external"],
) -> None:
    """注册看板状态路由。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.get("/api/state")
    def api_state() -> dict[str, object]:
        """看板数据：日期、状态速览、今日简报、inbox 积压。"""
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=ctx.provider_config_file())
        sync_state = runtime.snapshot().state.value
        brief_md = read_brief_block(ctx.vault_dir, day)
        inbox_path = ctx.vault_dir / "inbox.md"
        inbox_pending = (
            count_inbox_pending(inbox_path.read_text(encoding="utf-8"))
            if inbox_path.is_file()
            else 0
        )
        projects = [
            {
                "name": p.name,
                "dirty": p.dirty,
                "ahead": p.ahead,
                "behind": p.behind,
                "has_upstream": p.has_upstream,
                "inbox_pending": p.inbox_pending,
                "next_step": p.next_step,
                "git_error": p.git_error,
                "registered": p.registered,
                "status": p.status,
                "is_thread": p.is_thread,
                "updated": p.updated,
                "activity_at": p.activity_at,
                "title": p.title,
            }
            for p in scan_all_projects(ctx.work_root, ctx.vault_dir)
        ]
        payload: dict[str, object] = {
            "day": day,
            "status": status.as_dict(),
            "brief_md": brief_md,
            "brief_generated": brief_md is not None,
            "brief": brief_payload(read_snapshot(ctx.vault_dir, day)),
            "inbox_pending": inbox_pending,
            "projects": projects,
            "sync_state": sync_state,
        }
        try:
            info = build_info()
        except BuildInfoError:
            info = None
        if info is not None:
            payload["runtime"] = {
                "frontend_build": info.frontend_build,
                "server_version": info.version_payload(
                    server_instance=server_instance,
                    started_at=started_at,
                    mode=panel_mode,
                )["server_version"],
                "server_instance": server_instance,
            }
        return payload
