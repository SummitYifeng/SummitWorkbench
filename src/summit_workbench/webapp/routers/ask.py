"""问答路由（LEGACY-APP-SPLIT-PLAN Step 13 / R10）。

承载原 ``legacy_app`` 中 L 集群的 1 条 JSON 路由（``/api/ask``）与 N 集群的 1 条 SSR
路由（``/ask``）。

``_ask_html`` / ``_cited_source_ids`` 来自 ``webapp.ask_view``（S4）；迁移后测试通过
``summit_workbench.webapp.routers.ask._ask_html`` 做 monkeypatch（§6-R3）。
``/api/ask`` 的 ``ask_unavailable`` error code 内联在 handler 源码里，因此函数体必须
逐字保留，不得抽成共用 helper（§6-R1）。

``register_ask_routes`` 与原 JSON 路由同点注册，``register_ask_page_routes`` 与原 SSR
路由同点注册；后者所需的 ``_dashboard`` 由 ``create_app`` 注入。
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.webapp.api import AskPayload
from summit_workbench.webapp.ask_view import _ask_html as _ask_html
from summit_workbench.webapp.ask_view import _cited_source_ids
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.security import error_payload


def register_ask_routes(dependencies: RouteDependencies) -> None:
    """注册问答 JSON API（原 ``legacy_app`` 556–597）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context
    _operation_id = dependencies.operation_id

    @app.post("/api/ask", response_model=None)
    def api_ask(request: Request, payload: AskPayload) -> dict[str, object] | JSONResponse:
        question = payload.question.strip()
        if not question:
            return {"ok": False, "message": "请输入问题"}
        from summit_workbench.workflows.ask.ask import AskTurn

        history = tuple(
            AskTurn(question=t.question.strip(), sources=tuple(t.sources))
            for t in payload.history
            if t.question.strip()
        )
        project = None
        if payload.project:
            project = load_project_registry(ctx.vault_dir).resolve(payload.project)
        ask_result = _ask_html(
            ctx.vault_dir,
            question,
            history=history,
            project=project,
            config_file=ctx.config_file,
            workspace_id=ctx.workspace_id,
        )
        # 保留旧测试/扩展对二元返回值的兼容；新实现额外提供结构化答案。
        html, source_ids = ask_result[0], ask_result[1]
        answer = ask_result[2] if len(ask_result) > 2 else None
        if html.startswith('<p class="not-actionable">问答不可用：'):
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="ask_unavailable",
                    message="问答服务暂不可用",
                    operation_id=_operation_id(request),
                ),
            )
        return {
            "ok": True,
            "answer_html": html,
            "source_ids": source_ids,
            "cited_source_ids": _cited_source_ids(answer),
            "answer": answer,
        }


def register_ask_page_routes(
    dependencies: RouteDependencies,
    *,
    dashboard: Callable[..., HTMLResponse],
) -> None:
    """注册问答 SSR 兼容页（原 ``legacy_app`` 771–782）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context
    _dashboard = dashboard

    @app.post("/ask", response_class=HTMLResponse)
    def ask_endpoint(question: str = Form("", max_length=2_000)) -> HTMLResponse:
        q = question.strip()
        if not q:
            return _dashboard(msg="请输入问题")
        html, _source_ids, _answer = _ask_html(
            ctx.vault_dir,
            q,
            config_file=ctx.config_file,
            workspace_id=ctx.workspace_id,
        )
        return _dashboard(ask_q=q, ask_html=html)


__all__ = ["register_ask_page_routes", "register_ask_routes"]
