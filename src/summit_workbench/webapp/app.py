"""本地面板的 FastAPI 应用（只绑定回环地址，服务端渲染 + JSON API）。

领域逻辑全部复用 repositories/workflows：审批读页用 parse_review_page、改条目用
review_edit、应用用 apply_meeting_review；看板状态用 build_status、简报/复盘/问答用
各自 runner。Web 层只做路由与 HTML/JSON。

两种前端形态（同一套 API）：
- 构建了 webapp/static/index.html（npm run build 产物）时，/ 服务 SPA 工作台，
  交互走 /api/* JSON 端点；
- 未构建时回退为服务端渲染看板（views.render_dashboard），保证 wb web 永远可用。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

if TYPE_CHECKING:
    from summit_workbench.workflows.ask.ask import AskTurn

from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.review import CandidateDecision, ReviewEntry, RouteTarget
from summit_workbench.observability.status import build_status
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.repositories.project_registry import (
    archive_project,
    ensure_project_active,
)
from summit_workbench.repositories.project_scan import count_inbox_pending, scan_projects
from summit_workbench.repositories.review_edit import (
    ReviewEditError,
    set_decision,
    set_decisions,
    update_fields,
)
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.repositories.signal_snapshot import (
    mark_meeting_edited,
    mark_task_completed,
    mark_task_edited,
    read_snapshot,
)
from summit_workbench.webapp.api import (
    AskPayload,
    BatchDecidePayload,
    CapturePayload,
    DecidePayload,
    EditPayload,
    MeetingEditPayload,
    ProjectPayload,
    TaskCompletePayload,
    TaskEditPayload,
    brief_payload,
    review_payload,
)
from summit_workbench.webapp.build_info import (
    BuildInfoError,
    WebBuildInfo,
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.views import render_dashboard, render_plan, render_review
from summit_workbench.workflows.review_apply import (
    ApplyReport,
    MeetingCreator,
    TaskCreator,
    apply_meeting_review,
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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


def _build_meeting_creator(ctx: WebContext) -> MeetingCreator:
    """审批「新建会议」写回器：解析主日历后创建定时日程事件，返回 event_id。

    缺省结束时间 = 开始 + 60 分钟；失败（含日历写 scope 未授权）抛错由
    apply 面板层可见化。
    """
    from datetime import datetime, timedelta
    from functools import lru_cache

    from summit_workbench.providers.feishu import (
        FeishuClient,
        FeishuSession,
        create_event,
        load_feishu_config,
    )
    from summit_workbench.providers.feishu.calendar import primary_calendar_id

    @lru_cache(maxsize=1)
    def client() -> object:
        cfg = load_feishu_config()
        return FeishuClient(cfg, FeishuSession(cfg).access_token())

    def create(summary: str, start_at: str | None, end_at: str | None, candidate_id: str) -> str:
        if start_at is None:
            raise ValueError("新建会议需要开始时间")
        start = datetime.fromisoformat(start_at)
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)  # 统一按 ctx 时区解释（前端传本地 naive）
        end_iso = (
            end_at
            if end_at is not None
            else (start + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M")
        )
        calendar_id = primary_calendar_id(client())  # type: ignore[arg-type]
        return create_event(
            client(),  # type: ignore[arg-type]
            calendar_id,
            summary,
            start_at,
            end_iso,
            timezone=ctx.timezone,
        )

    return create


def _ask_html(
    vault_dir: Path, question: str, history: tuple[AskTurn, ...] = ()
) -> tuple[str, list[str]]:
    """跑一次 wb ask（可带追问上下文）并渲染为 HTML；返回 (HTML, 本次来源 id 列表)。

    模型不可用时返回可见错误；source_ids 供前端存进会话，追问时回传给后端。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError, load_model_config
    from summit_workbench.workflows.ask.ask import answer_question

    try:
        cfg = load_model_config("qa")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
        result = answer_question(vault_dir, question, cfg, api_key, prompt=prompt, history=history)
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return f'<p class="not-actionable">问答不可用：{escape(str(exc))}</p>', []

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
    source_ids = [c.source_id for c in result.sources]
    if result.sources:
        srcs = "、".join(f"[[{escape(c.source_id)}]]" for c in result.sources)
        parts.append(f'<p class="not-actionable">召回来源：{srcs}</p>')
    return "\n".join(parts), source_ids


def _run_web_import(ctx: WebContext, transcript_path: Path) -> dict[str, object]:
    """把一份本地逐字稿全自动归档 + 结构化 + 生成审批候选（复用 backfill 链路）。

    与 wb meeting import 同一套幂等逻辑；Web 侧按产品约定走全自动（不二次确认），
    软预算只报告不阻断（PRD：预算是提醒线，不是停机线）。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.observability.status import load_budget_settings
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError, load_model_config
    from summit_workbench.repositories.usage_ledger import monthly_totals
    from summit_workbench.workflows.meetings.backfill import (
        plan_backfill,
        run_backfill,
        scan_for_import,
    )

    try:
        cfg = load_model_config("meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return {"ok": False, "message": f"导入未启动（模型未配置？）：{exc}"}

    items = scan_for_import(ctx.vault_dir, transcript_path)
    if not items:
        return {"ok": False, "message": "未识别为可导入的逐字稿（需要 .md/.txt 且内容非空）"}

    month = datetime.now(ZoneInfo(ctx.timezone)).strftime("%Y-%m")
    month_spent = monthly_totals(ctx.vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(default_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)

    report = run_backfill(
        ctx.vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=True,
    )
    lines = [
        f"处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}、"
        f"生成候选 {report.candidates}"
    ]
    for result in report.results:
        if result.action == "failed":
            lines.append(f"✗ {result.item.date} {result.item.title}：{result.reason}")
    return {
        "ok": True,
        "message": "导入完成：" + "；".join(lines),
        "details": lines,
        "estimate": {
            "pending": est.pending,
            "already_done": est.already_done,
            "est_input_tokens": est.est_input_tokens,
            "est_output_tokens": est.est_output_tokens,
            "est_cost": est.est_cost,
            "currency": est.currency,
            "projected_month_cost": est.projected_month_cost,
            "soft_limit": soft_limit,
            "crosses_soft_budget": est.crosses_soft_budget,
        },
    }


def create_app(ctx: WebContext, *, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="SummitWorkbench 面板")
    spa_dir = static_dir or _STATIC_DIR
    server_instance = new_server_instance()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))

    def _build_info() -> WebBuildInfo:
        return WebBuildInfo.from_static_dir(spa_dir)

    @app.middleware("http")
    async def _cache_policy(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path == "/api/version":
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif path == "/" or path == "/static/build-meta.json":
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/static/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

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

    # ---- JSON API（SPA 工作台） ----

    @app.get("/api/version")
    def api_version() -> JSONResponse:
        """轻量 readiness + build handshake；静态构建无效时明确返回 503。"""
        try:
            info = _build_info()
        except BuildInfoError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "error": {"code": "invalid_build_manifest", "message": str(exc)},
                },
                headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
            )
        return JSONResponse(
            content=info.version_payload(
                server_instance=server_instance,
                started_at=started_at,
                mode=panel_mode,
            ),
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )

    @app.get("/api/state")
    def api_state() -> dict[str, object]:
        """看板数据：日期、状态速览、今日简报、inbox 积压。"""
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=default_config_file())
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
            }
            for p in scan_projects(ctx.work_root, ctx.vault_dir)
        ]
        payload: dict[str, object] = {
            "day": day,
            "status": status.as_dict(),
            "brief_md": brief_md,
            "brief_generated": brief_md is not None,
            "brief": brief_payload(read_snapshot(ctx.vault_dir, day)),
            "inbox_pending": inbox_pending,
            "projects": projects,
        }
        try:
            info = _build_info()
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

    def _project_dir(name: str) -> Path | None:
        """校验工作台精选的目标：必须是 ``work_root`` 的直接子目录（非 _vault、无路径分隔符）。"""
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            return None
        path = ctx.work_root / name
        if path.parent != ctx.work_root or path.name == "_vault" or not path.is_dir():
            return None
        return path

    @app.post("/api/projects/activate")
    def api_project_activate(payload: ProjectPayload) -> dict[str, object]:
        """把项目加入工作台（幂等）：无档案则建档；archived 则恢复为 active。"""
        name = payload.name.strip()
        if _project_dir(name) is None:
            return {"ok": False, "message": f"work_root 下没有该项目文件夹：{name}"}
        try:
            path = ensure_project_active(ctx.vault_dir, name)
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"加入工作台失败：{exc}"}
        return {"ok": True, "message": f"已加入工作台：{name}", "path": str(path)}

    @app.post("/api/projects/archive")
    def api_project_archive(payload: ProjectPayload) -> dict[str, object]:
        """把项目归档（幂等）：置 status: archived，不在首页显示；可随时恢复。"""
        name = payload.name.strip()
        if _project_dir(name) is None:
            return {"ok": False, "message": f"work_root 下没有该项目文件夹：{name}"}
        try:
            path = archive_project(ctx.vault_dir, name)
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"归档失败：{exc}"}
        return {"ok": True, "message": f"已归档：{name}", "path": str(path)}

    @app.get("/api/review")
    def api_review() -> dict[str, object]:
        entries, errors = _load(ctx.vault_dir)
        return review_payload(entries, errors)

    @app.post("/api/review/decide")
    def api_decide(payload: DecidePayload) -> dict[str, object]:
        try:
            set_decision(ctx.vault_dir, payload.candidate_id, CandidateDecision(payload.decision))
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"操作失败：{exc}"}
        return {"ok": True, "message": f"已更新 → {payload.decision}"}

    @app.post("/api/review/batch")
    def api_batch_decide(payload: BatchDecidePayload) -> dict[str, object]:
        try:
            updated = set_decisions(
                ctx.vault_dir, payload.candidate_ids, CandidateDecision(payload.decision)
            )
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"操作失败：{exc}"}
        return {
            "ok": True,
            "message": f"已批量更新 {updated} 条 → {payload.decision}",
            "updated": updated,
        }

    @app.post("/api/review/edit")
    def api_edit(payload: EditPayload) -> dict[str, object]:
        try:
            update_fields(
                ctx.vault_dir,
                payload.candidate_id,
                description=payload.description,
                target_project=payload.target_project,
                route=RouteTarget(payload.route) if payload.route else None,
                due_date=payload.due_date,
                start_at=payload.start_at,
                end_at=payload.end_at,
            )
        except (ReviewEditError, ValueError) as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "message": "已保存修改"}

    @app.post("/api/review/plan")
    def api_plan() -> dict[str, object]:
        try:
            report = apply_meeting_review(ctx.vault_dir, ctx.work_root, apply=False)
        except ValueError as exc:
            return {"ok": False, "message": f"预演失败：{exc}"}
        return {"ok": True, "plan_text": _plan_text(report), "executed": False}

    @app.post("/api/review/apply")
    def api_apply() -> dict[str, object]:
        try:
            report = apply_meeting_review(
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx),
                meeting_creator=_build_meeting_creator(ctx),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"应用失败：{type(exc).__name__}: {exc}"}
        return {"ok": True, "plan_text": _plan_text(report), "executed": True}

    @app.post("/api/capture")
    def api_capture(payload: CapturePayload) -> dict[str, object]:
        """快速捕捉：AI 分类（承诺/想法 + 截止 + #项目）后记入全局 inbox。

        模型不可用/超时/输出非法时按「想法」兜底，绝不丢数据；#项目 标签本地解析，
        不经模型，避免臆造项目名。分类以稳定标记写回 inbox，供 M4 wb task 承接路由。
        """
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "输入为空"}
        from summit_workbench.config.secrets import CredentialError, resolve_credential
        from summit_workbench.domain.capture import CaptureKind
        from summit_workbench.prompts import load_prompt
        from summit_workbench.providers.llm import LLMError, load_model_config
        from summit_workbench.repositories.project_registry import load_project_registry
        from summit_workbench.repositories.writeback import append_global_inbox
        from summit_workbench.workflows.capture import classify_capture, extract_project_tags

        candidate_id = f"web-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        kind: CaptureKind = CaptureKind.IDEA
        due_date: str | None = None
        model_used = False
        try:
            cfg = load_model_config("capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("capture-classifier")
            cls = classify_capture(cfg, api_key, prompt, text)
            kind = cls.kind
            due_date = cls.due_date
            model_used = True
        except (LLMError, CredentialError, FileNotFoundError, ValueError):
            # 分类不可用 → 按想法归档（不丢数据，录入永不阻塞）
            kind = CaptureKind.IDEA

        tags = extract_project_tags(text, load_project_registry(ctx.vault_dir))
        project = tags[0] if tags else None
        markers = [f"wb-capture-kind: {kind.value}"]
        if due_date:
            markers.append(f"wb-capture-due: {due_date}")
        if project:
            markers.append(f"wb-capture-project: {project}")
        path, written = append_global_inbox(ctx.vault_dir, text, candidate_id, markers=markers)
        label = "承诺" if kind is CaptureKind.TASK else "想法"
        tail = f"（截止 {due_date}）" if due_date else ""
        project_tail = f" · 关联 {project}" if project else ""
        return {
            "ok": True,
            "message": f"已记入全局 inbox · {label}{tail}{project_tail}",
            "path": str(path),
            "kind": kind.value,
            "due_date": due_date,
            "project": project,
            "model_used": model_used,
        }

    @app.post("/api/tasks/complete")
    def api_task_complete(payload: TaskCompletePayload) -> dict[str, object]:
        """把一条飞书任务标记为已完成（写回飞书 = 真源）并镜像到当日渲染快照。

        「反向完成」闭环：飞书侧完成成功后，当日快照里该任务从待办移除、计入
        「最近完成」，前端刷新即消失；下次生成简报以飞书状态为准自然收敛。
        任何失败（未授权/任务已删/网络）都可见化返回，不改本地快照。
        """
        guid = payload.task_id.strip()
        if not guid:
            return {"ok": False, "message": "缺少任务 id"}
        from summit_workbench.providers.feishu import (
            FeishuClient,
            FeishuSession,
            complete_task,
            load_feishu_config,
        )

        try:
            cfg = load_feishu_config()
            complete_task(FeishuClient(cfg, FeishuSession(cfg).access_token()), guid)
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化（授权过期/任务已删等）
            return {"ok": False, "message": f"完成失败：{type(exc).__name__}: {exc}"}
        summary = mark_task_completed(ctx.vault_dir, ctx.today(), guid)
        tail = f"：{summary}" if summary else ""
        return {"ok": True, "message": f"任务已完成{tail}", "task_id": guid}

    @app.post("/api/tasks/update")
    def api_task_update(payload: TaskEditPayload) -> dict[str, object]:
        """今日待办任务行内编辑：改标题/截止（写回飞书 = 真源）并镜像当日快照。"""
        guid = payload.task_id.strip()
        if not guid:
            return {"ok": False, "message": "缺少任务 id"}
        summary = payload.summary.strip() if payload.summary is not None else None
        if summary == "":
            return {"ok": False, "message": "任务标题不能为空"}
        due_raw = payload.due_date
        due_value: str | None = None
        clear_due = False
        if due_raw is not None:
            stripped = due_raw.strip()
            if stripped:
                due_value = stripped
            else:
                clear_due = True
        if summary is None and due_value is None and not clear_due:
            return {"ok": False, "message": "没有需要更新的内容"}
        from summit_workbench.providers.feishu import (
            FeishuClient,
            FeishuSession,
            load_feishu_config,
            update_task,
        )

        try:
            cfg = load_feishu_config()
            update_task(
                FeishuClient(cfg, FeishuSession(cfg).access_token()),
                guid,
                summary=summary,
                due_date=due_value,
                clear_due=clear_due,
                timezone=ctx.timezone,
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"保存失败：{type(exc).__name__}: {exc}"}
        mark_task_edited(
            ctx.vault_dir,
            ctx.today(),
            guid,
            summary=summary,
            due_date=due_value,
            clear_due=clear_due,
        )
        return {"ok": True, "message": "任务已更新", "task_id": guid}

    @app.post("/api/meetings/update")
    def api_meeting_update(payload: MeetingEditPayload) -> dict[str, object]:
        """今日会议行内编辑：改标题/起止时间（写回飞书日历 = 真源）并镜像当日快照。"""
        event_id = payload.event_id.strip()
        if not event_id:
            return {"ok": False, "message": "缺少会议事件 id"}
        summary = payload.summary.strip() if payload.summary is not None else None
        if summary == "":
            return {"ok": False, "message": "会议标题不能为空"}
        start_at = payload.start_at.strip() if payload.start_at else None
        end_at = payload.end_at.strip() if payload.end_at else None
        if end_at is not None and start_at is None:
            return {"ok": False, "message": "改了结束时间也要一并改开始时间"}
        if summary is None and start_at is None and end_at is None:
            return {"ok": False, "message": "没有需要更新的内容"}
        from summit_workbench.providers.feishu import (
            FeishuClient,
            FeishuSession,
            load_feishu_config,
            update_event,
        )
        from summit_workbench.providers.feishu.calendar import (
            local_iso_to_epoch_seconds,
            primary_calendar_id,
        )

        try:
            cfg = load_feishu_config()
            client = FeishuClient(cfg, FeishuSession(cfg).access_token())
            calendar_id = primary_calendar_id(client)
            update_event(
                client,
                calendar_id,
                event_id,
                summary=summary,
                start_iso=start_at,
                end_iso=end_at,
                timezone=ctx.timezone,
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"保存失败：{type(exc).__name__}: {exc}"}
        display_start = start_at[11:16] if start_at else None
        mark_meeting_edited(
            ctx.vault_dir,
            ctx.today(),
            event_id,
            summary=summary,
            start_time=display_start,
            start_ts=local_iso_to_epoch_seconds(start_at, ctx.timezone) if start_at else None,
            end_ts=local_iso_to_epoch_seconds(end_at, ctx.timezone) if end_at else None,
        )
        return {"ok": True, "message": "会议已更新", "event_id": event_id}

    @app.post("/api/run/brief")
    def api_run_brief() -> dict[str, object]:
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
            return {
                "ok": True,
                "message": f"已生成今日简报（健康度 {run.result.brief.health.level}）",
            }
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            return {"ok": False, "message": f"生成失败：{type(exc).__name__}: {exc}"}

    @app.post("/api/run/weekly")
    def api_run_weekly() -> dict[str, object]:
        from summit_workbench.workflows.weekly.weekly import generate_weekly

        try:
            result = generate_weekly(
                ctx.work_root,
                ctx.vault_dir,
                today=datetime.now(ZoneInfo(ctx.timezone)).date(),
                write=True,
            )
            return {"ok": True, "message": f"已生成周复盘 {result.review.week}"}
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            return {"ok": False, "message": f"生成失败：{type(exc).__name__}: {exc}"}

    @app.post("/api/ask")
    def api_ask(payload: AskPayload) -> dict[str, object]:
        question = payload.question.strip()
        if not question:
            return {"ok": False, "message": "请输入问题"}
        from summit_workbench.workflows.ask.ask import AskTurn

        history = tuple(
            AskTurn(question=t.question.strip(), sources=tuple(t.sources))
            for t in payload.history
            if t.question.strip()
        )
        html, source_ids = _ask_html(ctx.vault_dir, question, history=history)
        return {"ok": True, "answer_html": html, "source_ids": source_ids}

    @app.post("/api/meetings/import")
    def api_meetings_import(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        """拖拽上传逐字稿 → 全自动归档 + 结构化 + 生成审批候选。"""
        name = file.filename or "transcript.txt"
        if not name.lower().endswith((".md", ".txt")):
            return {"ok": False, "message": "仅支持 .md / .txt 逐字稿文件"}
        data = file.file.read()
        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            return {"ok": False, "message": "文件内容为空"}
        tmp_dir = Path(tempfile.mkdtemp(prefix="wb-web-import-"))
        try:
            target = tmp_dir / Path(name).name
            target.write_text(text, encoding="utf-8")
            return _run_web_import(ctx, target)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.post("/api/shutdown")
    def api_shutdown(
        x_wb_shutdown: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """关闭本地面板（网页「退出」按钮调用）。

        只允许面板页面自身触发：自定义头 ``X-WB-Shutdown`` 会强制浏览器先发 CORS
        预检，而本应用未开启跨域，外部网页无法直发——杜绝任意网页把本地服务关掉。
        收到请求后延迟片刻让响应先返回，再从独立线程退出进程。
        """
        if x_wb_shutdown != "1":
            return {"ok": False, "message": "缺少关闭令牌"}

        def _stop() -> None:
            time.sleep(0.3)
            os._exit(0)

        threading.Thread(target=_stop, daemon=True).start()
        return {"ok": True, "message": "工作台正在关闭…"}

    # ---- SSR 兼容路由（旧入口与既有测试继续可用） ----

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
        html, _source_ids = _ask_html(ctx.vault_dir, q)
        return _dashboard(ask_q=q, ask_html=html)

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
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx),
                meeting_creator=_build_meeting_creator(ctx),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            detail = f"应用失败：{type(exc).__name__}: {exc}"
            return HTMLResponse(render_plan(detail, executed=True))
        return HTMLResponse(render_plan(_plan_text(report), executed=True))

    return app
