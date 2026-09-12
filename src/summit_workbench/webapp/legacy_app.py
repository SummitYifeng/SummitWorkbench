"""本地面板的 FastAPI 应用（只绑定回环地址，服务端渲染 + JSON API）。

领域逻辑全部复用 repositories/workflows：审批读页用 parse_review_page、改条目用
review_edit、应用用 apply_meeting_review；看板状态用 build_status、简报/复盘/问答用
各自 runner。Web 层只做路由与 HTML/JSON。

两种前端形态（同一套 API）：
- 构建了 webapp/static/index.html（npm run build 产物）时，/ 服务 SPA 工作台，
  交互走 /api/* JSON 端点；
- 未构建时回退为服务端渲染看板（views.render_dashboard），保证 wb web 永远可用。
"""
# ruff: noqa: E501

from __future__ import annotations

import inspect
import os
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from summit_workbench.providers.llm.config import ModelConfig
    from summit_workbench.workflows.ask.ask import AskTurn

from summit_workbench.domain.threaddoc import ArtifactIndex, ArtifactKind, LogDigest
from summit_workbench.domain.workspace import DeviceRole
from summit_workbench.observability.status import build_status
from summit_workbench.repositories.autocommit import (
    CommitStatus,
    commit_diff_text,
    list_wb_commits,
    revert_commit,
    undo_error_code,
)
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.repositories.project_registry import (
    load_project_registry,
)
from summit_workbench.repositories.signal_snapshot import (
    mark_meeting_edited,
    mark_task_completed,
    mark_task_edited,
    snapshot_path,
)
from summit_workbench.repositories.thread_notes import (
    append_work_log,
    save_thread_artifact,
)
from summit_workbench.webapp.api import (
    ArtifactSavePayload,
    AskPayload,
    CapturePayload,
    LogAppendPayload,
    MeetingEditPayload,
    OnboardingCreatePayload,
    OnboardingPreflightPayload,
    OnboardingVaultPayload,
    ProjectStatePayload,
    TaskCompletePayload,
    TaskEditPayload,
    UndoRevertPayload,
)
from summit_workbench.webapp.build_info import (
    WebBuildInfo,
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.context import WebContext as WebContext
from summit_workbench.webapp.feishu_pool import (
    _FeishuClientPool,
)
from summit_workbench.webapp.knowledge_sources import (
    KNOWLEDGE_SOURCE_ROOTS as KNOWLEDGE_SOURCE_ROOTS,
)
from summit_workbench.webapp.knowledge_sources import (
    SOURCE_BODY_DISPLAY_CHARS as SOURCE_BODY_DISPLAY_CHARS,
)
from summit_workbench.webapp.knowledge_sources import (
    _is_knowledge_source as _is_knowledge_source,
)
from summit_workbench.webapp.mutation_response import (
    _commit_note,
    _mutation_fields,
)
from summit_workbench.webapp.mutation_runtime import (
    MutationRuntime,
)
from summit_workbench.webapp.mutation_runtime import (
    _commit_suffix as _commit_suffix,
)
from summit_workbench.webapp.request_boundary import (
    _SCHEMA_UPGRADE_WRITE_EXEMPTIONS as _SCHEMA_UPGRADE_WRITE_EXEMPTIONS,
)
from summit_workbench.webapp.request_boundary import (
    install_cache_policy,
    install_exception_handlers,
    install_security_boundary,
)
from summit_workbench.webapp.restricted_app import (
    _STATIC_DIR as _STATIC_DIR,
)
from summit_workbench.webapp.restricted_app import (
    create_restricted_app,
)
from summit_workbench.webapp.routers.review import (
    register_review_page_routes,
    register_review_routes,
)
from summit_workbench.webapp.routers.review_apply import (
    register_review_apply_page_routes,
    register_review_apply_routes,
)
from summit_workbench.webapp.routers.settings import register_settings_routes
from summit_workbench.webapp.routers.state import register_state_routes
from summit_workbench.webapp.routers.sync import register_sync_routes
from summit_workbench.webapp.security import (
    allowed_hosts,
    error_payload,
    validate_bind_host,
)
from summit_workbench.webapp.views import render_dashboard
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
    run_local_mutation,
)
from summit_workbench.workflows.thread_activity_migration import (
    ThreadActivityConsistencyReport,
    ThreadActivityMigration,
    ThreadActivityMigrationMode,
)

_create_restricted_app = create_restricted_app

# Remote normalization is the controlled escape hatch that lets an old-schema
# workspace become migratable.  It only changes the local origin/profile and
# workspace-scoped credential after a temporary-clone validation; it does not
# write vault content, create commits, or push.  Without this exemption the
# migration gate requires HTTPS while the read-only gate prevents the only
# operation that can establish HTTPS (a deadlock).


def _load_model_config_for_context(ctx: WebContext, capability: str) -> ModelConfig:
    """Load legacy test/development config without changing its monkeypatch contract."""
    from summit_workbench.workflows.settings_connections import model_config

    if ctx.workspace_id is None:
        from summit_workbench.providers.llm import load_model_config

        return load_model_config(capability)
    return model_config(
        capability=capability,
        config_file=ctx.provider_config_file(),
        workspace_id=ctx.workspace_id,
    )


def _thread_activity_migration(ctx: WebContext) -> ThreadActivityMigration | None:
    """Create the P2-01B seam only for a frozen production workspace context."""
    if ctx.active_workspace is None or not ctx.workspace_id or not ctx.active_workspace.device_id:
        return None
    return ThreadActivityMigration.from_environment(
        ctx.vault_dir,
        workspace_id=ctx.workspace_id,
        device_id=ctx.active_workspace.device_id,
    )


def _undo_error_response(code: str, message: str, *, operation_id: str = "unknown") -> JSONResponse:
    """返回撤销 API 的稳定 4xx 错误 envelope。"""
    status_code = {
        "undo_invalid_commit": 422,
        "undo_target_dirty": 409,
        "undo_not_git": 409,
        "undo_busy": 423,
    }.get(code, 409)
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code=code, message=message, operation_id=operation_id),
    )


def _cited_source_ids(answer: dict[str, object] | None) -> list[str]:
    if not answer:
        return []
    cited: set[str] = set()
    facts = answer.get("facts")
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict) and isinstance(fact.get("source_id"), str):
                cited.add(fact["source_id"])
    conflicts = answer.get("conflicts")
    if isinstance(conflicts, list):
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            sides = conflict.get("sides")
            if isinstance(sides, list):
                for side in sides:
                    if isinstance(side, dict) and isinstance(side.get("source_id"), str):
                        cited.add(side["source_id"])
    return sorted(cited)


def _ask_html(
    vault_dir: Path,
    question: str,
    history: tuple[AskTurn, ...] = (),
    project: str | None = None,
    *,
    config_file: Path | None = None,
    workspace_id: str | None = None,
) -> tuple[str, list[str], dict[str, object] | None]:
    """跑一次 wb ask（可带追问上下文与项目/线程范围）并渲染为 HTML。

    模型不可用时返回可见错误；source_ids 供前端存进会话，追问时回传给后端。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError, load_model_config
    from summit_workbench.workflows.ask.ask import answer_question

    try:
        if config_file is None and workspace_id is None:
            cfg = load_model_config("qa")
        else:
            cfg = load_model_config("qa", config_file, workspace_id=workspace_id)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
        result = answer_question(
            vault_dir, question, cfg, api_key, prompt=prompt, history=history, project=project
        )
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return f'<p class="not-actionable">问答不可用：{escape(str(exc))}</p>', [], None

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
    return "\n".join(parts), source_ids, answer.model_dump(mode="json")


def _run_web_import(
    ctx: WebContext,
    transcript_path: Path,
    *,
    local_mutation: Callable[..., object] | None = None,
) -> dict[str, object]:
    """把一份本地逐字稿全自动归档 + 结构化 + 生成审批候选（复用 backfill 链路）。

    与 wb meeting import 同一套幂等逻辑；Web 侧按产品约定走全自动（不二次确认），
    软预算只报告不阻断（PRD：预算是提醒线，不是停机线）。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.observability.status import load_budget_settings
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError
    from summit_workbench.repositories.usage_ledger import monthly_totals
    from summit_workbench.workflows.meetings.backfill import (
        plan_backfill,
        run_backfill,
        scan_for_import,
    )

    items = scan_for_import(ctx.vault_dir, transcript_path)
    if not items:
        return {"ok": False, "message": "未识别为可导入的逐字稿（需要 .md/.txt 且内容非空）"}

    # 先检查幂等账本：重复导入已经完成的逐字稿不应因为当前模型凭据不可用而
    # 被误报为“模型未配置”，也不应再次调用模型或写入归档。
    if all(item.done for item in items):
        skipped = len(items)
        lines = [f"处理 0、跳过 {skipped}、失败 0、生成候选 0"]
        return {
            "ok": True,
            "status": "success",
            "message": "导入完成：" + "；".join(lines) + "（幂等，未重复调用模型）",
            "details": lines,
            "operation_ids": [],
            "estimate": {
                "pending": 0,
                "already_done": skipped,
                "est_input_tokens": 0,
                "est_output_tokens": 0,
                "est_cost": 0,
                "currency": "—",
                "projected_month_cost": 0,
                "soft_limit": None,
                "crosses_soft_budget": False,
            },
        }

    try:
        cfg = _load_model_config_for_context(ctx, "meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return {"ok": False, "status": "failed", "message": f"导入未启动（模型未配置？）：{exc}"}

    month = datetime.now(ZoneInfo(ctx.timezone)).strftime("%Y-%m")
    month_spent = monthly_totals(ctx.vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(ctx.provider_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)

    report = run_backfill(
        ctx.vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=True,
        local_mutation=local_mutation or run_local_mutation,
    )
    lines = [
        f"处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}、"
        f"生成候选 {report.candidates}"
    ]
    for result in report.results:
        if result.action == "failed":
            lines.append(f"✗ {result.item.date} {result.item.title}：{result.reason}")
    operation_ids = list(report.operation_ids)
    operation_note = f" · operation_id：{operation_ids[-1]}" if operation_ids else ""
    status = (
        "success"
        if report.failed == 0
        else ("partial" if report.processed or report.skipped else "failed")
    )
    message_prefix = {
        "success": "导入完成：",
        "partial": "导入部分完成：",
        "failed": "导入失败：",
    }[status]
    return {
        "ok": report.failed == 0,
        "status": status,
        "message": message_prefix + "；".join(lines) + operation_note,
        "details": lines,
        "operation_ids": operation_ids,
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


# Step 1（LEGACY-APP-SPLIT-PLAN）：知识来源白名单与正文展示预算已抽到
# ``webapp/knowledge_sources.py``，并在文件顶部再导出（见那里的注释）。


def create_app(
    ctx: WebContext | None,
    *,
    static_dir: Path | None = None,
    bind_host: str = "127.0.0.1",
    port: int = 8787,
    session_token: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    server_instance: str | None = None,
) -> FastAPI:
    if ctx is None:
        context = getattr(ctx, "active_workspace", None)
        if context is None:
            from summit_workbench.config.profiles import resolve_active_workspace

            context = resolve_active_workspace(allow_env_fallback=False)
        return create_restricted_app(
            context,
            static_dir=static_dir,
            bind_host=bind_host,
            port=port,
            session_token=session_token,
            workspace_id=workspace_id,
            device_id=device_id,
            server_instance=server_instance,
        )

    feishu_clients = _FeishuClientPool(
        lock_root=ctx.lock_root,
        config_file=ctx.config_file,
        workspace_id=ctx.workspace_id,
    )
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))
    validate_bind_host(bind_host, panel_mode)
    normalized_bind_host = bind_host.strip().strip("[]").lower()
    external_bind = normalized_bind_host not in {
        "127.0.0.1",
        "::1",
    }
    host_allowlist = allowed_hosts(bind_host, port, include_test_alias=panel_mode != "production")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            feishu_clients.close()

    app = FastAPI(title="SummitWorkbench 面板", lifespan=lifespan)
    app.state.feishu_clients = feishu_clients
    spa_dir = static_dir or _STATIC_DIR
    server_instance = server_instance or new_server_instance()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _operation_id(request: Request) -> str:
        operation_id = getattr(request.state, "operation_id", None)
        return str(operation_id or "unknown")

    runtime = MutationRuntime(ctx, operation_id=_operation_id)

    install_exception_handlers(app, operation_id=_operation_id)

    install_security_boundary(
        app,
        ctx=ctx,
        port=port,
        host_allowlist=host_allowlist,
        panel_mode=panel_mode,
        external_bind=external_bind,
        session_token=session_token,
    )

    def _build_info() -> WebBuildInfo:
        return WebBuildInfo.from_static_dir(spa_dir)

    install_cache_policy(app)

    def _dashboard(
        msg: str | None = None, ask_q: str = "", ask_html: str | None = None
    ) -> HTMLResponse:
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=ctx.provider_config_file())
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

    from summit_workbench.webapp.dependencies import RouteDependencies
    from summit_workbench.webapp.routers.system import register_system_routes

    register_system_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        static_dir=spa_dir,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
        session_token=session_token,
        workspace_id=workspace_id,
        device_id=device_id,
        build_info=_build_info,
    )

    register_review_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_review_apply_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        feishu_clients=feishu_clients,
    )

    @app.post("/api/threads/state")
    def api_set_project_state(payload: ProjectStatePayload) -> dict[str, object]:
        """把主档案「当前状态」区块替换为一段文本（产物摘要 → 状态草案，显式确认后写回）。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "状态内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(payload.project.strip())
        if project is None:
            return {"ok": False, "message": f"项目未建档：{payload.project.strip()}"}

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            from summit_workbench.repositories.note_status import update_note_status
            from summit_workbench.repositories.vault import load_note as _load_note
            from summit_workbench.repositories.writeback import set_project_status

            path, _written = set_project_status(ctx.vault_dir, project, text)
            note = _load_note(path)
            status = note.meta.get("status")
            if isinstance(status, str):
                update_note_status(ctx.vault_dir, path, status, extra={"updated": ctx.today()})
            return LocalMutationOutcome(path, (path,))

        try:
            result = runtime.run("threads/state", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"更新失败：{exc}"}
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已更新 {project} 当前状态{git_note}",
            "project": project,
            **_mutation_fields(result),
        }

    from summit_workbench.webapp.routers.projects import register_project_read_routes

    register_project_read_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id)
    )

    @app.get("/api/threads/activity-consistency")
    def api_thread_activity_consistency() -> dict[str, object]:
        """Return the deterministic old/new report for the P2-01B event slice."""
        migration = _thread_activity_migration(ctx)
        if migration is None:
            report = ThreadActivityConsistencyReport(
                mode=ThreadActivityMigrationMode.LEGACY,
                status="disabled",
            )
        else:
            report = migration.inspect()
        return {"ok": report.ok, "thread_activity_consistency": report.as_dict()}

    @app.post("/api/threads/logs")
    def api_append_log(payload: LogAppendPayload) -> dict[str, object]:
        """追加推进日志（可关联多线程）；AI 消化是加分项，任何失败只存原文。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "日志内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        resolved: list[str] = []
        for name in payload.projects:
            cid = registry.resolve(name) or name
            if cid and cid in registry.canonical and cid not in resolved:
                resolved.append(cid)
        if not resolved:
            return {"ok": False, "message": "没有可关联的项目/线程（先在「项目」页建档）"}

        digest: LogDigest | None = None
        enriched = False
        try:
            from summit_workbench.config.secrets import CredentialError, resolve_credential
            from summit_workbench.prompts import load_prompt
            from summit_workbench.providers.llm import LLMError
            from summit_workbench.workflows.threadnotes import digest_log

            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("log-digest")
            digest = digest_log(cfg, api_key, prompt, text, project_hints=resolved)
            enriched = True
        except (LLMError, CredentialError, FileNotFoundError, ValueError):
            digest = None

        summary = digest.summary if digest else ""
        involved = digest.involved if digest else []
        tags = digest.tags if digest else []

        archives = [ctx.vault_dir / "projects" / f"{p}.md" for p in resolved]
        activity_migration = _thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = append_work_log(
                ctx.vault_dir,
                projects=resolved,
                text=text,
                summary=summary,
                involved=involved,
                tags=tags,
                next_step=digest.next_step if digest else None,
                decision=digest.decision if digest else None,
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            report = activity_migration.last_report.as_dict() if activity_migration else None
            changed_paths = (
                path,
                *archives,
                *(activity_migration.last_write_paths if activity_migration else ()),
            )
            return LocalMutationOutcome(changed_paths[0], changed_paths[1:], report)

        try:
            result = runtime.run("threads/logs", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        tail = f" · 摘要：{summary}" if summary else "（模型不可用，仅存原文）"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已追加推进日志 → {len(resolved)} 个线程 · {tail}{git_note}",
            "path": str(path),
            "summary": summary,
            "enriched": enriched,
            **_mutation_fields(result),
        }

    @app.post("/api/threads/artifacts")
    def api_save_artifact(payload: ArtifactSavePayload) -> dict[str, object]:
        """把 AI 产物（阶段总结/PRD/背景包等）存入线程档案并生成索引。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "产物内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(payload.project.strip())
        if project is None:
            return {
                "ok": False,
                "message": f"项目未建档：{payload.project.strip()}（先在「项目」页建档再存产物）",
            }
        title_hint = (payload.title or "").strip()
        index: ArtifactIndex | None = None
        enriched = False
        try:
            from summit_workbench.config.secrets import CredentialError, resolve_credential
            from summit_workbench.prompts import load_prompt
            from summit_workbench.providers.llm import LLMError
            from summit_workbench.workflows.threadnotes import index_artifact

            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("artifact-index")
            index = index_artifact(cfg, api_key, prompt, text, title_hint=title_hint)
            enriched = True
        except (LLMError, CredentialError, FileNotFoundError, ValueError):
            index = None

        title = (index.title if index and index.title else title_hint) or ""
        summary = index.summary if index else ""
        kind = index.kind if index else ArtifactKind.OTHER
        activity_migration = _thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = save_thread_artifact(
                ctx.vault_dir,
                project=project,
                text=text,
                title=title,
                summary=summary,
                kind=kind,
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            report = activity_migration.last_report.as_dict() if activity_migration else None
            changed_paths = (
                path,
                ctx.vault_dir / "projects" / f"{project}.md",
                *(activity_migration.last_write_paths if activity_migration else ()),
            )
            return LocalMutationOutcome(changed_paths[0], changed_paths[1:], report)

        try:
            result = runtime.run("threads/artifacts", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        tail = f" · 摘要：{summary}" if summary else "（模型不可用，仅存原文）"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已存入 {project} 档案 · {tail}{git_note}",
            "path": str(path),
            "title": title,
            "summary": summary,
            "enriched": enriched,
            **_mutation_fields(result),
        }

    @app.post("/api/capture", response_model=None)
    def api_capture(request: Request, payload: CapturePayload) -> dict[str, object] | JSONResponse:
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
        from summit_workbench.providers.llm import LLMError
        from summit_workbench.repositories.project_registry import load_project_registry
        from summit_workbench.repositories.writeback import append_global_inbox
        from summit_workbench.workflows.capture import classify_capture, extract_project_tags

        candidate_id = f"web-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        kind: CaptureKind = CaptureKind.IDEA
        due_date: str | None = None
        model_used = False
        try:
            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("capture-classifier")
            cls = classify_capture(
                cfg,
                api_key,
                prompt,
                text,
                today=datetime.now(ZoneInfo(ctx.timezone)).date().isoformat(),
            )
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

        def mutate(_operation_id: str) -> LocalMutationOutcome[tuple[Path, bool]]:
            path, written = append_global_inbox(ctx.vault_dir, text, candidate_id, markers=markers)
            return LocalMutationOutcome((path, written), (path,))

        result = runtime.run("capture", mutate)
        path, written = result.business_return
        label = "承诺" if kind is CaptureKind.TASK else "想法"
        tail = f"（截止 {due_date}）" if due_date else ""
        project_tail = f" · 关联 {project}" if project else ""
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已记入全局 inbox · {label}{tail}{project_tail}{git_note}",
            "path": str(path),
            "kind": kind.value,
            "due_date": due_date,
            "project": project,
            "model_used": model_used,
            **_mutation_fields(result),
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
        from summit_workbench.providers.feishu import complete_task

        try:
            complete_task(feishu_clients.user_client(), guid)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化（授权过期/任务已删等）
            return {"ok": False, "message": f"完成失败：{type(exc).__name__}: {exc}"}
        result = runtime.run(
            "tasks/complete",
            lambda _operation_id: LocalMutationOutcome(
                mark_task_completed(ctx.vault_dir, ctx.today(), guid),
                (snapshot_path(ctx.vault_dir, ctx.today()),),
            ),
        )
        summary = result.business_return
        tail = f"：{summary}" if summary else ""
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"任务已完成{tail}{git_note}",
            "task_id": guid,
            **_mutation_fields(result),
        }

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
        from summit_workbench.providers.feishu import update_task

        try:
            update_task(
                feishu_clients.user_client(),  # type: ignore[arg-type]
                guid,
                summary=summary,
                due_date=due_value,
                clear_due=clear_due,
                timezone=ctx.timezone,
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"保存失败：{type(exc).__name__}: {exc}"}
        result = runtime.run(
            "tasks/update",
            lambda _operation_id: LocalMutationOutcome(
                mark_task_edited(
                    ctx.vault_dir,
                    ctx.today(),
                    guid,
                    summary=summary,
                    due_date=due_value,
                    clear_due=clear_due,
                ),
                (snapshot_path(ctx.vault_dir, ctx.today()),),
            ),
        )
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"任务已更新{git_note}",
            "task_id": guid,
            **_mutation_fields(result),
        }

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
        from summit_workbench.providers.feishu import update_event
        from summit_workbench.providers.feishu.calendar import (
            local_iso_to_epoch_seconds,
            primary_calendar_id,
        )

        try:
            client = feishu_clients.user_client()
            calendar_id = primary_calendar_id(client)  # type: ignore[arg-type]
            update_event(
                client,  # type: ignore[arg-type]
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
        result = runtime.run(
            "meetings/update",
            lambda _operation_id: LocalMutationOutcome(
                mark_meeting_edited(
                    ctx.vault_dir,
                    ctx.today(),
                    event_id,
                    summary=summary,
                    start_time=display_start,
                    start_ts=local_iso_to_epoch_seconds(start_at, ctx.timezone)
                    if start_at
                    else None,
                    end_ts=local_iso_to_epoch_seconds(end_at, ctx.timezone) if end_at else None,
                ),
                (snapshot_path(ctx.vault_dir, ctx.today()),),
            ),
        )
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"会议已更新{git_note}",
            "event_id": event_id,
            **_mutation_fields(result),
        }

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
                today=datetime.now(ZoneInfo(ctx.timezone)).date(),
                write=True,
            )
            return {"ok": True, "message": f"已生成周复盘 {result.review.week}"}
        except Exception as exc:  # noqa: BLE001 - 面板需把失败可见化
            return {"ok": False, "message": f"生成失败：{type(exc).__name__}: {exc}"}

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

    @app.post("/api/meetings/import")
    def api_meetings_import(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        """拖拽上传逐字稿 → 全自动归档 + 结构化 + 生成审批候选。"""
        from summit_workbench.workflows.meetings.backfill import MAX_TRANSCRIPT_BYTES

        max_upload_bytes = MAX_TRANSCRIPT_BYTES
        chunk_size = 64 * 1024
        name = (file.filename or "transcript.txt")[:200]
        if not name.lower().endswith((".md", ".txt")):
            return {"ok": False, "message": "仅支持 .md / .txt 逐字稿文件"}
        buffer = BytesIO()
        total = 0
        while True:
            chunk = file.file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "upload_too_large",
                        "message": "逐字稿文件不能超过 10 MiB",
                    },
                )
            buffer.write(chunk)
        data = buffer.getvalue()
        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            return {"ok": False, "message": "文件内容为空"}
        tmp_dir = Path(tempfile.mkdtemp(prefix="wb-web-import-"))
        try:
            target = tmp_dir / Path(name).name
            target.write_text(text, encoding="utf-8")
            if "local_mutation" in inspect.signature(_run_web_import).parameters:
                return _run_web_import(ctx, target, local_mutation=runtime.run)
            # 保持旧版/测试注入器的二参数兼容性；正式实现始终走集中式写入门。
            return _run_web_import(ctx, target)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- 撤销系统自动提交（P0'） ----

    @app.get("/api/undo/history")
    def api_undo_history() -> dict[str, object]:
        """最近 ``wb:`` 自动提交列表（含每提交触碰文件与仓库状态）。"""
        commits, error = list_wb_commits(ctx.vault_dir, limit=20)
        if error == "not-git":
            return {
                "ok": True,
                "commits": [],
                "note": "vault 不是 git 仓库：系统写回不会自动留痕，也无法撤销",
            }
        if error is not None:
            return {"ok": False, "message": f"读取提交历史失败：{error}"}
        return {"ok": True, "commits": [c.as_dict() for c in commits], "note": None}

    @app.get("/api/undo/diff", response_model=None)
    def api_undo_diff(request: Request, sha: str) -> dict[str, object] | JSONResponse:
        """某次 wb 提交的 before/after 差异（git show 输出），供撤销前预览。"""
        text, error = commit_diff_text(ctx.vault_dir, sha)
        if error is not None:
            code = undo_error_code(error)
            return _undo_error_response(
                code, f"无法读取差异：{error}", operation_id=_operation_id(request)
            )
        return {"ok": True, "diff": text}

    @app.post("/api/undo/revert", response_model=None)
    def api_undo_revert(
        request: Request, payload: UndoRevertPayload
    ) -> dict[str, object] | JSONResponse:
        """还原一次 wb 自动提交（等价 git revert；只作用于 vault 文件）。"""
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        sha = payload.sha.strip()
        if not sha:
            return _undo_error_response(
                "undo_invalid_commit", "缺少提交 sha", operation_id=_operation_id(request)
            )
        result = revert_commit(ctx.vault_dir, sha)
        if result.status is CommitStatus.REVERTED:
            # 明示边界：飞书侧副作用（已建任务/会议、已完成状态）不可撤销。
            return {
                "ok": True,
                "message": "已还原 vault 文件。注意：飞书侧已产生的副作用（已建任务/会议、"
                "已完成状态）不可撤销、不受本次还原影响。" + (result.detail or ""),
            }
        if result.status is CommitStatus.NOT_GIT:
            return _undo_error_response(
                "undo_not_git", "vault 不是 git 仓库，无法撤销", operation_id=_operation_id(request)
            )
        code = {
            "invalid-wb-commit": "undo_invalid_commit",
            "undo-target-dirty": "undo_target_dirty",
            "workspace-locked": "undo_busy",
        }.get(result.error_code or "", "undo_failed")
        return _undo_error_response(
            code,
            f"还原失败：{result.detail or result.status.value}",
            operation_id=_operation_id(request),
        )

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
                today=datetime.now(ZoneInfo(ctx.timezone)).date(),
                write=True,
            )
            msg = f"已生成周复盘 {result.review.week}"
        except Exception as exc:  # noqa: BLE001
            msg = f"生成失败：{type(exc).__name__}: {exc}"
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)

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

    register_review_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    register_review_apply_page_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        feishu_clients=feishu_clients,
    )

    # ---- onboarding 服务 API（P0-08：服务 + API，无 UI） ----

    from summit_workbench.domain.onboarding import OnboardingFlow
    from summit_workbench.workflows import onboarding as onboarding_service

    def _onboarding_rejected(
        request: Request, exc: onboarding_service.OnboardingError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="onboarding_rejected",
                message=str(exc),
                operation_id=_operation_id(request),
                details={"reasons": exc.reasons},
            ),
        )

    @app.get("/api/onboarding/status", response_model=None)
    def api_onboarding_status() -> dict[str, object]:
        """当前 workspace 解析状态：active / env-compat / onboarding-required。"""
        from summit_workbench.config.profiles import resolve_workspace

        resolution = resolve_workspace()
        return {
            "ok": True,
            "state": resolution.state.value,
            "workspace_id": resolution.profile.workspace_id if resolution.profile else None,
            "reason": resolution.reason,
        }

    @app.post("/api/onboarding/preflight", response_model=None)
    def api_onboarding_preflight(
        request: Request, payload: Annotated[OnboardingPreflightPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """只读预演：返回结构化预检报告（不写任何文件）。"""
        try:
            report = onboarding_service.preflight(
                OnboardingFlow(payload.flow),
                Path(payload.path).expanduser(),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        return {"ok": True, "report": report.model_dump(mode="json")}

    @app.post("/api/onboarding/create", response_model=None)
    def api_onboarding_create(
        request: Request, payload: Annotated[OnboardingCreatePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """create-new：全新工作区（staging + 原子改名 + marker + profile，失败回滚）。"""
        try:
            result = onboarding_service.create_workspace(
                Path(payload.work_root).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/upgrade", response_model=None)
    def api_onboarding_upgrade(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """upgrade-existing：旧 vault 升级（备份 + marker + profile，内容不动）。"""
        try:
            result = onboarding_service.upgrade_workspace(
                Path(payload.vault_dir).expanduser(),
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/connect", response_model=None)
    def api_onboarding_connect(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        """connect-local：连接已 clone/拷贝的带 marker vault（建档 + 置 active）。"""
        try:
            result = onboarding_service.connect_workspace(
                Path(payload.vault_dir).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                home=ctx.active_workspace.home if ctx.active_workspace else None,
            )
        except onboarding_service.OnboardingError as exc:
            return _onboarding_rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=ctx.active_workspace.home if ctx.active_workspace else None)
        return {"ok": True, **result.model_dump(mode="json")}

    # ---- workspace schema migration（P1-02；P1-03 router 接线）----

    from summit_workbench.webapp.routers.workspace import register_workspace_routes

    register_state_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        build_info=_build_info,
        server_instance=server_instance,
        started_at=started_at,
        panel_mode=panel_mode,
    )
    from summit_workbench.webapp.routers.projects import register_project_write_routes

    register_project_write_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        run_mutation=lambda action, mutation: runtime.run(action, mutation),
    )

    register_settings_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
        build_info=_build_info,
    )
    register_workspace_routes(RouteDependencies(app=app, context=ctx, operation_id=_operation_id))

    # ---- 多设备同步（P0-10）----

    register_sync_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        runtime=runtime,
    )

    return app
