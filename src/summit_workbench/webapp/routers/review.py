"""审批路由（LEGACY-APP-SPLIT-PLAN Step 9 / R5）。

承载原 ``legacy_app`` 中 H 集群的 7 条 JSON 审批路由与 N 集群的 4 条 SSR 审批路由：
读取审批页与只读知识来源、单条/批量决策、字段编辑、应用预演。

``register_review_routes`` 在原 JSON 路由的注册点调用，``register_review_page_routes``
在原 SSR 路由的注册点调用——两个函数分开，使 ``app.routes`` 顺序与拆分前逐项一致。
事务守卫 ``runtime`` 由外部注入，``_load`` / ``_plan_text`` 来自 ``webapp.review_view``。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from summit_workbench.domain.approval import RETRIEVAL_TYPES, approval_digest
from summit_workbench.domain.markdown_blocks import chunk_markdown
from summit_workbench.domain.review import APPROVAL_ROUTES, CandidateDecision, RouteTarget
from summit_workbench.repositories.approval import approve_markdown
from summit_workbench.repositories.review_edit import (
    ReviewEditError,
    set_decision,
    set_decisions,
    update_fields,
)
from summit_workbench.repositories.review_page import review_path
from summit_workbench.repositories.vault import load_note, meta_date_iso
from summit_workbench.webapp.api import (
    BatchDecidePayload,
    ContentApprovalPayload,
    DecidePayload,
    EditPayload,
    review_payload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.knowledge_sources import (
    SOURCE_BODY_DISPLAY_CHARS,
    _is_knowledge_source,
)
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.review_view import _load, _plan_text
from summit_workbench.webapp.views import render_plan, render_review
from summit_workbench.workflows.content_review import list_pending_content
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.review_apply import apply_meeting_review


def register_review_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册审批 JSON API（原 ``legacy_app`` 563–725）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.get("/api/review")
    def api_review() -> dict[str, object]:
        entries, errors = _load(ctx.vault_dir)
        return {
            **review_payload(entries, errors),
            "content_items": [
                {
                    "path": item.path,
                    "title": item.title,
                    "content_type": item.content_type,
                    "summary": item.summary,
                    "body": item.body,
                    "content_sha256": item.content_sha256,
                }
                for item in list_pending_content(ctx.vault_dir)
            ],
        }

    @app.post("/api/review/content/approve", response_model=None)
    def api_approve_content(payload: ContentApprovalPayload) -> dict[str, object] | JSONResponse:
        """Approve the exact previewed formal page version, then make it active."""
        raw_path = payload.path
        if raw_path.startswith("/") or "\\" in raw_path or ".." in raw_path.split("/"):
            return JSONResponse({"ok": False, "message": "内容路径无效"}, status_code=400)
        relative = Path(*raw_path.split("/"))
        if relative.suffix.lower() != ".md":
            return JSONResponse(
                {"ok": False, "message": "只允许审批 Markdown 内容"}, status_code=400
            )
        root = ctx.vault_dir.resolve()
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            return JSONResponse({"ok": False, "message": "内容路径越界"}, status_code=400)
        if not source.is_file():
            return JSONResponse({"ok": False, "message": "内容不存在或已移动"}, status_code=404)

        try:

            def mutate(operation_id: str) -> LocalMutationOutcome[Path]:
                note = load_note(source)
                if note.parse_error is not None:
                    raise ValueError("内容格式无效，不能批准")
                content_type = note.meta.get("type")
                if (
                    not isinstance(content_type, str)
                    or content_type not in RETRIEVAL_TYPES
                    or content_type
                    in {
                        "source",
                        "meeting-transcript",
                    }
                ):
                    raise ValueError("该文件不是可批准的正式内容")
                if note.meta.get("status") != "pending-review":
                    raise ValueError("内容已变化或不再待审，请刷新审批页")
                if approval_digest(note.meta, note.body) != payload.content_sha256:
                    raise ValueError("内容在预览后发生变化，请刷新并重新核对")
                approve_markdown(
                    source,
                    operation_id=operation_id,
                    status="active",
                    expected_digest=payload.content_sha256,
                )
                return LocalMutationOutcome(source, (source,))

            result = runtime.run("review/content-approve", mutate)
        except ValueError as exc:
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=409)
        except OSError as exc:
            return JSONResponse({"ok": False, "message": f"批准失败：{exc}"}, status_code=500)
        return {
            "ok": True,
            "message": f"已批准当前版本：{raw_path}",
            **_mutation_fields(result),
        }

    @app.get("/api/review/source", response_class=PlainTextResponse)
    def api_review_source(path: str = "") -> PlainTextResponse:
        """在回环服务内只读展示审批候选引用的 Markdown/文本来源。"""
        relative = Path(path.strip())
        if not path.strip() or relative.is_absolute() or ".." in relative.parts:
            return PlainTextResponse("来源路径无效", status_code=400)
        if not _is_knowledge_source(relative):
            return PlainTextResponse("来源路径不在允许的知识范围内", status_code=400)
        root = ctx.vault_dir.resolve()
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            return PlainTextResponse("来源路径无效", status_code=400)
        if source.suffix.lower() not in {".md", ".txt"}:
            return PlainTextResponse("只允许打开 Markdown 或文本来源", status_code=415)
        if not source.is_file():
            return PlainTextResponse("来源不存在", status_code=404)
        if source.stat().st_size > 2_000_000:
            return PlainTextResponse("来源过大，请在本地编辑器中打开", status_code=413)
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return PlainTextResponse("来源不是可读取的 UTF-8 文本", status_code=415)
        return PlainTextResponse(text)

    @app.get("/api/sources/read", response_model=None)
    def api_sources_read(source_id: str = "") -> dict[str, object] | JSONResponse:
        """只读返回允许的知识 Markdown，供审批页证据面板查看。"""
        raw_id = source_id.strip()
        # 引用可以是「路径#区块」：解析文件时只看路径部分，返回时按区块切片，
        # 让「每条结论带 路径#区块 出处」在来源面板里能直接跳到对应段落。
        path_part, _, block = raw_id.partition("#")
        path_text = path_part.strip()
        # 空引用、以及「只有 #区块、没有路径」的引用，必须在**碰 Path 之前**挡掉：
        # `Path("").with_suffix(".md")` 会抛 `ValueError: PosixPath('.') has an empty name`，
        # 于是前端传一个畸形参数就变成 500（界面只能显示兜底的「服务内部错误」），
        # 而这里本就有明确的 400 语义。2026-09-14 在已装 build 41 上实测：两者都是 500。
        if not path_text:
            return JSONResponse(
                {"ok": False, "message": "来源路径不在允许的知识范围内"}, status_code=400
            )
        relative = Path(path_text)
        if relative.suffix.lower() != ".md":
            relative = relative.with_suffix(".md")
        if relative.is_absolute() or ".." in relative.parts or not _is_knowledge_source(relative):
            return JSONResponse(
                {"ok": False, "message": "来源路径不在允许的知识范围内"}, status_code=400
            )
        root = ctx.vault_dir.resolve()
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            return JSONResponse({"ok": False, "message": "来源路径越界"}, status_code=400)
        if not source.is_file():
            return JSONResponse({"ok": False, "message": "来源不存在或已失效"}, status_code=404)
        if source.stat().st_size > 256 * 1024:
            return JSONResponse(
                {"ok": False, "message": "来源超过 256 KiB，请缩小范围后重试"}, status_code=413
            )
        note = load_note(source)
        if note.parse_error is not None:
            return JSONResponse(
                {"ok": False, "message": "来源不是可读取的 Markdown 笔记"}, status_code=415
            )
        heading = ""
        if block:
            wanted = block.strip()
            match = next(
                (
                    chunk
                    for chunk in chunk_markdown(path_part, note.body)
                    if chunk.heading == wanted
                ),
                None,
            )
            if match is None:
                return JSONResponse(
                    {"ok": False, "message": f"来源中没有区块 {wanted}"}, status_code=404
                )
            note = replace(note, body=match.text)
            heading = match.heading
        title = next(
            (line[2:].strip() for line in note.body.splitlines() if line.startswith("# ")),
            str(note.meta.get("title") or note.meta.get("project") or source.stem),
        )
        date_value = meta_date_iso(note.meta.get("date")) or meta_date_iso(note.meta.get("updated"))
        # 正文超过展示预算时返回前 N 字符并显式标记；256 KiB 以上的文件仍在上方直接拒绝。
        truncated = len(note.body) > SOURCE_BODY_DISPLAY_CHARS
        body = note.body[:SOURCE_BODY_DISPLAY_CHARS] if truncated else note.body
        return {
            "ok": True,
            "source_id": raw_id,
            "title": title,
            "date": date_value,
            "body": body,
            "truncated": truncated,
            "anchor": raw_id,
            "heading": heading,
        }

    @app.post("/api/review/decide", response_model=None)
    def api_decide(payload: DecidePayload) -> dict[str, object]:
        try:

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                set_decision(
                    ctx.vault_dir, payload.candidate_id, CandidateDecision(payload.decision)
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = runtime.run(
                "review/decide",
                mutate,
            )
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"操作失败：{exc}"}
        return {
            "ok": True,
            "message": f"已更新 → {payload.decision}{_commit_note(result.commit_result)}",
            **_mutation_fields(result),
        }

    @app.post("/api/review/batch", response_model=None)
    def api_batch_decide(payload: BatchDecidePayload) -> dict[str, object]:
        try:
            result = runtime.run(
                "review/batch",
                lambda _operation_id: LocalMutationOutcome(
                    set_decisions(
                        ctx.vault_dir,
                        payload.candidate_ids,
                        CandidateDecision(payload.decision),
                    ),
                    (review_path(ctx.vault_dir),),
                ),
            )
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"操作失败：{exc}"}
        return {
            "ok": True,
            "message": f"已批量更新 {result.business_return} 条 → {payload.decision}"
            f"{_commit_note(result.commit_result)}",
            "updated": result.business_return,
            **_mutation_fields(result),
        }

    @app.post("/api/review/edit", response_model=None)
    def api_edit(payload: EditPayload) -> dict[str, object]:
        if payload.route and payload.route not in {route.value for route in APPROVAL_ROUTES}:
            return {"ok": False, "message": "请选择沉淀知识、更新项目或创建飞书任务"}
        try:

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                update_fields(
                    ctx.vault_dir,
                    payload.candidate_id,
                    description=payload.description,
                    target_project=payload.target_project,
                    route=RouteTarget(payload.route) if payload.route else None,
                    due_date=payload.due_date,
                    start_at=payload.start_at,
                    end_at=payload.end_at,
                    sink_target=payload.sink_target,
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = runtime.run(
                "review/edit",
                mutate,
            )
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {
            "ok": True,
            "message": f"已保存修改{_commit_note(result.commit_result)}",
            **_mutation_fields(result),
        }

    @app.post("/api/review/plan")
    def api_plan() -> dict[str, object]:
        try:
            report = apply_meeting_review(ctx.vault_dir, ctx.work_root, apply=False)
        except ValueError as exc:
            return {"ok": False, "message": f"预演失败：{exc}"}
        return {"ok": True, "plan_text": _plan_text(report), "executed": False}


def register_review_page_routes(
    dependencies: RouteDependencies, *, runtime: MutationRuntime
) -> None:
    """注册审批 SSR 兼容页（原 ``legacy_app`` 1525–1586）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.get("/review", response_class=HTMLResponse)
    def review(msg: str | None = None) -> HTMLResponse:
        entries, errors = _load(ctx.vault_dir)
        return HTMLResponse(render_review(entries, errors, message=msg))

    @app.post("/review/decide", response_class=RedirectResponse, response_model=None)
    def decide(
        candidate_id: str = Form(..., min_length=1, max_length=200),
        decision: str = Form(..., max_length=32),
    ) -> RedirectResponse:
        try:

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                set_decision(ctx.vault_dir, candidate_id, CandidateDecision(decision))
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = runtime.run(
                "review/decide",
                mutate,
            )
            msg = f"已更新 {candidate_id} → {decision}{_commit_note(result.commit_result)}"
        except (ReviewEditError, ValueError) as exc:
            msg = f"操作失败：{exc}"
        return RedirectResponse(url=f"/review?msg={msg}", status_code=303)

    @app.post("/review/edit", response_class=RedirectResponse, response_model=None)
    def edit(
        candidate_id: str = Form(..., min_length=1, max_length=200),
        description: str = Form("", max_length=100_000),
        target_project: str = Form("", max_length=200),
        route: str = Form("", max_length=64),
        due_date: str = Form("", max_length=32),
        sink_target: str = Form("", max_length=512),
    ) -> RedirectResponse:
        try:
            if route and RouteTarget(route) not in APPROVAL_ROUTES:
                raise ValueError("请选择沉淀知识、更新项目或创建飞书任务")

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                update_fields(
                    ctx.vault_dir,
                    candidate_id,
                    description=description.strip() or None,
                    target_project=target_project.strip() or None,
                    route=RouteTarget(route) if route else None,
                    due_date=due_date.strip() or None,
                    sink_target=sink_target.strip() or None,
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = runtime.run(
                "review/edit",
                mutate,
            )
            msg = f"已保存修改：{candidate_id}{_commit_note(result.commit_result)}"
        except (ReviewEditError, ValueError) as exc:
            msg = f"保存失败：{exc}"
        return RedirectResponse(url=f"/review?msg={msg}", status_code=303)

    @app.get("/review/plan", response_class=HTMLResponse)
    def plan() -> HTMLResponse:
        try:
            report = apply_meeting_review(ctx.vault_dir, ctx.work_root, apply=False)
        except ValueError as exc:
            return HTMLResponse(render_plan(f"预演失败：{exc}", executed=False))
        return HTMLResponse(render_plan(_plan_text(report), executed=False))


__all__ = ["register_review_page_routes", "register_review_routes"]
