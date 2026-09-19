"""应用外壳：首页（SPA 优先 / SSR 回退）+ ``/static`` 挂载 + 看板与构建信息回调（Step 16 / S7）。

从 ``legacy_app`` 抽出。``install_app_shell`` 返回两个回调，供后续 ``register_*`` 注入：

- ``build_info``：``GET /api/version``、``GET /api/state`` 与 settings 域读取构建元信息；
- ``dashboard``：看板首页（状态速览 + 今日简报）；问答页签已下线。

``install_app_shell`` 的调用点必须与拆分前注册 ``/`` 的位置**完全相同**（§6-R7）：在
settings / state / review 等 ``register_*`` 之前，且在 ``install_security_boundary`` →
``install_cache_policy`` 之后，以免改变 ``app.routes`` 顺序与中间件顺序。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from summit_workbench.observability.status import build_status
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.webapp.build_info import WebBuildInfo
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.views import render_dashboard


@dataclass(frozen=True)
class AppShell:
    """``install_app_shell`` 的产物：供后续 ``register_*`` 注入的回调。"""

    build_info: Callable[[], WebBuildInfo]
    dashboard: Callable[..., HTMLResponse]


def install_app_shell(app: FastAPI, ctx: WebContext, spa_dir: Path) -> AppShell:
    """安装首页（SPA 优先，否则 SSR 回退）与 ``/static``，返回 shell 回调。"""

    def _build_info() -> WebBuildInfo:
        return WebBuildInfo.from_static_dir(spa_dir)

    def _dashboard(msg: str | None = None) -> HTMLResponse:
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=ctx.provider_config_file())
        brief_md = read_brief_block(ctx.vault_dir, day, workspace_id=ctx.workspace_id)
        return HTMLResponse(render_dashboard(status, day, brief_md, message=msg))

    # ---- 首页：SPA（已构建）或 SSR 回退 ----
    spa_index = spa_dir / "index.html"
    if spa_index.is_file():
        app.mount("/static", StaticFiles(directory=str(spa_dir)), name="static")

        @app.get("/", response_class=FileResponse, include_in_schema=False)
        def spa_home() -> FileResponse:
            return FileResponse(spa_index)

    else:

        @app.get("/", response_class=HTMLResponse)
        def home(msg: str | None = None) -> HTMLResponse:
            return _dashboard(msg=msg)

    return AppShell(build_info=_build_info, dashboard=_dashboard)


__all__ = ["AppShell", "install_app_shell"]
