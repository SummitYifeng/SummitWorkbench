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
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

if TYPE_CHECKING:
    from summit_workbench.providers.llm.config import ModelConfig
    from summit_workbench.workflows.ask.ask import AskTurn

from summit_workbench.config.git_credentials import profile_identity
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.review import CandidateDecision, ReviewEntry, RouteTarget
from summit_workbench.domain.threaddoc import ArtifactIndex, ArtifactKind, LogDigest
from summit_workbench.domain.workspace import Compatibility, DeviceRole
from summit_workbench.observability.status import build_status
from summit_workbench.repositories.autocommit import (
    CommitResult,
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
from summit_workbench.repositories.project_registry import (
    archive_project,
    create_project_note,
    ensure_project_active,
    load_project_registry,
)
from summit_workbench.repositories.project_scan import (
    count_inbox_pending,
    is_internal_dirname,
    scan_all_projects,
)
from summit_workbench.repositories.project_view import build_project_view
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
    ArtifactSavePayload,
    AskPayload,
    AutomationPrimaryPayload,
    BatchDecidePayload,
    CapturePayload,
    DecidePayload,
    EditPayload,
    ExternalActionReconcilePayload,
    LogAppendPayload,
    MeetingEditPayload,
    OnboardingCreatePayload,
    OnboardingDraftPayload,
    OnboardingPreflightPayload,
    OnboardingRemoteConfirmPayload,
    OnboardingRemoteStagePayload,
    OnboardingVaultPayload,
    ProjectCreatePayload,
    ProjectPayload,
    ProjectRenamePayload,
    ProjectStatePayload,
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
    mode_from_environment,
    new_server_instance,
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
    # P0-06：工作区锁根（WorkspacePaths.lock_root）。None 时回退旧语义（env 默认）。
    lock_root: Path | None = None
    # P0-07C：production 由 active profile 冻结的运行时上下文。
    active_workspace: ActiveWorkspaceContext | None = None
    config_file: Path | None = None

    @classmethod
    def from_active_workspace(cls, context: ActiveWorkspaceContext) -> WebContext | None:
        if context.paths is None or context.profile is None or not context.can_read:
            return None
        return cls(
            vault_dir=context.paths.vault_dir,
            work_root=context.paths.work_root,
            timezone=context.timezone,
            lock_root=context.paths.lock_root,
            active_workspace=context,
            config_file=context.config_file,
        )

    def provider_config_file(self) -> Path:
        return self.config_file or default_config_file()

    @property
    def workspace_id(self) -> str | None:
        return self.active_workspace.workspace_id if self.active_workspace else None

    @property
    def compatibility(self) -> Compatibility:
        if self.active_workspace and self.active_workspace.compatibility is not None:
            return self.active_workspace.compatibility
        return Compatibility.READ_WRITE

    def today(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).date().isoformat()

    @property
    def git_backend_kind(self) -> str | None:
        """production active profile 固定 Dulwich；旧兼容 context 不覆盖默认 backend。"""
        return "dulwich" if self.active_workspace is not None else None


def _load_model_config_for_context(ctx: WebContext, capability: str) -> ModelConfig:
    """Load legacy test/development config without changing its monkeypatch contract."""
    from summit_workbench.providers.llm import load_model_config

    if ctx.workspace_id is None and ctx.config_file is None:
        return load_model_config(capability)
    return load_model_config(
        capability,
        ctx.provider_config_file(),
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

            if self._config_file is None and self._workspace_id is None:
                cfg = load_feishu_config()
            else:
                cfg = load_feishu_config(
                    self._config_file,
                    workspace_id=self._workspace_id,
                )
            session = FeishuSession(cfg, lock_root=self._lock_root)
            token = session.access_token() if identity == "user" else session.tenant_access_token()
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


def _commit_note(result: CommitResult) -> str:
    if result.status in {
        CommitStatus.FAILED,
        CommitStatus.BUSY,
        CommitStatus.INDEX_NOT_CLEAN,
    }:
        return f"（git 留痕失败：{result.detail or result.status.value}）"
    return ""


def _mutation_fields[T](result: LocalMutationResult[T]) -> dict[str, object]:
    """把本地事务的 operation id 与可见提交状态加入 API 响应。"""
    return {
        "operation_id": result.operation_id,
        "commit": result.commit_result.as_dict(),
    }


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
  const state={flow:null,step:0,work_root:'',vault_dir:'',display_name:'',device_name:'',git_mode:'skipped',remote_url:'',expected_workspace_id:'',git_username:'',automation_role:'primary',stage_id:null};
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
      if(state.git_mode==='remote')html+=field('remote_url','HTTPS 远端地址',state.remote_url,'url','https://git.example.com/team/workspace.git')+field('git_username','远端用户名',state.git_username,'text','你的用户名')+field('expected_workspace_id','预期 workspace id（连接已有远端时填写）',state.expected_workspace_id,'text','从原设备的工作区信息复制');
    } else if(steps[state.step]==='model'){
      html+='<p>模型配置可稍后在设置中心完成。跳过不会影响本地捕捉和知识库使用。</p><div class="notice">当前选择：稍后设置。此步骤不收集或保存任何密钥。</div>';
    } else if(steps[state.step]==='feishu'){
      html+='<p>飞书登录可稍后完成。跳过后仍可使用本地工作台与捕捉。</p><div class="notice">当前选择：稍后登录。授权会在你明确开始时进行。</div>';
    } else if(steps[state.step]==='role'){
      html+='<p>新建工作台默认由本机负责自动化；连接已有工作台默认是辅助设备。</p><label for="automation_role">设备角色</label><select id="automation_role"><option value="primary"'+(state.automation_role==='primary'?' selected':'')+'>主设备</option><option value="secondary"'+(state.automation_role==='secondary'?' selected':'')+'>辅助设备</option></select><div class="notice">更换已有工作区的主设备需要在后续同步设置中明确接管并确认影响。</div>';
    } else {html+='<p>请确认后完成设置。最终结果以服务端返回的 workspace/device 信息为准。</p><ul><li>流程：'+esc(state.flow)+'</li><li>位置：'+esc(state.work_root||state.vault_dir)+'</li><li>同步：'+esc(state.git_mode)+'</li><li>设备角色：'+esc(state.automation_role)+'</li></ul>'}
    html+='<div class="row"><button class="text" data-back="1">返回</button><div><button data-next="1">'+(steps[state.step]==='check'?'完成设置':'继续')+'</button></div></div>';content.innerHTML=html;
  }
  function read(){for(const id of ['work_root','vault_dir','display_name','remote_url','git_username','expected_workspace_id']){const el=document.getElementById(id);if(el)state[id]=el.value.trim()}const role=document.getElementById('automation_role');if(role)state.automation_role=role.value}
  async function next(){read();const current=steps[state.step];if(current==='location'){const path=state.flow==='create-new'?state.work_root:state.vault_dir;await api('/api/onboarding/preflight',{method:'POST',body:JSON.stringify({flow:state.flow==='connect-existing'?'connect-local':state.flow,path})})}if(current==='git'&&state.git_mode==='remote'&&!state.remote_url)throw new Error('请填写 HTTPS 远端地址');if(current==='check')return complete();state.step++;await save();render()}
  async function complete(){await save();let d;if(state.flow==='create-new')d=await api('/api/onboarding/create',{method:'POST',body:JSON.stringify({work_root:state.work_root,display_name:state.display_name||null,device_name:state.device_name||null,device_role:state.automation_role==='primary'?'automation-primary':'secondary'})});else if(state.flow==='upgrade-existing')d=await api('/api/onboarding/upgrade',{method:'POST',body:JSON.stringify({vault_dir:state.vault_dir,display_name:state.display_name||null,device_name:state.device_name||null,device_role:state.automation_role==='primary'?'automation-primary':'secondary'})});else if(state.git_mode==='remote'){const staged=await api('/api/onboarding/remote/stage',{method:'POST',body:JSON.stringify({remote_url:state.remote_url,target_vault:state.vault_dir,expected_workspace_id:state.expected_workspace_id||null,git_username:state.git_username})});d=await api('/api/onboarding/remote/confirm',{method:'POST',body:JSON.stringify({stage_id:staged.stage_id,display_name:state.display_name||null,device_name:state.device_name||null})})}else d=await api('/api/onboarding/connect',{method:'POST',body:JSON.stringify({vault_dir:state.vault_dir,display_name:state.display_name||null,device_name:state.device_name||null,device_role:'secondary'})});await api('/api/onboarding/draft',{method:'DELETE'});content.innerHTML='<h2>设置完成</h2><div class="success">工作区已准备好。workspace id：'+esc(d.workspace_id)+'<br>本机 device id：'+esc(d.device_id)+'<br><br>请重新打开 SummitWorkbench 进入工作台。</div>';progress.textContent='完成';}
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
            if origin is not None and not origin_matches(
                origin, request.url.scheme, host_allowlist
            ):
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
        return HTMLResponse(_onboarding_wizard_html())

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

        try:
            staged = stage_remote_clone(
                payload.remote_url,
                Path(payload.target_vault).expanduser(),
                workspace_id=payload.expected_workspace_id,
                username=payload.git_username,
                home=active_workspace.home,
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
            if origin is not None and not origin_matches(
                origin, request.url.scheme, host_allowlist
            ):
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

    @app.get("/api/version")
    def api_version(request: Request) -> JSONResponse:
        """轻量 readiness + build handshake；静态构建无效时明确返回 503。"""
        try:
            info = _build_info()
        except BuildInfoError as exc:
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    code="invalid_build_manifest",
                    message=str(exc),
                    operation_id=_operation_id(request),
                ),
                headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
            )
        return JSONResponse(
            content=info.version_payload(
                server_instance=server_instance,
                started_at=started_at,
                mode=panel_mode,
                workspace_id=workspace_id or ctx.workspace_id,
                device_id=device_id
                or (ctx.active_workspace.device_id if ctx.active_workspace else None),
                port=getattr(app.state, "bound_port", None),
            ),
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )

    @app.get("/api/session/bootstrap", include_in_schema=False)
    def session_bootstrap(request: Request, token: str) -> Response:
        expected_token = session_token or os.environ.get("WB_SESSION_TOKEN")
        if panel_mode == "production" or not session_token_matches(token, expected_token):
            return JSONResponse(
                status_code=401,
                content=error_payload(
                    code="authentication_required",
                    message="一次性会话令牌无效",
                    operation_id=_operation_id(request),
                ),
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, path="/"
        )
        return response

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

    def _project_target(name: str) -> tuple[bool, str]:
        """校验「加入/归档工作台」的目标：Work 仓库文件夹 或 已建档的知识线程。

        返回 (ok, 错误消息)。下划线前缀目录是系统内部目录，一律不允许操作。
        """
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            return False, f"非法项目名：{name}"
        if is_internal_dirname(name):
            return False, f"{name} 是系统内部目录，不能作为项目操作"
        folder = ctx.work_root / name
        if folder.is_dir():
            return True, ""
        registry = load_project_registry(ctx.vault_dir)
        if name in registry.canonical:
            return True, ""
        return False, f"work_root 下没有该项目文件夹，vault 中也没有 {name} 的档案"

    @app.post("/api/projects/rename")
    def api_project_rename(payload: ProjectRenamePayload) -> dict[str, object]:
        """设置项目/线程的显示名（写档案 frontmatter ``title``；不影响 ID/别名/文件夹）。"""
        name = payload.name.strip()
        title = payload.title.strip()
        if not title:
            return {"ok": False, "message": "显示名不能为空"}
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(name)
        if project is None:
            return {"ok": False, "message": f"项目未建档：{name}"}
        path = ctx.vault_dir / "projects" / f"{project}.md"

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            from summit_workbench.repositories.note_status import update_note_status
            from summit_workbench.repositories.vault import load_note as _load_note

            note = _load_note(path)
            status = note.meta.get("status")
            if not isinstance(status, str):
                raise ValueError(f"项目档案无效：{project}")
            update_note_status(
                ctx.vault_dir, path, status, extra={"title": title, "updated": ctx.today()}
            )
            return LocalMutationOutcome(path, (path,))

        try:
            result = _run_web_mutation("projects/rename", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"改名失败：{exc}"}
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"{project} 显示名已设为「{title}」{git_note}",
            **_mutation_fields(result),
        }

    @app.post("/api/projects/activate")
    def api_project_activate(payload: ProjectPayload) -> dict[str, object]:
        """把项目加入工作台（幂等）：无档案则建档；archived 则恢复为 active。"""
        name = payload.name.strip()
        ok, message = _project_target(name)
        if not ok:
            return {"ok": False, "message": message}
        try:
            result = _run_web_mutation(
                "projects/activate",
                lambda _operation_id: LocalMutationOutcome(
                    (path := ensure_project_active(ctx.vault_dir, name)), (path,)
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"加入工作台失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已加入工作台：{name}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }

    @app.post("/api/projects/archive")
    def api_project_archive(payload: ProjectPayload) -> dict[str, object]:
        """把项目归档（幂等）：置 status: archived，不在首页显示；可随时恢复。"""
        name = payload.name.strip()
        ok, message = _project_target(name)
        if not ok:
            return {"ok": False, "message": message}
        try:
            result = _run_web_mutation(
                "projects/archive",
                lambda _operation_id: LocalMutationOutcome(
                    (path := archive_project(ctx.vault_dir, name)), (path,)
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"归档失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已归档：{name}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }

    @app.post("/api/projects/create")
    def api_project_create(payload: ProjectCreatePayload) -> dict[str, object]:
        """新建知识线程项目：在 vault 建档（不创建任何 Work 文件夹 / git 仓库）。"""
        project_id = payload.project_id.strip()
        if not project_id:
            return {"ok": False, "message": "请输入项目 ID"}
        if is_internal_dirname(project_id):
            return {"ok": False, "message": "项目 ID 不能以下划线开头（保留给系统内部目录）"}
        if (ctx.work_root / project_id).is_dir():
            return {
                "ok": False,
                "message": f"Work 下已有同名文件夹 {project_id}，请用「加入工作台」建档",
            }
        aliases = [alias.strip() for alias in payload.aliases if alias.strip()]
        try:
            result = _run_web_mutation(
                "projects/create",
                lambda _operation_id: LocalMutationOutcome(
                    (
                        path := create_project_note(
                            ctx.vault_dir, project_id, aliases=aliases or None
                        )
                    ),
                    (path,),
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"新建失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已建档知识线程：{project_id}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }

    @app.get("/api/review")
    def api_review() -> dict[str, object]:
        entries, errors = _load(ctx.vault_dir)
        return review_payload(entries, errors)

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

    @app.get("/api/projects/view")
    def api_project_view(name: str) -> dict[str, object]:
        """线视图：某项目/线程的档案区块 + 时间线（logs/artifacts/meetings 聚合）。"""
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(name)
        if project is None:
            return {"ok": False, "message": f"项目未建档：{name}"}
        try:
            view = build_project_view(ctx.vault_dir, project)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **view}

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
            )
            return LocalMutationOutcome(path, (path, *archives))

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

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = save_thread_artifact(
                ctx.vault_dir,
                project=project,
                text=text,
                title=title,
                summary=summary,
                kind=kind,
            )
            return LocalMutationOutcome(path, (path, ctx.vault_dir / "projects" / f"{project}.md"))

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
            return {
                "ok": True,
                "message": f"已生成今日简报（健康度 {run.result.brief.health.level}）",
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
        profile = ctx.active_workspace.profile if ctx.active_workspace else None
        return run_local_mutation(
            ctx.vault_dir,
            action,
            mutation,
            sync_snapshot=_current_sync_snapshot() if ctx.active_workspace else None,
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
            return JSONResponse(
                status_code=403,
                content=error_payload(
                    code="not_automation_primary",
                    message="本机不是该 workspace 的 automation-primary，定时任务不执行",
                    operation_id=_operation_id(request),
                ),
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
