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
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

if TYPE_CHECKING:
    from summit_workbench.providers.llm.config import ModelConfig
    from summit_workbench.workflows.ask.ask import AskTurn

from summit_workbench import __version__
from summit_workbench.config.git_credentials import profile_identity
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.automation import AutomationJob
from summit_workbench.domain.review import CandidateDecision, ReviewEntry, RouteTarget
from summit_workbench.domain.sync_conflict import explain_conflict, plan_conflict_recovery
from summit_workbench.domain.threaddoc import ArtifactIndex, ArtifactKind, LogDigest
from summit_workbench.domain.workspace import Compatibility, DeviceRole
from summit_workbench.observability.status import build_status
from summit_workbench.repositories.autocommit import (
    CommitStatus,
    commit_diff_text,
    commit_paths,
    list_wb_commits,
    revert_commit,
    undo_error_code,
)
from summit_workbench.repositories.daily_note import read_brief_block
from summit_workbench.repositories.external_action_outbox import (
    latest_action,
    latest_actions,
)
from summit_workbench.repositories.git import GitError
from summit_workbench.repositories.project_registry import (
    load_project_registry,
)
from summit_workbench.repositories.project_scan import (
    count_inbox_pending,
    scan_all_projects,
)
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
    snapshot_path,
)
from summit_workbench.repositories.thread_notes import (
    append_work_log,
    save_thread_artifact,
)
from summit_workbench.webapp.api import (
    AcceptancePreflightPayload,
    ArtifactSavePayload,
    AskPayload,
    AutomationPrimaryPayload,
    AutomationRunPayload,
    AutomationSettingsPayload,
    BatchDecidePayload,
    CapturePayload,
    DecidePayload,
    DoctorPayload,
    EditPayload,
    ExternalActionReconcilePayload,
    GitRemoteNormalizationPayload,
    GitRemoteNormalizationPlanPayload,
    GitRemoteRollbackPayload,
    LogAppendPayload,
    MeetingEditPayload,
    OnboardingCreatePayload,
    OnboardingDraftPayload,
    OnboardingPreflightPayload,
    OnboardingRemoteConfirmPayload,
    OnboardingRemoteStagePayload,
    OnboardingVaultPayload,
    ProfileRemovePayload,
    ProfileSwitchCommitPayload,
    ProfileSwitchPayload,
    ProjectStatePayload,
    ProviderSettingsPayload,
    SyncConflictRecoveryPayload,
    SyncConflictSelectionPayload,
    TaskCompletePayload,
    TaskEditPayload,
    UndoRevertPayload,
    brief_payload,
    external_action_payload,
    review_payload,
)
from summit_workbench.webapp.build_info import (
    BuildInfoError,
    WebBuildInfo,
    discover_build_number,
    mode_from_environment,
    new_server_instance,
)
from summit_workbench.webapp.context import WebContext as WebContext
from summit_workbench.webapp.mutation_response import (
    _commit_note,
    _mutation_fields,
)
from summit_workbench.webapp.security import (
    SESSION_COOKIE,
    SESSION_HEADER,
    allowed_hosts,
    error_payload,
    origin_matches,
    session_token_matches,
    validate_bind_host,
)
from summit_workbench.webapp.views import render_dashboard, render_plan, render_review
from summit_workbench.workflows.acceptance_preflight import acceptance_preflight
from summit_workbench.workflows.external_actions import (
    authorize_retry,
    reconcile_not_found,
    reconcile_succeeded,
    workspace_id_for_vault,
)
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
    LocalMutationResult,
    MutationBlocked,
    run_local_mutation,
)
from summit_workbench.workflows.profile_settings import (
    ProfileSettingsError,
    ProfileSwitchPlan,
    commit_profile_switch,
    list_profile_summaries,
    prepare_profile_switch,
    remove_local_profile,
    update_provider_settings,
)
from summit_workbench.workflows.remote_normalization import (
    RemoteNormalizationError,
    RemoteNormalizationPlan,
    apply_remote_normalization,
    preview_remote_normalization,
    rollback_remote_normalization,
)
from summit_workbench.workflows.review_apply import (
    ApplyReport,
    MeetingCreator,
    TaskCreator,
    apply_meeting_review,
)
from summit_workbench.workflows.thread_activity_migration import (
    ThreadActivityConsistencyReport,
    ThreadActivityMigration,
    ThreadActivityMigrationMode,
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Remote normalization is the controlled escape hatch that lets an old-schema
# workspace become migratable.  It only changes the local origin/profile and
# workspace-scoped credential after a temporary-clone validation; it does not
# write vault content, create commits, or push.  Without this exemption the
# migration gate requires HTTPS while the read-only gate prevents the only
# operation that can establish HTTPS (a deadlock).
_SCHEMA_UPGRADE_WRITE_EXEMPTIONS = frozenset(
    {
        "/api/settings/git/remote/preview",
        "/api/settings/git/remote/apply",
        "/api/settings/git/remote/rollback",
        "/api/settings/acceptance-preflight",
    }
)


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


class _FeishuClientPool:
    """按身份复用飞书客户端，并由 App lifespan 统一释放。

    P0-06：会话携带本工作区 lock root，Feishu refresh 与同 workspace 写者锁同一把
    ``.wb.lock``，不再默认落到 ``~/Documents/Work``。
    """

    def __init__(
        self,
        lock_root: Path | None = None,
        *,
        config_file: Path | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self._clients: dict[str, object] = {}
        self._lock = threading.Lock()
        self._lock_root = lock_root
        self._config_file = config_file
        self._workspace_id = workspace_id

    def _get(self, identity: str) -> object:
        with self._lock:
            existing = self._clients.get(identity)
            if existing is not None:
                return existing
            from summit_workbench.providers.feishu import (
                FeishuClient,
                FeishuSession,
                load_feishu_config,
            )

            if self._workspace_id is not None:
                from summit_workbench.workflows.settings_connections import feishu_config

                cfg = feishu_config(
                    config_file=self._config_file or default_config_file(),
                    workspace_id=self._workspace_id,
                )
            elif self._config_file is None:
                cfg = load_feishu_config()
            else:
                cfg = load_feishu_config(self._config_file)
            session = FeishuSession(cfg, lock_root=self._lock_root)
            if identity == "user":
                token = session.access_token()
                if "token_provider" in inspect.signature(FeishuClient).parameters:
                    client = FeishuClient(
                        cfg,
                        token,
                        token_provider=session.access_token,
                        token_invalidator=session.invalidate_access_token,
                    )
                else:  # compatibility with injected legacy/test clients
                    client = FeishuClient(cfg, token)
            else:
                token = session.tenant_access_token()
                client = FeishuClient(cfg, token)
            self._clients[identity] = client
            return client

    def user_client(self) -> object:
        return self._get("user")

    def tenant_client(self) -> object:
        return self._get("tenant")

    def close(self) -> None:
        with self._lock:
            clients = tuple(self._clients.values())
            self._clients.clear()
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def invalidate(self, identity: str = "user") -> None:
        with self._lock:
            client = self._clients.pop(identity, None)
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()


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


def _commit_suffix(ctx: WebContext, paths: Sequence[Path | str], summary: str) -> str:
    """系统写回成功后自动留痕（消息带 ``wb:`` 前缀，P0'）。

    返回需要追加进响应 ``message`` 的可见说明：非 git 仓库 / 内容未变是正常态（静默，
    撤销面板会提示 not-git）；commit 失败或锁忙返回说明，但绝不阻断业务写回。
    """
    result = commit_paths(
        ctx.vault_dir,
        [Path(p) for p in paths if p],
        message=f"wb: {summary}",
        backend_kind=ctx.git_backend_kind,
        author=(
            profile_identity(ctx.active_workspace.profile)
            if ctx.active_workspace is not None and ctx.active_workspace.profile is not None
            else None
        ),
    )
    if result.status is CommitStatus.COMMITTED and ctx.active_workspace is not None:
        from summit_workbench.workflows import sync_coordinator

        sync_coordinator.push_after_commit(
            ctx.vault_dir,
            home=ctx.active_workspace.home,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )
    return _commit_note(result)


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


def _build_task_creator(ctx: WebContext, clients: _FeishuClientPool) -> TaskCreator:
    from summit_workbench.providers.feishu import (
        create_task,
    )

    def create(
        summary: str, due_date: str | None, candidate_id: str, *, operation_id: str | None = None
    ) -> str:
        return create_task(
            clients.user_client(),  # type: ignore[arg-type]
            summary,
            due_date,
            candidate_id,
            timezone=ctx.timezone,
            operation_id=operation_id,
        ).guid

    return create


def _build_meeting_creator(ctx: WebContext, clients: _FeishuClientPool) -> MeetingCreator:
    """审批「新建会议」写回器：解析主日历后创建定时日程事件，返回 event_id。

    缺省结束时间 = 开始 + 60 分钟；失败（含日历写 scope 未授权）抛错由
    apply 面板层可见化。
    """
    from datetime import datetime, timedelta

    from summit_workbench.providers.feishu import (
        create_event,
    )
    from summit_workbench.providers.feishu.calendar import primary_calendar_id

    def create(
        summary: str,
        start_at: str | None,
        end_at: str | None,
        candidate_id: str,
        *,
        operation_id: str | None = None,
    ) -> str:
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
        client = clients.user_client()
        calendar_id = primary_calendar_id(client)  # type: ignore[arg-type]
        return create_event(
            client,  # type: ignore[arg-type]
            calendar_id,
            summary,
            start_at,
            end_iso,
            timezone=ctx.timezone,
            candidate_id=candidate_id,
            operation_id=operation_id,
        )

    return create


def _ask_html(
    vault_dir: Path,
    question: str,
    history: tuple[AskTurn, ...] = (),
    project: str | None = None,
    *,
    config_file: Path | None = None,
    workspace_id: str | None = None,
) -> tuple[str, list[str]]:
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

    try:
        cfg = _load_model_config_for_context(ctx, "meeting")
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
    return {
        "ok": True,
        "message": "导入完成：" + "；".join(lines) + operation_note,
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


def _onboarding_wizard_html() -> str:
    """空安装的轻量向导；所有持久化和业务动作都经 onboarding API。"""
    return r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>开始使用 SummitWorkbench</title>
<style>
:root{font:15px -apple-system,BlinkMacSystemFont,"SF Pro Text",sans-serif;color:#1f2937;background:#f7f7f5}
main{max-width:680px;margin:7vh auto;padding:32px;background:#fff;border:1px solid #e5e7eb;border-radius:18px;box-shadow:0 12px 36px #0000000d}
h1{margin:0 0 8px;font-size:28px}h2{font-size:20px;margin:0 0 18px}p{line-height:1.65;color:#596273}.muted{font-size:13px;color:#778091}
.progress{color:#687386;font-size:13px;margin-bottom:22px}.choices{display:grid;gap:12px;margin-top:24px}
button{border:0;border-radius:10px;padding:12px 16px;font-size:15px;cursor:pointer;background:#2563eb;color:white}
button.secondary{background:#eef2ff;color:#1e40af}button.text{background:transparent;color:#4b5563;padding:8px}
label{display:block;font-weight:600;margin:14px 0 6px}input,select{box-sizing:border-box;width:100%;padding:11px;border:1px solid #d1d5db;border-radius:9px;font:inherit}
.row{display:flex;gap:10px;justify-content:space-between;margin-top:26px}.row>div{display:flex;gap:10px}.notice{background:#f3f6fb;padding:12px 14px;border-radius:10px;margin:16px 0}.error{color:#b42318;background:#fff1f0;padding:12px;border-radius:10px;margin-top:14px}
ul{line-height:1.9;padding-left:22px}.success{color:#166534;background:#f0fdf4;padding:14px;border-radius:10px}
</style></head><body><main id="wizard"><div class="progress" id="progress"></div><section id="content"></section><div id="error"></div></main>
<script>
(() => {
  const state={flow:null,step:0,work_root:'',vault_dir:'',display_name:'',device_name:'',git_mode:'skipped',remote_url:'',expected_workspace_id:'',git_username:'',pat:'',automation_role:'primary',stage_id:null};
  const steps=['location','git','model','feishu','role','check'];
  const content=document.getElementById('content'), progress=document.getElementById('progress'), error=document.getElementById('error');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(path,options={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.message||d.detail?.message||'操作未完成');return d}
  function draft(){return {flow:state.flow,step:steps[state.step],work_root:state.work_root||null,vault_dir:state.vault_dir||null,display_name:state.display_name||null,device_name:state.device_name||null,git_mode:state.git_mode,remote_url:state.remote_url||null,expected_workspace_id:state.expected_workspace_id||null,git_username:state.git_username||null,automation_role:state.automation_role,provider_status:'skipped'}}
  async function save(){await api('/api/onboarding/draft',{method:'PUT',body:JSON.stringify(draft())})}
  function setError(e){error.innerHTML='<div class="error">'+esc(e.message||e)+'</div>'}
  function field(id,label,value,type='text',placeholder=''){return '<label for="'+id+'">'+label+'</label><input id="'+id+'" type="'+type+'" value="'+esc(value)+'" placeholder="'+esc(placeholder)+'">'}
  function render(){
    error.innerHTML=''; progress.textContent=state.flow?'第 '+(state.step+1)+' / '+steps.length+' 步':'开始设置';
    if(!state.flow){content.innerHTML='<h1>开始使用 SummitWorkbench</h1><p>用几分钟选好工作区。向导会记住非秘密进度，关闭后可以继续。</p><div class="choices"><button data-flow="create-new">新建我的工作台</button><button class="secondary" data-flow="connect-existing">连接已有工作台</button><button class="secondary" data-flow="upgrade-existing">升级这台 Mac 上的旧工作台</button></div>';return}
    const title={location:'选择工作区位置',git:'同步方式',model:'模型（可跳过）',feishu:'飞书（可跳过）',role:'设备角色',check:'最终检查'}[steps[state.step]];
    let html='<h2>'+title+'</h2>';
    if(steps[state.step]==='location'){
      const create=state.flow==='create-new';html+='<p>'+(create?'选择一个新的 Work 根目录，系统会在其中创建工作区。':'填写现有工作区的 vault 目录。')+'</p>';
      html+=field(create?'work_root':'vault_dir',create?'Work 根目录':'vault 目录',create?state.work_root:state.vault_dir,'text',create?'/Users/你/Work':'/Users/你/Work/_vault');
      html+=field('display_name','显示名称',state.display_name,'text','我的工作台');
    } else if(steps[state.step]==='git'){
      html+='<p>可以先只在本机使用，之后再连接私有远端。连接远端时，向导只调用后端服务，不在页面执行 Git。</p><div class="choices"><button class="secondary" data-git="local">仅本机使用</button><button class="secondary" data-git="remote">连接私有 HTTPS 远端</button><button class="secondary" data-git="skipped">稍后设置</button></div>';
      if(state.git_mode==='remote')html+=field('remote_url','HTTPS 远端地址',state.remote_url,'url','https://git.example.com/team/workspace.git')+field('git_username','远端用户名',state.git_username,'text','你的用户名')+field('expected_workspace_id','预期 workspace id（连接已有远端时填写）',state.expected_workspace_id,'text','从原设备的工作区信息复制')+field('pat','GitHub PAT（仅本次 clone 与保存到本机 Keychain，不落盘）',state.pat,'password','ghp_…');
    } else if(steps[state.step]==='model'){
      html+='<p>模型配置可稍后在设置中心完成。跳过不会影响本地捕捉和知识库使用。</p><div class="notice">当前选择：稍后设置。此步骤不收集或保存任何密钥。</div>';
    } else if(steps[state.step]==='feishu'){
      html+='<p>飞书登录可稍后完成。跳过后仍可使用本地工作台与捕捉。</p><div class="notice">当前选择：稍后登录。授权会在你明确开始时进行。</div>';
    } else if(steps[state.step]==='role'){
      html+='<p>新建工作台默认由本机负责自动化；连接已有工作台默认是辅助设备。</p><label for="automation_role">设备角色</label><select id="automation_role"><option value="primary"'+(state.automation_role==='primary'?' selected':'')+'>主设备</option><option value="secondary"'+(state.automation_role==='secondary'?' selected':'')+'>辅助设备</option></select><div class="notice">更换已有工作区的主设备需要在后续同步设置中明确接管并确认影响。</div>';
    } else {html+='<p>请确认后完成设置。最终结果以服务端返回的 workspace/device 信息为准。</p><ul><li>流程：'+esc(state.flow)+'</li><li>位置：'+esc(state.work_root||state.vault_dir)+'</li><li>同步：'+esc(state.git_mode)+'</li><li>设备角色：'+esc(state.automation_role)+'</li></ul>'}
    html+='<div class="row"><button class="text" data-back="1">返回</button><div><button data-next="1">'+(steps[state.step]==='check'?'完成设置':'继续')+'</button></div></div>';content.innerHTML=html;
  }
  function read(){for(const id of ['work_root','vault_dir','display_name','remote_url','git_username','expected_workspace_id','pat']){const el=document.getElementById(id);if(el)state[id]=el.value.trim()}const role=document.getElementById('automation_role');if(role)state.automation_role=role.value}
  async function next(){read();const current=steps[state.step];if(current==='location'){const path=state.flow==='create-new'?state.work_root:state.vault_dir;await api('/api/onboarding/preflight',{method:'POST',body:JSON.stringify({flow:state.flow==='connect-existing'?'connect-remote':state.flow,path})})}if(current==='git'&&state.git_mode==='remote'&&!state.remote_url)throw new Error('请填写 HTTPS 远端地址');if(current==='check')return complete();state.step++;await save();render()}
  async function complete(){await save();let d;if(state.flow==='create-new')d=await api('/api/onboarding/create',{method:'POST',body:JSON.stringify({work_root:state.work_root,display_name:state.display_name||null,device_name:state.device_name||null,device_role:state.automation_role==='primary'?'automation-primary':'secondary'})});else if(state.flow==='upgrade-existing')d=await api('/api/onboarding/upgrade',{method:'POST',body:JSON.stringify({vault_dir:state.vault_dir,display_name:state.display_name||null,device_name:state.device_name||null,device_role:state.automation_role==='primary'?'automation-primary':'secondary'})});else if(state.git_mode==='remote'){const staged=await api('/api/onboarding/remote/stage',{method:'POST',body:JSON.stringify({remote_url:state.remote_url,target_vault:state.vault_dir,expected_workspace_id:state.expected_workspace_id||null,git_username:state.git_username,pat:state.pat||null})});d=await api('/api/onboarding/remote/confirm',{method:'POST',body:JSON.stringify({stage_id:staged.stage_id,display_name:state.display_name||null,device_name:state.device_name||null,pat:state.pat||null})})}else d=await api('/api/onboarding/connect',{method:'POST',body:JSON.stringify({vault_dir:state.vault_dir,display_name:state.display_name||null,device_name:state.device_name||null,device_role:'secondary'})});await api('/api/onboarding/draft',{method:'DELETE'});content.innerHTML='<h2>设置完成</h2><div class="success">工作区已准备好。workspace id：'+esc(d.workspace_id)+'<br>本机 device id：'+esc(d.device_id)+'<br><br>请重新打开 SummitWorkbench 进入工作台。</div>';progress.textContent='完成';}
  document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.flow){state.flow=b.dataset.flow;state.step=0;state.automation_role=state.flow==='connect-existing'?'secondary':'primary';await save();render()}else if(b.dataset.git){state.git_mode=b.dataset.git;render()}else if(b.dataset.back){if(state.step===0){state.flow=null;render()}else{state.step--;await save();render()}}else if(b.dataset.next){await next()}}catch(err){setError(err)}});
  (async()=>{try{const d=(await api('/api/onboarding/draft')).draft;if(d){Object.assign(state,d);state.flow=d.flow;state.step=Math.max(0,steps.indexOf(d.step));render()}else render()}catch(e){setError(e)}})();
})();
</script></body></html>"""


def _create_restricted_app(
    active_workspace: ActiveWorkspaceContext,
    *,
    static_dir: Path | None = None,
    bind_host: str = "127.0.0.1",
    port: int = 8787,
    session_token: str | None = None,
    workspace_id: str | None = None,
    device_id: str | None = None,
    server_instance: str | None = None,
) -> FastAPI:
    """Create the empty-install control plane without constructing a vault context."""
    panel_mode = mode_from_environment(os.environ.get("WB_PANEL_MODE"))
    validate_bind_host(bind_host, panel_mode)
    normalized_bind_host = bind_host.strip().strip("[]").lower()
    external_bind = normalized_bind_host not in {"127.0.0.1", "::1"}
    host_allowlist = allowed_hosts(bind_host, port, include_test_alias=panel_mode != "production")
    server_instance = server_instance or new_server_instance()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    app = FastAPI(title="SummitWorkbench onboarding", lifespan=None)
    app.state.active_workspace_context = active_workspace
    remote_stages: dict[str, object] = {}

    @app.exception_handler(RequestValidationError)
    async def _restricted_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"loc": list(error.get("loc", ())), "msg": str(error.get("msg", "输入无效"))}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="validation_error",
                message="请求参数不符合接口约束",
                operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                details=details,
            ),
        )

    @app.middleware("http")
    async def _restricted_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from uuid import uuid4

        operation_id = str(uuid4())
        host = request.headers.get("host", "").lower()
        dynamic_loopback_host = (
            port == 0
            and (host.startswith("127.0.0.1:") or host.startswith("localhost:"))
            and host.rsplit(":", 1)[-1].isdigit()
        )
        if host not in host_allowlist and not dynamic_loopback_host:
            return JSONResponse(
                status_code=403,
                content=error_payload(
                    code="host_not_allowed",
                    message="请求 Host 不属于当前本地服务",
                    operation_id=operation_id,
                ),
            )
        session_required = panel_mode == "production" or external_bind or session_token is not None
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        supplied_token = request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER)
        if request.method in {"POST", "PATCH", "DELETE"} or (
            request.url.path.startswith("/api/")
            and session_required
            and request.url.path != "/api/session/bootstrap"
        ):
            origin = request.headers.get("origin")
            origin_hosts = {host} if dynamic_loopback_host else host_allowlist
            if origin is not None and not origin_matches(origin, request.url.scheme, origin_hosts):
                return JSONResponse(
                    status_code=403,
                    content=error_payload(
                        code="origin_not_allowed",
                        message="请求来源不是当前服务同源地址",
                        operation_id=operation_id,
                    ),
                )
            if session_required and not session_token_matches(supplied_token, expected_token):
                return JSONResponse(
                    status_code=401,
                    content=error_payload(
                        code="authentication_required",
                        message="写请求需要本地会话令牌",
                        operation_id=operation_id,
                    ),
                )
        response = await call_next(request)
        response.headers["X-WB-Operation-ID"] = operation_id
        return response

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def restricted_home() -> HTMLResponse:
        from summit_workbench.webapp.onboarding_view import render_onboarding_wizard

        return HTMLResponse(render_onboarding_wizard())

    @app.get("/api/version")
    def restricted_version(request: Request) -> JSONResponse:
        try:
            info = WebBuildInfo.from_static_dir(static_dir or _STATIC_DIR)
        except BuildInfoError as exc:
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="invalid_build_manifest",
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        return JSONResponse(
            info.version_payload(
                server_instance=server_instance,
                started_at=started_at,
                mode=panel_mode,
                workspace_id=workspace_id,
                device_id=device_id,
                port=getattr(app.state, "bound_port", None),
            )
        )

    @app.get("/api/session/bootstrap", include_in_schema=False)
    def restricted_session_bootstrap(request: Request, token: str) -> Response:
        if panel_mode == "production" or not session_token_matches(
            token, session_token or os.environ.get("WB_SESSION_TOKEN")
        ):
            return JSONResponse(
                status_code=401,
                content=error_payload(
                    code="authentication_required",
                    message="一次性会话令牌无效",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, path="/"
        )
        return response

    from summit_workbench.config.profiles import resolve_workspace
    from summit_workbench.domain.onboarding import OnboardingFlow
    from summit_workbench.workflows import onboarding as onboarding_service

    def _rejected(request: Request, exc: onboarding_service.OnboardingError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="onboarding_rejected",
                message=str(exc),
                operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                details={"reasons": exc.reasons},
            ),
        )

    @app.get("/api/onboarding/status", response_model=None)
    def restricted_onboarding_status() -> dict[str, object]:
        resolution = resolve_workspace(allow_env_fallback=False)
        return {
            "ok": True,
            "state": resolution.state.value,
            "workspace_id": resolution.profile.workspace_id if resolution.profile else None,
            "reason": resolution.reason,
        }

    @app.get("/api/onboarding/draft", response_model=None)
    def restricted_draft() -> dict[str, object]:
        from summit_workbench.repositories.onboarding_draft import load_onboarding_draft

        draft = load_onboarding_draft(home=active_workspace.home)
        return {"ok": True, "draft": draft.model_dump(mode="json") if draft else None}

    @app.put("/api/onboarding/draft", response_model=None)
    def restricted_save_draft(
        request: Request, payload: Annotated[OnboardingDraftPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.repositories.onboarding_draft import (
            OnboardingDraft,
            save_onboarding_draft,
        )

        try:
            draft = OnboardingDraft.model_validate(payload.model_dump())
            path = save_onboarding_draft(draft, home=active_workspace.home)
        except (OSError, ValueError):
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="onboarding_draft_failed",
                    message="向导进度暂时无法保存",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        return {"ok": True, "step": draft.step, "path": str(path)}

    @app.delete("/api/onboarding/draft", response_model=None)
    def restricted_clear_draft() -> dict[str, object]:
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True}

    @app.post("/api/onboarding/remote/stage", response_model=None)
    def restricted_remote_stage(
        request: Request, payload: Annotated[OnboardingRemoteStagePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from uuid import uuid4

        from summit_workbench.workflows.remote_onboarding import (
            RemoteCloneError,
            stage_remote_clone,
        )

        credential_resolver = None
        if payload.pat:
            from pydantic import SecretStr

            from summit_workbench.config.git_credentials import GitCredentials

            pat = SecretStr(payload.pat)

            def resolve(_ws: str, host: str, _username: str) -> GitCredentials:
                return GitCredentials(_ws, host, payload.git_username, pat)

            credential_resolver = resolve

        try:
            staged = stage_remote_clone(
                payload.remote_url,
                Path(payload.target_vault).expanduser(),
                workspace_id=payload.expected_workspace_id,
                username=payload.git_username,
                home=active_workspace.home,
                credential_resolver=credential_resolver,
            )
        except RemoteCloneError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code,
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                    details={"reasons": exc.reasons},
                ),
            )
        stage_id = str(uuid4())
        remote_stages[stage_id] = staged
        return {
            "ok": True,
            "stage_id": stage_id,
            "workspace_id": staged.workspace_id,
            "remote_url": staged.remote_url,
            "compatibility": staged.compatibility.value,
        }

    @app.post("/api/onboarding/remote/confirm", response_model=None)
    def restricted_remote_confirm(
        request: Request, payload: Annotated[OnboardingRemoteConfirmPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.remote_onboarding import (
            RemoteCloneError,
            confirm_remote_clone,
        )

        staged = remote_stages.get(payload.stage_id)
        if staged is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="staging_missing",
                    message="连接准备已失效，请重新开始",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        try:
            result = confirm_remote_clone(
                staged,  # type: ignore[arg-type]
                home=active_workspace.home,
                display_name=payload.display_name,
                device_name=payload.device_name,
                user_email=payload.user_email,
            )
            if payload.pat:
                from urllib.parse import urlsplit

                from pydantic import SecretStr

                from summit_workbench.config.git_credentials import store_git_credentials
                from summit_workbench.workflows.remote_onboarding import RemoteCloneStage

                staged_info = cast(RemoteCloneStage, staged)
                host = urlsplit(staged_info.remote_url).hostname or ""
                store_git_credentials(
                    staged_info.workspace_id, host, staged_info.username, SecretStr(payload.pat)
                )
        except RemoteCloneError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code,
                    message=str(exc),
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        remote_stages.pop(payload.stage_id, None)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/remote/cancel", response_model=None)
    def restricted_remote_cancel(
        request: Request, payload: Annotated[OnboardingRemoteConfirmPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.remote_onboarding import cancel_remote_clone

        staged = remote_stages.pop(payload.stage_id, None)
        if staged is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="staging_missing",
                    message="连接准备已失效",
                    operation_id=request.headers.get("x-wb-operation-id", "unknown"),
                ),
            )
        cancel_remote_clone(staged)  # type: ignore[arg-type]
        return {"ok": True}

    @app.post("/api/onboarding/preflight", response_model=None)
    def restricted_preflight(
        request: Request, payload: Annotated[OnboardingPreflightPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            report = onboarding_service.preflight(
                OnboardingFlow(payload.flow),
                Path(payload.path).expanduser(),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        return {"ok": True, "report": report.model_dump(mode="json")}

    @app.post("/api/onboarding/create", response_model=None)
    def restricted_create(
        request: Request, payload: Annotated[OnboardingCreatePayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.create_workspace(
                Path(payload.work_root).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                templates_dir=onboarding_service.default_vault_templates_dir(),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/upgrade", response_model=None)
    def restricted_upgrade(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.upgrade_workspace(
                Path(payload.vault_dir).expanduser(),
                device_name=payload.device_name,
                device_role=DeviceRole(payload.device_role),
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    @app.post("/api/onboarding/connect", response_model=None)
    def restricted_connect(
        request: Request, payload: Annotated[OnboardingVaultPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = onboarding_service.connect_workspace(
                Path(payload.vault_dir).expanduser(),
                display_name=payload.display_name,
                device_name=payload.device_name,
                home=active_workspace.home,
            )
        except onboarding_service.OnboardingError as exc:
            return _rejected(request, exc)
        from summit_workbench.repositories.onboarding_draft import clear_onboarding_draft

        clear_onboarding_draft(home=active_workspace.home)
        return {"ok": True, **result.model_dump(mode="json")}

    from summit_workbench.webapp.routers.settings import register_restricted_connection_routes

    register_restricted_connection_routes(
        app,
        active_workspace=active_workspace,
        operation_id=lambda request: request.headers.get("x-wb-operation-id", "unknown"),
    )

    return app


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
        return _create_restricted_app(
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
    switch_plans: dict[str, object] = {}
    remote_normalization_plans: dict[str, RemoteNormalizationPlan] = {}
    profile_switch_in_progress = False

    def _operation_id(request: Request) -> str:
        operation_id = getattr(request.state, "operation_id", None)
        return str(operation_id or "unknown")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(error.get("loc", ())), "msg": str(error.get("msg", "输入无效"))}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="validation_error",
                message="请求参数不符合接口约束",
                operation_id=_operation_id(request),
                details=details,
            ),
        )

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        code = "http_error"
        message = str(detail)
        details: object | None = None
        if isinstance(detail, dict):
            code = str(detail.get("code", code))
            message = str(detail.get("message", message))
            details = detail.get("details")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=message,
                operation_id=_operation_id(request),
                details=details,
            ),
        )

    @app.exception_handler(MutationBlocked)
    async def _mutation_blocked_error(request: Request, exc: MutationBlocked) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="sync_diverged",
                message=str(exc),
                operation_id=_operation_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="internal_error",
                message="服务内部错误，请稍后重试",
                operation_id=_operation_id(request),
            ),
        )

    @app.middleware("http")
    async def _security_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from uuid import uuid4

        operation_id = str(uuid4())
        request.state.operation_id = operation_id
        host = request.headers.get("host", "").lower()
        dynamic_loopback_host = (
            port == 0
            and (host.startswith("127.0.0.1:") or host.startswith("localhost:"))
            and host.rsplit(":", 1)[-1].isdigit()
        )
        if host not in host_allowlist and not dynamic_loopback_host:
            return JSONResponse(
                status_code=403,
                content=error_payload(
                    code="host_not_allowed",
                    message="请求 Host 不属于当前本地服务",
                    operation_id=operation_id,
                ),
            )
        session_required = panel_mode == "production" or external_bind or session_token is not None
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        supplied_token = request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER)
        if request.method in {"POST", "PATCH", "DELETE"} or (
            request.url.path.startswith("/api/")
            and session_required
            and request.url.path != "/api/session/bootstrap"
        ):
            if (
                request.method in {"POST", "PATCH", "DELETE"}
                and ctx.compatibility is Compatibility.CANNOT_OPEN
                and not request.url.path.startswith("/api/onboarding")
                and request.url.path != "/api/workspace/migration"
            ):
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        code="workspace_not_found",
                        message="当前工作区无法打开，请升级或重新连接工作区",
                        operation_id=operation_id,
                    ),
                )
            if (
                request.method in {"POST", "PATCH", "DELETE"}
                and ctx.compatibility is Compatibility.READ_ONLY_UPGRADE_REQUIRED
                and not request.url.path.startswith("/api/onboarding")
                and request.url.path != "/api/workspace/migration"
                and request.url.path not in _SCHEMA_UPGRADE_WRITE_EXEMPTIONS
            ):
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        code="workspace_read_only_upgrade_required",
                        message="当前工作区需要升级后才能写入",
                        operation_id=operation_id,
                    ),
                )
            origin = request.headers.get("origin")
            origin_hosts = {host} if dynamic_loopback_host else host_allowlist
            if origin is not None and not origin_matches(origin, request.url.scheme, origin_hosts):
                return JSONResponse(
                    status_code=403,
                    content=error_payload(
                        code="origin_not_allowed",
                        message="请求来源不是当前服务同源地址",
                        operation_id=operation_id,
                    ),
                )
            if session_required:
                if not session_token_matches(supplied_token, expected_token):
                    return JSONResponse(
                        status_code=401,
                        content=error_payload(
                            code="authentication_required",
                            message="写请求需要本地会话令牌",
                            operation_id=operation_id,
                        ),
                    )
        response = await call_next(request)
        response.headers["X-WB-Operation-ID"] = operation_id
        return response

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

    def _settings_home() -> Path:
        return ctx.active_workspace.home if ctx.active_workspace else Path.home()

    @app.get("/api/settings/profiles", response_model=None)
    def settings_profiles() -> dict[str, object]:
        from summit_workbench.repositories.profile_registry import active_profile_id

        summaries = list_profile_summaries(home=_settings_home())
        return {
            "ok": True,
            "active_workspace_id": active_profile_id(home=_settings_home()),
            "current_device_id": (
                ctx.active_workspace.device_id if ctx.active_workspace is not None else None
            ),
            "profiles": [item.as_dict() for item in summaries],
        }

    @app.post("/api/settings/acceptance-preflight", response_model=None)
    def settings_acceptance_preflight(
        request: Request, _payload: AcceptancePreflightPayload
    ) -> dict[str, object] | JSONResponse:
        """Run the read-only P1-07D gate and return a copyable redacted report."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以运行验收预检",
                    operation_id=_operation_id(request),
                ),
            )
        try:
            try:
                web_info = _build_info()
                frontend_build = web_info.frontend_build
                git_revision = web_info.git_revision
            except BuildInfoError:
                frontend_build = None
                git_revision = None
            report = acceptance_preflight(
                ctx.vault_dir,
                home=ctx.active_workspace.home,
                workspace_id=ctx.workspace_id,
                app_version=__version__,
                backend_kind=ctx.git_backend_kind or "dulwich",
                build_number=discover_build_number(),
                frontend_build=frontend_build,
                git_revision=git_revision,
            )
        except Exception:  # noqa: BLE001 - report boundary must stay redacted
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="acceptance_preflight_failed",
                    message="验收预检无法完成；请查看本机诊断，不会显示凭据或远端密钥",
                    operation_id=_operation_id(request),
                ),
            )
        return {
            "ok": report.ok,
            "workspace_id": report.workspace_id,
            "app_version": report.app_version,
            "checks": [item.__dict__ for item in report.checks],
            "report": report.text,
        }

    @app.post("/api/settings/git/remote/preview", response_model=None)
    def settings_git_remote_preview(
        request: Request, payload: GitRemoteNormalizationPayload
    ) -> dict[str, object] | JSONResponse:
        """Validate a candidate HTTPS origin in a temporary clone; no local mutation."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以规范化 Git remote",
                    operation_id=_operation_id(request),
                ),
            )
        try:
            from pydantic import SecretStr

            plan = preview_remote_normalization(
                ctx.vault_dir,
                workspace_id=ctx.workspace_id,
                username=payload.git_username,
                pat=SecretStr(payload.pat),
                candidate_url=payload.candidate_url,
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=_operation_id(request)
                ),
            )
        remote_normalization_plans[plan.plan_id] = plan
        return {
            "ok": True,
            "plan_id": plan.plan_id,
            "workspace_id": plan.workspace_id,
            "old_url": plan.old_url,
            "candidate_url": plan.candidate_url,
            "branch": plan.branch,
            "candidate_fetched": plan.candidate.fetched,
            "candidate_ahead": plan.candidate.ahead,
            "candidate_behind": plan.candidate.behind,
            "note": "预览未修改 origin、profile、vault、提交、推送或 Keychain",
        }

    @app.post("/api/settings/git/remote/apply", response_model=None)
    def settings_git_remote_apply(
        request: Request, payload: GitRemoteNormalizationPlanPayload
    ) -> dict[str, object] | JSONResponse:
        """Revalidate a preview then atomically apply origin/profile/keychain."""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active workspace 可以规范化 Git remote",
                    operation_id=_operation_id(request),
                ),
            )
        plan = remote_normalization_plans.get(payload.plan_id)
        if plan is None or plan.workspace_id != ctx.workspace_id:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="normalization_plan_missing",
                    message="转换预览已失效，请重新预览",
                    operation_id=_operation_id(request),
                ),
            )
        try:
            from pydantic import SecretStr

            transaction = apply_remote_normalization(
                ctx.vault_dir,
                plan,
                username=payload.git_username,
                pat=SecretStr(payload.pat),
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=_operation_id(request)
                ),
            )
        remote_normalization_plans.pop(payload.plan_id, None)
        return {
            "ok": True,
            "transaction_id": transaction.transaction_id,
            "old_url": transaction.old_url,
            "new_url": transaction.new_url,
            "note": "origin/profile/Keychain 已更新；未提交、未推送、未修改 vault 内容",
        }

    @app.post("/api/settings/git/remote/rollback", response_model=None)
    def settings_git_remote_rollback(
        request: Request, payload: GitRemoteRollbackPayload
    ) -> dict[str, object] | JSONResponse:
        """Rollback the last applied remote normalization transaction."""
        if not payload.confirmed or ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="confirmation_required",
                    message="请明确确认回滚当前 remote 转换",
                    operation_id=_operation_id(request),
                ),
            )
        try:
            transaction = rollback_remote_normalization(
                ctx.vault_dir,
                workspace_id=ctx.workspace_id,
                home=ctx.active_workspace.home,
                backend_kind=ctx.git_backend_kind or "dulwich",
            )
        except RemoteNormalizationError as exc:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=exc.code, message=str(exc), operation_id=_operation_id(request)
                ),
            )
        return {
            "ok": True,
            "transaction_id": transaction.transaction_id,
            "restored_url": transaction.old_url,
            "note": "origin/profile 已恢复；未提交、未推送、未修改 vault 内容",
        }

    @app.post("/api/settings/profile/prepare", response_model=None)
    def settings_profile_prepare(payload: ProfileSwitchPayload) -> dict[str, object]:
        nonlocal profile_switch_in_progress
        try:
            plan = prepare_profile_switch(
                home=_settings_home(), target_workspace_id=payload.workspace_id
            )
        except ProfileSettingsError as exc:
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        switch_plans[plan.plan_id] = plan
        profile_switch_in_progress = True
        return {"ok": True, "plan_id": plan.plan_id, "workspace_id": plan.target_workspace_id}

    @app.post("/api/settings/profile/commit", response_model=None)
    def settings_profile_commit(payload: ProfileSwitchCommitPayload) -> dict[str, object]:
        nonlocal profile_switch_in_progress
        plan = switch_plans.pop(payload.plan_id, None)
        if plan is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "switch_plan_missing", "message": "切换计划已失效，请重新准备"},
            )
        assert isinstance(plan, ProfileSwitchPlan)
        try:
            return commit_profile_switch(home=_settings_home(), plan=plan)
        except ProfileSettingsError as exc:
            profile_switch_in_progress = False
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @app.post("/api/settings/profile/remove", response_model=None)
    def settings_profile_remove(payload: ProfileRemovePayload) -> dict[str, object]:
        try:
            return remove_local_profile(
                home=_settings_home(),
                workspace_id=payload.workspace_id,
                confirmed=payload.confirmed,
            )
        except ProfileSettingsError as exc:
            if exc.code == "confirmation_required":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": exc.code,
                        "message": str(exc),
                        "details": {
                            "workspace_id": payload.workspace_id,
                            "deletes": ["local_profile", "runtime", "onboarding_draft"],
                            "preserves": ["vault", "remote", "keychain"],
                        },
                    },
                ) from exc
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @app.post("/api/settings/provider", response_model=None)
    def settings_provider(payload: ProviderSettingsPayload) -> dict[str, object]:
        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        try:
            return update_provider_settings(
                home=_settings_home(),
                workspace_id=ctx.workspace_id,
                provider=payload.provider,
                settings=payload.settings,
                secret=payload.secret,
            )
        except ProfileSettingsError as exc:
            raise HTTPException(
                status_code=409, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    def _automation_settings_payload() -> dict[str, object]:
        from summit_workbench.repositories.automation_settings import load_automation_settings

        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        try:
            settings = load_automation_settings(ctx.workspace_id, home=_settings_home())
        except ValueError as exc:
            raise HTTPException(
                status_code=409, detail={"code": "automation_settings_invalid", "message": str(exc)}
            ) from exc
        return {
            "ok": True,
            "workspace_id": settings.workspace_id,
            "jobs": {
                job.value: schedule.model_dump(mode="json")
                for job, schedule in ((job, settings.for_job(job)) for job in AutomationJob)
            },
        }

    @app.get("/api/settings/automation", response_model=None)
    def settings_automation() -> dict[str, object]:
        return _automation_settings_payload()

    @app.put("/api/settings/automation", response_model=None)
    def update_settings_automation(payload: AutomationSettingsPayload) -> dict[str, object]:
        from summit_workbench.repositories.automation_settings import (
            load_automation_settings,
            save_automation_settings,
        )

        if ctx.workspace_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        job = AutomationJob(payload.job)
        try:
            settings = load_automation_settings(ctx.workspace_id, home=_settings_home())
            current = settings.for_job(job)
            settings.jobs[job] = current.model_copy(
                update={
                    "enabled": payload.enabled,
                    "hour": payload.hour,
                    "minute": payload.minute,
                    "weekdays": sorted(set(payload.weekdays)),
                    "next_run_at": None,
                }
            )
            save_automation_settings(settings, home=_settings_home())
        except ValueError as exc:
            raise HTTPException(
                status_code=409, detail={"code": "automation_settings_invalid", "message": str(exc)}
            ) from exc
        return {"ok": True, "job": settings.jobs[job].model_dump(mode="json")}

    @app.post("/api/settings/automation/run", response_model=None)
    def run_settings_automation(
        request: Request, payload: AutomationRunPayload
    ) -> dict[str, object] | JSONResponse:
        from summit_workbench.workflows.automation_worker import run_automation_job

        if ctx.active_workspace is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_not_found", "message": "当前没有 active workspace"},
            )
        # 「立即运行」是人工触发，不应被当天已执行过的调度记录拦截；
        # 定时 worker 仍使用默认的 schedule due 门控。
        result = run_automation_job(ctx.active_workspace, AutomationJob(payload.job), force=True)
        # secondary/未启用的「跳过」是预期结果，不是错误：返回 ok=true 让前端以提示而非
        # 报错呈现（P1-07D 要求 Air 自动化安全跳过，绝不运行定时 writer）。
        return {
            "ok": result.status.value in {"success", "degraded", "skipped", "not-primary"},
            **result.as_dict(),
        }

    @app.post("/api/settings/doctor", response_model=None)
    def settings_doctor(payload: DoctorPayload) -> dict[str, object]:
        from summit_workbench.cli.doctor import CheckStatus, run_checks
        from summit_workbench.config.settings import load_settings

        active = ctx.active_workspace
        settings = load_settings(
            work_root=ctx.work_root, vault_dir=ctx.vault_dir, timezone=ctx.timezone
        )
        checks = run_checks(
            settings,
            config_file=ctx.provider_config_file(),
            online=payload.online,
            context=active,
        )
        return {
            "ok": not any(item.status is CheckStatus.FAIL for item in checks),
            "online": payload.online,
            "checks": [item.as_dict() for item in checks],
        }

    @app.get("/api/state")
    def api_state() -> dict[str, object]:
        """看板数据：日期、状态速览、今日简报、inbox 积压。"""
        day = ctx.today()
        status = build_status(ctx.vault_dir, config_file=ctx.provider_config_file())
        sync_state = _current_sync_snapshot().state.value
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

    from summit_workbench.webapp.routers.projects import register_project_write_routes

    register_project_write_routes(
        RouteDependencies(app=app, context=ctx, operation_id=_operation_id),
        run_mutation=lambda action, mutation: _run_web_mutation(action, mutation),
    )

    @app.get("/api/review")
    def api_review() -> dict[str, object]:
        entries, errors = _load(ctx.vault_dir)
        return review_payload(entries, errors)

    @app.get("/api/review/source", response_class=PlainTextResponse)
    def api_review_source(path: str = "") -> PlainTextResponse:
        """在回环服务内只读展示审批候选引用的 Markdown/文本来源。"""
        relative = Path(path.strip())
        if not path.strip() or relative.is_absolute() or ".." in relative.parts:
            return PlainTextResponse("来源路径无效", status_code=400)
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
        return PlainTextResponse(source.read_text(encoding="utf-8"))

    @app.post("/api/review/decide", response_model=None)
    def api_decide(payload: DecidePayload) -> dict[str, object]:
        try:

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                set_decision(
                    ctx.vault_dir, payload.candidate_id, CandidateDecision(payload.decision)
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = _run_web_mutation(
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
            result = _run_web_mutation(
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
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = _run_web_mutation(
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
                result = _run_web_mutation(
                    "external-actions/reconcile",
                    lambda _operation_id: LocalMutationOutcome(
                        reconcile_succeeded(ctx.vault_dir, current_action, payload.remote_id or ""),
                        (ctx.vault_dir / "_signals" / "external-actions" / "log.jsonl",),
                    ),
                )
                action = result.business_return
            elif payload.decision == "not-found":
                result = _run_web_mutation(
                    "external-actions/reconcile",
                    lambda _operation_id: LocalMutationOutcome(
                        reconcile_not_found(ctx.vault_dir, current_action),
                        (ctx.vault_dir / "_signals" / "external-actions" / "log.jsonl",),
                    ),
                )
                action = result.business_return
            elif payload.decision == "retry":
                result = _run_web_mutation(
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
        blocked = _mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            report = apply_meeting_review(
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx, feishu_clients),
                meeting_creator=_build_meeting_creator(ctx, feishu_clients),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            return {"ok": False, "message": f"应用失败：{type(exc).__name__}: {exc}"}
        # 自动留痕：写回目标文件 + 审批页 + 审计归档（P0' 埋点；库外文件自动跳过）
        touched: list[Path | str] = [review_path(ctx.vault_dir)]
        if report.archive_path is not None:
            touched.append(report.archive_path)
        touched.extend(
            a.destination for a in report.actions if not a.destination.startswith("feishu-")
        )
        git_note = _commit_suffix(ctx, touched, "审批应用写回")
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
            result = _run_web_mutation("threads/state", mutate)
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
            result = _run_web_mutation("threads/logs", mutate)
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
            result = _run_web_mutation("threads/artifacts", mutate)
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

        def mutate(_operation_id: str) -> LocalMutationOutcome[tuple[Path, bool]]:
            path, written = append_global_inbox(ctx.vault_dir, text, candidate_id, markers=markers)
            return LocalMutationOutcome((path, written), (path,))

        result = _run_web_mutation("capture", mutate)
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
        result = _run_web_mutation(
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
        result = _run_web_mutation(
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
        result = _run_web_mutation(
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

        blocked = _sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = _mutation_blocked(request)
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
            commit_note = _commit_suffix(
                ctx,
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

        blocked = _sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = _mutation_blocked(request)
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
        html, source_ids = _ask_html(
            ctx.vault_dir,
            question,
            history=history,
            project=project,
            config_file=ctx.config_file,
            workspace_id=ctx.workspace_id,
        )
        if html.startswith('<p class="not-actionable">问答不可用：'):
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="ask_unavailable",
                    message="问答服务暂不可用",
                    operation_id=_operation_id(request),
                ),
            )
        return {"ok": True, "answer_html": html, "source_ids": source_ids}

    @app.post("/api/meetings/import")
    def api_meetings_import(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        """拖拽上传逐字稿 → 全自动归档 + 结构化 + 生成审批候选。"""
        max_upload_bytes = 10 * 1024 * 1024
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
                return _run_web_import(ctx, target, local_mutation=_run_web_mutation)
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
        blocked = _mutation_blocked(request)
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

        blocked = _sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = _mutation_blocked(request)
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

        blocked = _sync_blocked(request)
        if blocked is not None:
            return blocked
        blocked = _mutation_blocked(request)
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
        html, _source_ids = _ask_html(
            ctx.vault_dir,
            q,
            config_file=ctx.config_file,
            workspace_id=ctx.workspace_id,
        )
        return _dashboard(ask_q=q, ask_html=html)

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

            result = _run_web_mutation(
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
    ) -> RedirectResponse:
        try:

            def mutate(_operation_id: str) -> LocalMutationOutcome[None]:
                update_fields(
                    ctx.vault_dir,
                    candidate_id,
                    description=description.strip() or None,
                    target_project=target_project.strip() or None,
                    route=RouteTarget(route) if route else None,
                    due_date=due_date.strip() or None,
                )
                return LocalMutationOutcome(None, (review_path(ctx.vault_dir),))

            result = _run_web_mutation(
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

    @app.post("/review/apply", response_class=HTMLResponse, response_model=None)
    def apply(request: Request) -> HTMLResponse | JSONResponse:
        blocked = _mutation_blocked(request)
        if blocked is not None:
            return blocked
        try:
            report = apply_meeting_review(
                ctx.vault_dir,
                ctx.work_root,
                apply=True,
                task_creator=_build_task_creator(ctx, feishu_clients),
                meeting_creator=_build_meeting_creator(ctx, feishu_clients),
            )
        except Exception as exc:  # noqa: BLE001 - 面板需把任何失败可见化
            detail = f"应用失败：{type(exc).__name__}: {exc}"
            return HTMLResponse(render_plan(detail, executed=True))
        return HTMLResponse(render_plan(_plan_text(report), executed=True))

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

    register_workspace_routes(RouteDependencies(app=app, context=ctx, operation_id=_operation_id))

    # ---- 多设备同步（P0-10）----

    from summit_workbench.domain.sync import AutomationOutcome, SyncSnapshot
    from summit_workbench.repositories.automation_primary import load_automation_primary
    from summit_workbench.workflows import sync_coordinator

    def _current_sync_snapshot() -> SyncSnapshot:
        return sync_coordinator.current_snapshot(
            ctx.vault_dir,
            home=ctx.active_workspace.home if ctx.active_workspace else None,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )

    def _run_web_mutation[T](
        action: str, mutation: Callable[[str], LocalMutationOutcome[T]]
    ) -> LocalMutationResult[T]:
        if profile_switch_in_progress:
            raise MutationBlocked("工作台正在切换，请等待本机服务重启后再修改")
        profile = ctx.active_workspace.profile if ctx.active_workspace else None
        return run_local_mutation(
            ctx.vault_dir,
            action,
            mutation,
            sync_snapshot=_current_sync_snapshot() if ctx.active_workspace else None,
            sync_snapshot_provider=_current_sync_snapshot if ctx.active_workspace else None,
            compatibility=ctx.compatibility,
            backend_kind=ctx.git_backend_kind,
            author=profile_identity(profile) if profile is not None else None,
            push_after_commit=(
                lambda: sync_coordinator.push_after_commit(
                    ctx.vault_dir,
                    home=ctx.active_workspace.home if ctx.active_workspace else None,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                    context=ctx.active_workspace,
                )
            )
            if ctx.active_workspace
            else None,
        )

    def _sync_blocked(request: Request) -> JSONResponse | None:
        """automation 角色门：secondary 上定时 writer 不执行（env-compat 放行）。"""
        profile = ctx.active_workspace.profile if ctx.active_workspace else None
        if ctx.active_workspace is None:
            # 保留直接注入 WebContext 的 development/test 兼容语义：这些调用方
            # 可能在 app 创建后才准备临时 profile。production 入口始终传入冻结
            # 的 ActiveWorkspaceContext，不会走这条动态回退。
            from summit_workbench.config.profiles import resolve_active_workspace

            profile = resolve_active_workspace(allow_env_fallback=True).profile
        claim = None
        device_id = None
        if ctx.active_workspace is not None:
            claim = load_automation_primary(ctx.vault_dir)
            device_id = ctx.active_workspace.device_id
        if (
            sync_coordinator.automation_gate(
                profile,
                claim=claim,
                device_id=device_id,
                require_claim=ctx.active_workspace is not None,
            )
            is AutomationOutcome.NOT_PRIMARY
        ):
            # P1-07D：secondary 上的手动/定时写入是预期跳过，不是错误。返回 200 友好
            # 提示（前端以普通提示而非红色 ApiError 呈现），写入本身仍被门控跳过。
            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "skipped": True,
                    "code": "not_automation_primary",
                    "message": "本机不是该 workspace 的主设备，本次操作已跳过",
                },
            )
        return None

    def _mutation_blocked(request: Request) -> JSONResponse | None:
        """diverged/dirty 保护态：修改共享 vault 的写被拒（读照常）。"""
        snapshot = _current_sync_snapshot()
        ok, reason = sync_coordinator.mutation_guard(snapshot)
        if ok:
            return None
        state = snapshot.state.value if snapshot is not None else "protected"
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="sync_diverged",
                message=reason,
                operation_id=_operation_id(request),
                details={"state": state},
            ),
        )

    def _sync_payload() -> dict[str, object]:
        snapshot = _current_sync_snapshot()
        claim = load_automation_primary(ctx.vault_dir)
        return {
            "ok": True,
            "workspace_id": snapshot.workspace_id,
            "state": snapshot.state.value,
            "pending_commits": snapshot.pending_commits,
            "last_sync_at": snapshot.last_sync_at,
            "next_step": snapshot.next_step,
            "detail": snapshot.detail,
            "ahead": snapshot.ahead,
            "behind": snapshot.behind,
            "branch": snapshot.branch,
            "remote_host": snapshot.remote_host,
            "repo_states": snapshot.repo_states,
            "automation_primary_device_id": claim.device_id if claim is not None else None,
            "automation_primary_generation": claim.generation if claim is not None else None,
        }

    @app.get("/api/sync/status", response_model=None)
    def api_sync_status() -> dict[str, object]:
        """当前 workspace 同步状态（供 UI banner；不执行任何 git 写）。"""
        return _sync_payload()

    @app.get("/api/sync/conflict/explain", response_model=None)
    def api_sync_conflict_explain(paths: str | None = None) -> dict[str, object]:
        """Explain conflict handling without fetching, merging, or writing anything."""
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        explanation = explain_conflict(_current_sync_snapshot().state, raw_paths)
        return {"ok": True, "conflict": explanation.as_dict()}

    @app.get("/api/sync/conflict/plan", response_model=None)
    def api_sync_conflict_plan(paths: str | None = None) -> dict[str, object]:
        """Return a safe recovery plan; preparation/apply are separate later steps."""
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        plan = plan_conflict_recovery(_current_sync_snapshot().state, raw_paths)
        return {"ok": True, "recovery_plan": plan.as_dict()}

    @app.get("/api/sync/conflict/details", response_model=None)
    def api_sync_conflict_details(paths: str | None = None) -> dict[str, object]:
        """Return safe structured details from already-fetched divergence refs."""
        snapshot = _current_sync_snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": True,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        from summit_workbench.workflows.sync_conflict_recovery import inspect_divergence

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
                paths=raw_paths or None,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "分叉详情暂时无法读取，请保留当前保护态并导出诊断",
            }
        return {
            "ok": True,
            "available": True,
            "state": snapshot.state.value,
            "details": details.as_dict(),
        }

    @app.get("/api/sync/conflict/validate", response_model=None)
    def api_sync_conflict_validate(paths: str | None = None) -> dict[str, object]:
        """Validate automatic event recovery in an ephemeral, non-git directory."""
        snapshot = _current_sync_snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": True,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        raw_paths = tuple(item.strip() for item in (paths or "").split(",") if item.strip())
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            validate_automatic_recovery,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
                paths=raw_paths or None,
            )
            if not ctx.workspace_id:
                raise GitError("workspace 未配置")
            validation = validate_automatic_recovery(
                ctx.vault_dir,
                details,
                workspace_id=ctx.workspace_id,
                backend_kind=ctx.git_backend_kind,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "临时验证暂时无法执行，请保留当前保护态并导出诊断",
            }
        return {
            "ok": validation.status == "validated",
            "available": True,
            "state": snapshot.state.value,
            "validation": validation.as_dict(),
        }

    @app.get("/api/sync/conflict/export", response_model=None)
    def api_sync_conflict_export() -> Response:
        """Export a body-free recovery manifest; never export vault content or credentials."""
        snapshot = _current_sync_snapshot()
        raw_paths = ()
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            recovery_manifest_bytes,
        )

        plan = plan_conflict_recovery(snapshot.state, raw_paths)
        details = None
        if snapshot.state.value == "diverged-protected":
            try:
                details = inspect_divergence(
                    ctx.vault_dir,
                    backend_kind=ctx.git_backend_kind,
                    workspace_id=ctx.workspace_id,
                )
            except (ValueError, GitError):
                details = None
            if details is not None:
                plan = plan_conflict_recovery(
                    snapshot.state, tuple(path.path for path in details.paths)
                )
        return Response(
            content=recovery_manifest_bytes(snapshot.state, plan, details),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="summitworkbench-sync-recovery.zip"',
                "Cache-Control": "no-store, max-age=0",
            },
        )

    @app.post("/api/sync/conflict/selection/validate", response_model=None)
    def api_sync_conflict_selection_validate(
        payload: SyncConflictSelectionPayload,
    ) -> dict[str, object]:
        """Validate explicit choices against the current read-only divergence snapshot."""
        snapshot = _current_sync_snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        from summit_workbench.workflows.sync_conflict_recovery import (
            inspect_divergence,
            validate_manual_selections,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
            )
            result = validate_manual_selections(
                details,
                base_revision=payload.base_revision,
                local_revision=payload.local_revision,
                remote_revision=payload.remote_revision,
                selections=payload.selections,
            )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前分叉快照暂时无法读取，请重新打开冲突详情",
            }
        return {
            "ok": result.status == "validated",
            "available": True,
            "state": snapshot.state.value,
            "selection": result.as_dict(),
        }

    @app.post("/api/sync/conflict/recover", response_model=None)
    def api_sync_conflict_recover(
        payload: SyncConflictRecoveryPayload,
    ) -> dict[str, object]:
        """Prepare or explicitly apply a revision-bound local recovery merge."""
        snapshot = _current_sync_snapshot()
        if snapshot.state.value != "diverged-protected":
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "当前 workspace 不在 diverged-protected 状态",
            }
        if not ctx.workspace_id:
            return {
                "ok": False,
                "available": False,
                "state": snapshot.state.value,
                "reason": "workspace 未配置",
            }
        from summit_workbench.workflows.sync_conflict_recovery import (
            apply_prepared_recovery,
            inspect_divergence,
            prepare_automatic_recovery,
            prepare_manual_recovery,
        )

        try:
            details = inspect_divergence(
                ctx.vault_dir,
                backend_kind=ctx.git_backend_kind,
                workspace_id=ctx.workspace_id,
            )
            if (
                details.base_revision != payload.base_revision
                or details.local.revision != payload.local_revision
                or details.remote.revision != payload.remote_revision
            ):
                return {
                    "ok": False,
                    "available": True,
                    "state": snapshot.state.value,
                    "recovery": {
                        "status": "stale",
                        "error_code": "conflict_snapshot_stale",
                    },
                }
            if details.manual_path_count or payload.selections:
                prepared = prepare_manual_recovery(
                    ctx.vault_dir,
                    details,
                    workspace_id=ctx.workspace_id,
                    selections=payload.selections,
                    backend_kind=ctx.git_backend_kind,
                )
            else:
                prepared = prepare_automatic_recovery(
                    ctx.vault_dir,
                    details,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                )
            with prepared:
                if not payload.confirmed:
                    return {
                        "ok": False,
                        "available": True,
                        "state": snapshot.state.value,
                        "preparation": prepared.as_dict(),
                        "recovery": {
                            "status": "confirmation-required"
                            if prepared.ready
                            else "preparation-not-ready",
                            "error_code": "explicit_confirmation"
                            if prepared.ready
                            else prepared.error_code,
                        },
                    }
                result = apply_prepared_recovery(
                    ctx.vault_dir,
                    prepared,
                    workspace_id=ctx.workspace_id,
                    confirm=True,
                    backend_kind=ctx.git_backend_kind,
                )
        except (ValueError, GitError):
            return {
                "ok": False,
                "available": True,
                "state": snapshot.state.value,
                "reason": "恢复准备暂时无法执行，请保留当前保护态并重新读取分叉详情",
            }
        push: dict[str, object] | None = None
        if result.status == "committed":
            from summit_workbench.workflows.sync_coordinator import push_after_commit

            try:
                push_state, push_snapshot = push_after_commit(
                    ctx.vault_dir,
                    home=ctx.active_workspace.home if ctx.active_workspace else None,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                    context=ctx.active_workspace,
                )
                push = {
                    "ok": push_state.value == "ready",
                    "state": push_state.value,
                    "detail": push_snapshot.detail if push_snapshot is not None else None,
                }
            except (ValueError, GitError):
                push = {
                    "ok": False,
                    "state": "error",
                    "detail": "恢复提交已保留，但普通同步暂未完成",
                }
        current = _current_sync_snapshot()
        return {
            "ok": result.status == "committed",
            "available": True,
            "state": current.state.value,
            "recovery": result.as_dict(),
            "push": push,
        }

    @app.get("/api/sync/export", response_model=None)
    def api_sync_export() -> dict[str, object]:
        """导出脱敏的本机同步状态副本，不读 token、不修改共享 vault。"""
        return _sync_payload()

    @app.post("/api/sync/primary/claim", response_model=None)
    def api_claim_primary(
        request: Request, payload: AutomationPrimaryPayload
    ) -> dict[str, object] | JSONResponse:
        """显式声明/接管 automation-primary，并作为 wb 提交同步。"""
        if ctx.active_workspace is None or ctx.workspace_id is None:
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active profile 可以声明 workspace 主设备",
                    operation_id=_operation_id(request),
                ),
            )
        from summit_workbench.repositories.automation_primary import claim_automation_primary

        try:
            result = _run_web_mutation(
                "sync/primary",
                lambda _operation_id: LocalMutationOutcome(
                    claim_automation_primary(
                        ctx.vault_dir,
                        ctx.workspace_id or "",
                        payload.device_id,
                        expected_generation=payload.expected_generation,
                        takeover=payload.takeover,
                    ),
                    (ctx.vault_dir / ".summit-workbench" / "automation-primary.json",),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - stable API envelope
            code = getattr(exc, "code", "primary_claim_failed")
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code=code, message=str(exc), operation_id=_operation_id(request)
                ),
            )
        return {
            "ok": True,
            "claim": result.business_return.model_dump(mode="json"),
            **_mutation_fields(result),
        }

    @app.post("/api/sync/run", response_model=None)
    def api_sync_run(request: Request) -> dict[str, object] | JSONResponse:
        """手动触发一次同步（fetch → ff → push，绝不 force）。"""
        state, outcomes, _ = sync_coordinator.sync_workspace(
            ctx.vault_dir,
            work_root=ctx.work_root,
            home=ctx.active_workspace.home if ctx.active_workspace else None,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )
        return {
            "ok": True,
            "state": state.value,
            "repos": [{"name": name, "state": repo_state.value} for name, repo_state in outcomes],
        }

    return app
