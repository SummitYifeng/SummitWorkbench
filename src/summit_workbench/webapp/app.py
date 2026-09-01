"""本地审批面板的 FastAPI 应用（只绑定回环地址，服务端渲染）。

领域逻辑全部复用 repositories/workflows：读页用 ``parse_review_page``，改条目用
``review_edit``，应用用 ``apply_meeting_review``。Web 层只做路由与 HTML。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from summit_workbench.domain.review import CandidateDecision, ReviewEntry, RouteTarget
from summit_workbench.repositories.review_edit import (
    ReviewEditError,
    set_decision,
    update_fields,
)
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.webapp.views import render_plan, render_review
from summit_workbench.workflows.review_apply import (
    ApplyReport,
    TaskCreator,
    apply_meeting_review,
)


@dataclass(frozen=True)
class WebContext:
    vault_dir: Path
    work_root: Path
    timezone: str


def _load(vault_dir: Path) -> tuple[list[ReviewEntry], list[str]]:
    path = review_path(vault_dir)
    if not path.is_file():
        return [], []
    parsed = parse_review_page(path.read_text(encoding="utf-8"))
    return parsed.entries, parsed.errors


def _plan_text(report: ApplyReport) -> str:
    head = "DRY-RUN（零写入）" if report.dry_run else "已显式应用"
    lines = [head, ""]
    for a in report.actions:
        icon = "✓" if a.executable else "✗"
        reason = f"  原因：{a.reason}" if a.reason else ""
        lines.append(f"{icon} {a.candidate_id}  {a.decision.value} → {a.destination}{reason}")
    lines.append("")
    lines.append(
        f"结果：批准写回={report.applied}  拒绝归档={report.rejected}  失败={report.failed}"
    )
    if report.archive_path is not None:
        lines.append(f"审计：{report.archive_path}")
    return "\n".join(lines)


def _build_task_creator(ctx: WebContext) -> TaskCreator:
    from functools import lru_cache

    from summit_workbench.providers.feishu import (
        FeishuClient,
        FeishuSession,
        create_task,
        load_feishu_config,
    )

    @lru_cache(maxsize=1)
    def client() -> object:
        cfg = load_feishu_config()
        return FeishuClient(cfg, FeishuSession(cfg).access_token())

    def create(summary: str, due_date: str | None, candidate_id: str) -> str:
        return create_task(
            client(), summary, due_date, candidate_id, timezone=ctx.timezone  # type: ignore[arg-type]
        ).guid

    return create


def create_app(ctx: WebContext) -> FastAPI:
    app = FastAPI(title="SummitWorkbench 审批面板")

    @app.get("/", response_class=RedirectResponse)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/review", status_code=303)

    @app.get("/review", response_class=HTMLResponse)
    def review(msg: str | None = None) -> HTMLResponse:
        entries, errors = _load(ctx.vault_dir)
        return HTMLResponse(render_review(entries, errors, message=msg))

    @app.post("/review/decide", response_class=RedirectResponse)
    def decide(candidate_id: str = Form(...), decision: str = Form(...)) -> RedirectResponse:
        try:
            set_decision(ctx.vault_dir, candidate_id, CandidateDecision(decision))
            msg = f"已更新 {candidate_id} → {decision}"
        except (ReviewEditError, ValueError) as exc:
            msg = f"操作失败：{exc}"
        return RedirectResponse(url=f"/review?msg={msg}", status_code=303)

    @app.post("/review/edit", response_class=RedirectResponse)
    def edit(
        candidate_id: str = Form(...),
        description: str = Form(""),
        target_project: str = Form(""),
        route: str = Form(""),
        due_date: str = Form(""),
    ) -> RedirectResponse:
        try:
            update_fields(
                ctx.vault_dir,
                candidate_id,
                description=description.strip() or None,
                target_project=target_project.strip() or None,
                route=RouteTarget(route) if route else None,
                due_date=due_date.strip() or None,
            )
            msg = f"已保存修改：{candidate_id}"
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

    @app.post("/review/apply", response_class=HTMLResponse)
    def apply() -> HTMLResponse:
        try:
            report = apply_meeting_review(
                ctx.vault_dir, ctx.work_root, apply=True, task_creator=_build_task_creator(ctx)
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            detail = f"应用失败：{type(exc).__name__}: {exc}"
            return HTMLResponse(render_plan(detail, executed=True))
        return HTMLResponse(render_plan(_plan_text(report), executed=True))

    return app
