"""本地面板的 FastAPI 应用（只绑定回环地址，服务端渲染）。

领域逻辑全部复用 repositories/workflows：审批读页用 ``parse_review_page``、改条目用
``review_edit``、应用用 ``apply_meeting_review``；看板状态用 ``build_status``、简报/复盘/问答用
各自 runner。Web 层只做路由与 HTML。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.review import CandidateDecision, ReviewEntry, RouteTarget
from summit_workbench.observability.status import build_status
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.repositories.review_edit import (
    ReviewEditError,
    set_decision,
    update_fields,
)
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.webapp.views import render_dashboard, render_plan, render_review
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

    def today(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).date().isoformat()


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
            client(),  # type: ignore[arg-type]
            summary,
            due_date,
            candidate_id,
            timezone=ctx.timezone,
        ).guid

    return create


def _ask_html(vault_dir: Path, question: str) -> str:
    """跑一次 wb ask 并渲染为 HTML；模型不可用时返回可见错误。"""
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError, load_model_config
    from summit_workbench.workflows.ask.ask import answer_question

    try:
        cfg = load_model_config("qa")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
        result = answer_question(vault_dir, question, cfg, api_key, prompt=prompt)
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return f'<p class="not-actionable">问答不可用：{escape(str(exc))}</p>'

    answer = result.answer
    parts = [f"<p><strong>{escape(answer.summary)}</strong></p>"]
    if answer.facts:
        parts.append("<h4>事实（带来源）</h4><ul>")
        parts += [
            f"<li>{escape(f.text)} <span class='wikilink'>[[{escape(f.source_id)}]]</span></li>"
            for f in answer.facts
        ]
        parts.append("</ul>")
    if answer.suggestions:
        parts.append("<h4>建议（模型推断）</h4><ul>")
        parts += [f"<li>{escape(s)}</li>" for s in answer.suggestions]
        parts.append("</ul>")
    if result.sources:
        srcs = "、".join(f"[[{escape(c.source_id)}]]" for c in result.sources)
        parts.append(f'<p class="not-actionable">召回来源：{srcs}</p>')
    return "\n".join(parts)


def create_app(ctx: WebContext) -> FastAPI:
    app = FastAPI(title="SummitWorkbench 面板")

    def _dashboard(
        msg: str | None = None, ask_q: str = "", ask_html: str | None = None
    ) -> HTMLResponse:
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=default_config_file())
        brief_md = read_brief_block(ctx.vault_dir, day)
        return HTMLResponse(
            render_dashboard(
                status,
                day,
                brief_md,
                ask_question=ask_q,
                ask_answer_html=ask_html,
                message=msg,
            )
        )

    @app.get("/", response_class=HTMLResponse)
    def home(msg: str | None = None) -> HTMLResponse:
        return _dashboard(msg=msg)

    @app.post("/run/brief", response_class=RedirectResponse)
    def run_brief_endpoint() -> RedirectResponse:
        from summit_workbench.workflows.brief.runner import run_brief

        try:
            run = run_brief(
                work_root=ctx.work_root,
                vault_dir=ctx.vault_dir,
                timezone=ctx.timezone,
                day=ctx.today(),
                write=True,
                notify=False,
            )
            msg = f"已生成今日简报（健康度 {run.result.brief.health.level}）"
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            msg = f"生成失败：{type(exc).__name__}: {exc}"
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)

    @app.post("/run/weekly", response_class=RedirectResponse)
    def run_weekly_endpoint() -> RedirectResponse:
        from summit_workbench.workflows.weekly.weekly import generate_weekly

        try:
            result = generate_weekly(
                ctx.work_root,
                ctx.vault_dir,
                today=datetime.now(ZoneInfo(ctx.timezone)).date(),
                write=True,
            )
            msg = f"已生成周复盘 {result.review.week}"
        except Exception as exc:  # noqa: BLE001
            msg = f"生成失败：{type(exc).__name__}: {exc}"
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)

    @app.post("/ask", response_class=HTMLResponse)
    def ask_endpoint(question: str = Form("")) -> HTMLResponse:
        q = question.strip()
        if not q:
            return _dashboard(msg="请输入问题")
        return _dashboard(ask_q=q, ask_html=_ask_html(ctx.vault_dir, q))

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
