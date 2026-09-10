import './style.css';

import { createApiClient } from './api/client';
import { workspaceScopedKey, workspaceStore } from './core/workspace-store';
import { mutation, deferReloadUntilMutationsComplete, isMutationInFlight, setMutationIdleHandler } from './lifecycle/connection';
import {
  clearDraftSnapshot,
  clearEntityDraft,
  loadDraftSnapshot,
  loadEntityDraft,
  saveDraftSnapshot as persistDraftSnapshot,
  saveEntityDraft,
  type DraftSnapshot,
  type ReviewDraftFields,
} from './lifecycle/drafts';
import {
  canonicalPanelUrl,
  CLIENT_BUILD,
  shouldPreventReload,
  validateVersionPayload,
  type VersionPayload,
  type VersionStatus,
} from './lifecycle/version';
import { notifyClientReady, sendNativeMessage } from './lifecycle/native-bridge';
import { esc, mdToHtml } from './md';
import { briefCardHtml, type BriefData } from './brief-card';
import { projectDisplayName, projectsHtml, projectsListHtml } from './features/projects';
import type { ProjectState, ProjectView } from './features/projects';
import { reviewHtml } from './features/review';
import type { ExternalAction, ReviewEntry, ReviewGroup, ReviewPayload } from './features/review';
import { renderSettings as renderSettingsFeature } from './features/settings';
import { mountToday } from './features/today';
// 使用指南（WEB_USAGE_GUIDE.md 由 npm run sync-guide 在构建前同步；随包内置，离线可看）
import guideMd from './guide.md?raw';

type Tab = 'today' | 'review' | 'ask' | 'projects' | 'guide' | 'settings';

interface StatusUsage {
  estimated_cost: number;
  currency: string;
}
interface StatusBudget {
  over_soft_limit: boolean;
  soft_limit: number | null;
}
interface StatusBacklog {
  count: number;
  oldest_age_days: number | null;
  active: boolean;
  severity: string;
}
interface StatusFeishu {
  needs_reauthorize: boolean;
  detail: string | null;
}
interface StatusState {
  succeeded: number;
  total_meetings: number;
  failed: number;
  unavailable: number;
  pending_review: number;
  usage: StatusUsage;
  budget: StatusBudget;
  backlog: StatusBacklog;
  feishu_auth: StatusFeishu;
}
interface StatePayload {
  day: string;
  status: StatusState;
  brief_md: string | null;
  brief_generated: boolean;
  /** 结构化简报（旧快照无明细时为 null → 前端回退 Markdown 视图） */
  brief?: BriefData | null;
  inbox_pending: number;
  projects: ProjectState[];
  runtime?: {
    frontend_build: string;
    server_version: string;
    server_instance: string;
  };
}
interface SyncStatusPayload {
  ok: boolean;
  workspace_id?: string;
  state: string;
  pending_commits?: number;
  last_sync_at?: string | null;
  ahead?: number;
  behind?: number;
  branch?: string | null;
  remote_host?: string | null;
  repo_states?: string[];
  automation_primary_device_id?: string | null;
  automation_primary_generation?: number | null;
  detail?: string;
  next_step?: string;
}
interface DiagnosticsPreviewPayload {
  ok: boolean;
  files: Array<{ name: string; description: string }>;
  snapshot: Record<string, unknown>;
}

type ConflictSelection = 'keep-local' | 'keep-remote' | 'preserve-both' | '';
interface ConflictPathDetail {
  path: string;
  kind: string;
  action: string;
  automatic: boolean;
  changed_on: string[];
  local_sha256: string | null;
  remote_sha256: string | null;
  local_event?: Record<string, string> | null;
  remote_event?: Record<string, string> | null;
}
interface ConflictDetails {
  base_revision: string;
  local: { revision: string; authored_at: string; changed_path_count: number };
  remote: { revision: string; authored_at: string; changed_path_count: number };
  automatic_path_count: number;
  manual_path_count: number;
  paths: ConflictPathDetail[];
}
interface SyncConflictDetailsPayload {
  ok: boolean;
  available: boolean;
  state: string;
  details?: ConflictDetails;
  reason?: string;
}
interface RecoveryPreparationSummary {
  status: string;
  ok: boolean;
  event_count: number;
  aggregate_count: number;
  generated_view_count: number;
  rebuilt_view_count: number;
  candidate_path_count: number;
  staging_ready: boolean;
  error_code: string | null;
}
interface SyncConflictRecoveryPayload {
  ok: boolean;
  available: boolean;
  state: string;
  preparation?: RecoveryPreparationSummary;
  recovery?: {
    status: string;
    revision?: string | null;
    error_code?: string | null;
    audit?: { status: string; error_code?: string | null };
  };
  push?: { ok: boolean; state: string; detail?: string | null } | null;
  reason?: string;
}

let state: StatePayload | null = null;
let review: ReviewPayload | null = null;
let externalActions: ExternalAction[] = [];
let tab: Tab = 'today';
let importing = false;
let importOpen = false;
let capturing = false;
let draftStorageWarningShown = false;
let importResult: {
  fileName: string;
  bytes: number;
  status: 'processing' | 'success' | 'error';
  message: string;
  details?: string[];
  estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
} | null = null;
let stateLoadError: string | null = null;
let reviewLoadError: string | null = null;
let externalActionsError: string | null = null;
let reviewPlanReady = false;
let modalReturnFocus: HTMLElement | null = null;
let lastStateReadAt: string | null = null;
let lastReviewReadAt: string | null = null;
let reviewDrafts: Record<string, ReviewDraftFields> = {};
let apiRequestSequence = 0;
let latestStateRequest = 0;
let latestReviewRequest = 0;

class StaleWorkspaceResponseError extends Error {
  constructor() {
    super('工作区已切换，忽略旧请求结果');
    this.name = 'StaleWorkspaceResponseError';
  }
}

function isStaleWorkspaceResponse(error: unknown): boolean {
  return error instanceof StaleWorkspaceResponseError;
}
let versionStatus: VersionStatus = 'checking';
let remoteVersion: VersionPayload | null = null;
let lastServerInstance: string | null = null;
let versionCheckPromise: Promise<void> | null = null;
let connectionHadFailure = false;
let restoredDraft: DraftSnapshot | null = null;
let loadedAskWorkspace = 'unknown';
let conflictDetails: ConflictDetails | null = null;
let conflictSelections: Record<string, ConflictSelection> = {};
let conflictPreparation: RecoveryPreparationSummary | null = null;
let conflictMessage: string | null = null;
let conflictBusy = false;

// ---------- 第二大脑（对话式问答，localStorage 持久化） ----------

interface AskMsg {
  role: 'user' | 'ai';
  /** user：原文（追问时回传）；ai：服务端渲染的答案 HTML */
  text: string;
  ts: string;
  /** ai 消息本次召回/引用的来源 id（追问时回传，让后端重新纳入候选） */
  sources: string[];
}
interface AskThread {
  id: string;
  title: string;
  createdAt: string;
  messages: AskMsg[];
}
interface AskHistoryTurn {
  question: string;
  sources: string[];
}
interface AskResponse {
  ok: boolean;
  message?: string;
  answer_html?: string;
  source_ids?: string[];
}

const ASK_MAX_THREADS = 10;
/** 追问时最多回传的历史轮数（与后端 _MAX_HISTORY_TURNS 同口径） */
const ASK_MAX_HISTORY = 6;
let askThreads: AskThread[] = [];
let askActiveId: string | null = null;
let askBusy = false;
/** 正在请求的会话 id（切换会话时「思考中…」只出现在真正等待的那个会话） */
let askBusyThreadId: string | null = null;
/** 输入框草稿：renderAskChat 会整体重建输入区，等待期间打的新问题不能丢 */
let askDraft = '';
let askErrors: Record<string, string> = {};
/** 问答检索范围：''=全部；否则为项目/线程名（后端按 registry 解析） */
let askScope = '';

function askStorageKey(): string {
  return workspaceScopedKey('wb.ask.threads.v1', workspaceStore.workspaceId);
}

function askDraftEntity(threadId: string): string {
  return 'ask:' + threadId;
}

const app = document.getElementById('app') as HTMLElement;
const toasts = document.getElementById('toasts') as HTMLElement;

const apiClient = createApiClient({
  onFailure: () => { connectionHadFailure = true; },
  onSuccess: (url) => {
    if (connectionHadFailure && url !== '/api/version') {
      connectionHadFailure = false;
      void checkVersion('connection-restored');
    }
  },
});

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const generation = workspaceStore.generation;
  const requestSequence = ++apiRequestSequence;
  const headers = new Headers(init?.headers);
  headers.set('X-WB-Workspace-Generation', String(generation));
  headers.set('X-WB-Request-Sequence', String(requestSequence));
  const result = await apiClient.request<T>(url, { ...init, headers });
  if (generation !== workspaceStore.generation) throw new StaleWorkspaceResponseError();
  return result;
}

function persistEntityDraft<T>(entity: string, value: T): void {
  if (saveEntityDraft(entity, value, remoteVersion?.workspace_id)) return;
  if (!draftStorageWarningShown) {
    draftStorageWarningShown = true;
    toast('浏览器暂时无法保存草稿；请先完成当前编辑再切页', 'err');
  }
}

function toast(msg: string, kind: 'ok' | 'err' | 'info' = 'info'): void {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  toasts.appendChild(el);
  window.setTimeout(() => el.remove(), 4600);
}

function healthTone(): { tone: string; label: string } {
  if (!state) return { tone: 'idle', label: '连接中…' };
  const s = state.status;
  if (s.failed > 0 || s.feishu_auth.needs_reauthorize) {
    return { tone: 'bad', label: '有异常待处理' };
  }
  if (s.backlog.active || s.budget.over_soft_limit) {
    return { tone: 'warn', label: '有积压/接近预算' };
  }
  return { tone: 'ok', label: '一切正常' };
}

function fmtCost(v: number, cur: string): string {
  if (cur === 'CNY') return '¥' + v.toFixed(2);
  return v.toFixed(4) + ' ' + cur;
}

function versionStatusLabel(status: VersionStatus): string {
  if (status === 'checking') return '正在检查版本';
  if (status === 'synced') {
    return remoteVersion
      ? '界面 ' + CLIENT_BUILD + ' · 服务 ' + remoteVersion.server_version + ' · 已同步'
      : '已同步';
  }
  if (status === 'update-pending') return '新版本已就绪';
  if (status === 'reconnecting') return '正在重新连接';
  return '更新未完成';
}

function setVersionStatus(status: VersionStatus): void {
  versionStatus = status;
  const el = document.getElementById('version-status');
  if (el) {
    el.className = 'version-status ' + status;
    el.textContent = versionStatusLabel(status);
  }
  const banner = document.getElementById('version-error-banner');
  if (banner) banner.hidden = status !== 'failed';
}

function saveCurrentDraftSnapshot(): void {
  const reviewForms: Record<string, ReviewDraftFields> = {};
  const editForms = document.querySelectorAll<HTMLFormElement>('.edit-form');
  editForms.forEach((form) => {
    const data = new FormData(form);
    const candidateId = String(data.get('candidate_id') ?? '');
    if (!candidateId) return;
    reviewForms[candidateId] = {
      description: String(data.get('description') ?? ''),
      target_project: String(data.get('target_project') ?? ''),
      route: String(data.get('route') ?? ''),
      due_date: String(data.get('due_date') ?? ''),
      start_at: String(data.get('start_at') ?? ''),
      end_at: String(data.get('end_at') ?? ''),
    };
  });
  if (editForms.length > 0) reviewDrafts = reviewForms;
  const persistedReviewForms = editForms.length > 0 ? reviewForms : reviewDrafts;
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  const ask = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (ask) askDraft = ask.value;
  const saved = persistDraftSnapshot({
    schema: 1,
    saved_at: new Date().toISOString(),
    source_build: CLIENT_BUILD,
    tab,
    scroll_y: window.scrollY,
    capture_text: capture?.value ?? '',
    ask_draft: askDraft,
    review_forms: persistedReviewForms,
  }, remoteVersion?.workspace_id);
  if (!saved && !draftStorageWarningShown) {
    draftStorageWarningShown = true;
    toast('浏览器暂时无法保存草稿；版本更新仍会继续，但请先完成当前编辑', 'err');
  }
}

function applyRestoredDraft(): void {
  const draft = restoredDraft;
  if (!draft) return;
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  if (capture) capture.value = draft.capture_text;
  askDraft = draft.ask_draft;
  reviewDrafts = draft.review_forms;
  const ask = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (ask) ask.value = draft.ask_draft;
  document.querySelectorAll<HTMLFormElement>('.edit-form').forEach((form) => {
    const candidateId = String(new FormData(form).get('candidate_id') ?? '');
    const fields = draft.review_forms[candidateId];
    if (!fields) return;
    for (const [name, value] of Object.entries(fields)) {
      const input = form.elements.namedItem(name);
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement || input instanceof HTMLSelectElement) {
        input.value = value;
      }
    }
  });
  window.scrollTo({ top: draft.scroll_y, behavior: 'instant' as ScrollBehavior });
  clearDraftSnapshot(remoteVersion?.workspace_id);
  toast('已恢复更新前草稿（未自动提交）', 'info');
  restoredDraft = null;
}

function reloadToBuild(targetBuild: string): void {
  try {
    window.sessionStorage.setItem('wb.update.last-target', targetBuild);
    window.sessionStorage.setItem('wb.update.last-attempt-at', new Date().toISOString());
  } catch {
    // sessionStorage 不可用时仍尝试导航；页面自身会通过 URL 继续握手。
  }
  setVersionStatus('update-pending');
  window.location.assign(canonicalPanelUrl(window.location.href, targetBuild));
}

async function copyDiagnostics(): Promise<void> {
  const lines = [
    'App frontend client build: ' + CLIENT_BUILD,
    'Served frontend build: ' + (remoteVersion?.frontend_build ?? 'unknown'),
    'Server version/instance: ' + (remoteVersion?.server_version ?? 'unknown') +
      '/' + (remoteVersion?.server_instance ?? 'unknown'),
    'Panel mode: ' + (remoteVersion?.mode ?? 'unknown'),
    'API protocol: ' + (remoteVersion?.api_protocol ?? 'unknown'),
  ];
  try {
    await navigator.clipboard.writeText(lines.join('\n'));
    toast('诊断信息已复制', 'ok');
  } catch {
    toast(lines.join(' · '), 'info');
  }
}

async function previewDiagnostics(): Promise<void> {
  const target = document.getElementById('diagnostics-preview');
  try {
    const result = await api<DiagnosticsPreviewPayload>('/api/diagnostics/preview');
    if (target) {
      target.innerHTML = '<div class="success"><strong>导出内容预览</strong><ul>' +
        result.files.map((file) => '<li><code>' + esc(file.name) + '</code>：' + esc(file.description) + '</li>').join('') +
        '</ul></div>';
    }
    toast('诊断包预览已生成', 'ok');
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function exportDiagnostics(): Promise<void> {
  try {
    const response = await fetch('/api/diagnostics/export', { cache: 'no-store' });
    if (!response.ok) throw new Error('诊断包导出失败（HTTP ' + response.status + '）');
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'summitworkbench-diagnostics.zip';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(link.href);
      link.remove();
    }, 1000);
    toast('诊断包已导出', 'ok');
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function doCheckVersion(reason: string): Promise<void> {
  setVersionStatus('checking');
  const response = await fetch('/api/version', { cache: 'no-store' });
  if (!response.ok) throw new Error('version HTTP ' + response.status + ' (' + reason + ')');
  const remote = validateVersionPayload(await response.json());
  const instanceChanged = lastServerInstance !== null && lastServerInstance !== remote.server_instance;
  lastServerInstance = remote.server_instance;
  remoteVersion = remote;
  const workspaceId = remote.workspace_id ?? 'unknown';
  workspaceStore.setWorkspace(workspaceId);
  if (loadedAskWorkspace !== workspaceId) {
    state = null;
    review = null;
    stateLoadError = null;
    reviewLoadError = null;
    lastStateReadAt = null;
    lastReviewReadAt = null;
    askThreads = [];
    askActiveId = null;
    askDraft = '';
    askErrors = {};
    askBusy = false;
    askBusyThreadId = null;
    loadedAskWorkspace = workspaceId;
    loadAskStore();
  }
  if (remote.frontend_build === CLIENT_BUILD) {
    setVersionStatus('synced');
    notifyClientReady(CLIENT_BUILD, remote.server_instance);
    if (instanceChanged) await refreshAll();
    return;
  }

  saveCurrentDraftSnapshot();
  if (shouldPreventReload(window.sessionStorage, remote.frontend_build, Date.now())) {
    setVersionStatus('failed');
    return;
  }
  if (isMutationInFlight()) {
    setVersionStatus('update-pending');
    deferReloadUntilMutationsComplete(remote.frontend_build);
    return;
  }
  reloadToBuild(remote.frontend_build);
}

function checkVersion(reason: string): Promise<void> {
  if (versionCheckPromise) return versionCheckPromise;
  versionCheckPromise = doCheckVersion(reason)
    .catch(() => setVersionStatus('reconnecting'))
    .finally(() => { versionCheckPromise = null; });
  return versionCheckPromise;
}

// ---------- 渲染 ----------

function render(): void {
  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    const active = b.dataset.tab === tab;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', active ? 'true' : 'false');
    b.setAttribute('tabindex', active ? '0' : '-1');
  });
  const todayView = document.getElementById('view-today') as HTMLElement;
  const reviewView = document.getElementById('view-review') as HTMLElement;
  const askView = document.getElementById('view-ask') as HTMLElement;
  const projectsView = document.getElementById('view-projects') as HTMLElement;
  const guideView = document.getElementById('view-guide') as HTMLElement;
  const settingsView = document.getElementById('view-settings') as HTMLElement;
  todayView.style.display = tab === 'today' ? '' : 'none';
  reviewView.style.display = tab === 'review' ? '' : 'none';
  askView.style.display = tab === 'ask' ? '' : 'none';
  projectsView.style.display = tab === 'projects' ? '' : 'none';
  guideView.style.display = tab === 'guide' ? '' : 'none';
  settingsView.style.display = tab === 'settings' ? '' : 'none';
  [todayView, reviewView, askView, projectsView, guideView, settingsView].forEach((view) => {
    view.setAttribute('aria-hidden', view.style.display === 'none' ? 'true' : 'false');
  });
  if (tab === 'today') {
    renderToday(todayView);
  } else if (tab === 'review') {
    renderReview(reviewView);
  } else if (tab === 'projects') {
    renderProjects(projectsView);
  } else if (tab === 'guide') {
    renderGuide(guideView);
  } else if (tab === 'settings') {
    void renderSettings(settingsView);
  } else {
    renderAsk(askView);
  }
  applyRestoredDraft();
}

function renderShell(): void {
  app.innerHTML =
    '<a class="skip-link" href="#main-content">跳到主内容</a>' +
    '<div class="nav-shell"><header class="topbar">' +
    '<div class="brand"><span class="logo">SW</span><div><h1>SummitWorkbench</h1>' +
    '<p class="tagline">外置执行管理层 · 第二大脑</p></div></div>' +
    '<div class="header-right">' +
    '<span class="version-status checking" id="version-status">正在检查版本</span>' +
    '<span class="day-pill" id="day-pill">—</span>' +
    '<button class="ghost" id="btn-refresh" title="刷新">↻</button>' +
    '<button class="ghost" id="btn-check-updates" title="检查更新">检查更新</button>' +
    '<button class="ghost" id="btn-undo" title="撤销系统改动（只作用于 vault 文件）">↩ 撤销</button>' +
    '<button class="ghost" id="btn-quit" title="退出工作台（停止本地服务）">退出</button>' +
    '</div></header>' +
    '<div class="sync-banner" id="sync-banner" hidden></div>' +
    '<div class="version-error-banner" id="version-error-banner" hidden>' +
    '<span>工作台更新未完成。你的草稿已保留。</span>' +
    '<button class="ghost" data-action="retry-update">重试更新</button>' +
    '<button class="ghost" data-action="copy-diagnostics">复制诊断信息</button>' +
    '</div>' +
    '<nav class="tabs" role="tablist" aria-label="工作台页面">' +
    '<button class="tab" id="tab-today" data-tab="today" aria-controls="view-today" role="tab">今日</button>' +
    '<button class="tab" id="tab-review" data-tab="review" aria-controls="view-review" role="tab">审批 <span class="tab-badge" id="tab-badge-review"></span></button>' +
    '<button class="tab" id="tab-ask" data-tab="ask" aria-controls="view-ask" role="tab">第二大脑</button>' +
    '<button class="tab" id="tab-projects" data-tab="projects" aria-controls="view-projects" role="tab">项目</button>' +
    '<button class="tab" id="tab-guide" data-tab="guide" aria-controls="view-guide" role="tab">指南</button>' +
    '<button class="tab" id="tab-settings" data-tab="settings" aria-controls="view-settings" role="tab">设置</button>' +
    '</nav></div>' +
    '<main id="main-content" tabindex="-1">' +
    '<section id="view-today" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-review" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-ask" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-projects" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-guide" class="view" role="tabpanel" tabindex="0"></section>' +
    '<section id="view-settings" class="view" role="tabpanel" tabindex="0"></section>' +
    '</main>' +
    '<div class="modal-backdrop" id="modal-backdrop" hidden><div class="modal" id="modal"></div></div>';

  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    b.addEventListener('click', () => {
      const next = b.dataset.tab;
      tab = next === 'review' || next === 'ask' || next === 'projects' || next === 'guide' || next === 'settings' ? next : 'today';
      render();
      b.focus();
    });
    b.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>('.tab'));
      const index = tabs.indexOf(b);
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
        (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      const nextButton = tabs[nextIndex];
      const next = nextButton?.dataset.tab;
      tab = next === 'review' || next === 'ask' || next === 'projects' || next === 'guide' || next === 'settings' ? next : 'today';
      render();
      nextButton?.focus();
    });
  });
  (document.getElementById('btn-refresh') as HTMLButtonElement).addEventListener('click', () => {
    void Promise.all([refreshAll(), refreshSyncBanner()]).then(([result]) => {
      toast(result.state && result.review ? '已刷新' : '刷新未完成：保留了可用的旧数据', result.state && result.review ? 'ok' : 'err');
    });
  });
  (document.getElementById('btn-check-updates') as HTMLButtonElement).addEventListener('click', () => {
    if (sendNativeMessage({ type: 'checkForUpdates' })) {
      toast('正在检查更新', 'info');
    } else {
      toast('更新检查仅支持已安装的 macOS App', 'info');
    }
  });
  (document.getElementById('btn-undo') as HTMLButtonElement)?.addEventListener('click', () => {
    void openUndoModal();
  });
  (document.getElementById('btn-quit') as HTMLButtonElement).addEventListener('click', () => {
    if (!window.confirm('确定退出工作台并停止本地服务？')) return;
    if (sendNativeMessage({ type: 'quit' })) return;
    void api<{ ok: boolean; message: string }>('/api/shutdown', {
      method: 'POST',
      headers: { 'X-WB-Shutdown': '1' },
    }).then((r) => {
      toast(r.message, r.ok ? 'ok' : 'err');
      window.setTimeout(() => window.close(), 800);
    }).catch((err: unknown) => {
      // 服务已关闭时请求可能直接失败；仍尝试关窗
      toast(String(err), 'err');
      window.setTimeout(() => window.close(), 800);
    });
  });
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement;
  backdrop.addEventListener('click', (ev) => {
    if (ev.target === backdrop) requestModalClose();
  });
  document.addEventListener('keydown', (event) => {
    if (backdrop.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      requestModalClose();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(backdrop.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex="0"]',
    ));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}

function renderToday(view: HTMLElement): void {
  mountToday(view, state, {
    importing,
    importOpen,
    capturing,
    loadError: stateLoadError,
    importResult,
    readStatus: { lastSuccessfulAt: lastStateReadAt, error: stateLoadError },
    health: healthTone(),
    actions: {
      capture: async (text) => {
        if (capturing) return { ok: false };
        capturing = true;
        renderToday(view);
        try {
          const result = await mutation(() => api<{ ok: boolean; message: string }>('/api/capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
          }));
          toast(result.message, result.ok ? 'ok' : 'err');
          return { ok: result.ok };
        } catch (err) {
          toast(String(err), 'err');
          return { ok: false };
        } finally {
          capturing = false;
          renderToday(view);
        }
      },
      importFile: async (file) => {
        if (importing) return;
        if (!file.name.toLowerCase().endsWith('.md') && !file.name.toLowerCase().endsWith('.txt')) {
          toast('仅支持 .md / .txt 逐字稿文件', 'err');
          return;
        }
        importing = true;
        importResult = { fileName: file.name, bytes: file.size, status: 'processing', message: '正在处理…' };
        renderToday(view);
        const form = new FormData();
        form.append('file', file);
        try {
          const result = await mutation(() => api<{
            ok: boolean;
            message: string;
            details?: string[];
            estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
          }>('/api/meetings/import', {
            method: 'POST', body: form,
          }));
          importResult = {
            fileName: file.name,
            bytes: file.size,
            status: result.ok ? 'success' : 'error',
            message: result.message,
            details: result.details,
            estimate: result.estimate,
          };
          toast(result.message, result.ok ? 'ok' : 'err');
        } catch (err) {
          importResult = { fileName: file.name, bytes: file.size, status: 'error', message: String(err) };
          toast(String(err), 'err');
        } finally {
          importing = false;
          renderToday(view);
          void refreshState();
        }
      },
      toggleImport: (open) => { importOpen = open; },
      refresh: () => { void refreshState(); },
    },
  });
}

// ---------- 第二大脑：会话存储（localStorage，上限 10） ----------

function loadAskStore(): void {
  try {
    const raw = window.localStorage.getItem(askStorageKey());
    if (!raw) return;
    const parsed = JSON.parse(raw) as { threads?: AskThread[]; activeId?: string | null };
    if (Array.isArray(parsed.threads)) askThreads = parsed.threads.slice(0, ASK_MAX_THREADS);
    if (typeof parsed.activeId === 'string') askActiveId = parsed.activeId;
    if (!askThreads.some((t) => t.id === askActiveId)) askActiveId = askThreads[0]?.id ?? null;
  } catch {
    /* localStorage 数据损坏时按空会话处理，不阻断使用 */
  }
}

function saveAskStore(): void {
  try {
    window.localStorage.setItem(
      askStorageKey(),
      JSON.stringify({ threads: askThreads, activeId: askActiveId }),
    );
  } catch {
    /* 配额满/隐私模式等：静默失败，仅本次不持久化 */
  }
}

function activeAskThread(): AskThread | null {
  return askThreads.find((t) => t.id === askActiveId) ?? null;
}

function makeThreadTitle(q: string): string {
  const one = q.replace(/\s+/g, ' ').trim();
  if (!one) return '新会话';
  return one.length > 12 ? one.slice(0, 12) + '…' : one;
}

function newAskThread(): AskThread | null {
  if (askThreads.length >= ASK_MAX_THREADS) {
    toast('已达 ' + ASK_MAX_THREADS + ' 个会话上限，请先删除或清空一个', 'err');
    return null;
  }
  const thread: AskThread = {
    id: 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
    title: '新会话',
    createdAt: new Date().toISOString(),
    messages: [],
  };
  askThreads.push(thread);
  askActiveId = thread.id;
  saveAskStore();
  return thread;
}

function deleteAskThread(threadId: string): void {
  const idx = askThreads.findIndex((t) => t.id === threadId);
  if (idx < 0) return;
  if (!window.confirm('删除会话「' + askThreads[idx].title + '」？其中的问答记录会一并删除。')) return;
  askThreads.splice(idx, 1);
  if (askActiveId === threadId) {
    askActiveId = askThreads[0]?.id ?? null;
    askDraft = '';
  }
  saveAskStore();
  renderAsk(document.getElementById('view-ask') as HTMLElement);
}

function askHistoryOf(thread: AskThread): AskHistoryTurn[] {
  const turns: AskHistoryTurn[] = [];
  for (let i = 0; i + 1 < thread.messages.length; i += 2) {
    const userMsg = thread.messages[i];
    const aiMsg = thread.messages[i + 1];
    if (userMsg.role === 'user' && aiMsg?.role === 'ai') {
      turns.push({ question: userMsg.text, sources: aiMsg.sources });
    }
  }
  return turns.slice(-ASK_MAX_HISTORY);
}

function askView(): HTMLElement {
  return document.getElementById('view-ask') as HTMLElement;
}

function renderAsk(view: HTMLElement): void {
  const full = askThreads.length >= ASK_MAX_THREADS;
  view.innerHTML =
    '<div class="ask-layout">' +
    '<aside class="ask-side">' +
    '<div class="ask-side-head">' +
    '<button class="primary ask-new-btn" data-action="ask-new"' + (full ? ' disabled title="已达 10 个会话上限，请先删除或清空一个"' : '') + '>＋ 新会话</button>' +
    '<span class="ask-side-count">' + askThreads.length + '/' + ASK_MAX_THREADS + '</span>' +
    '</div>' +
    '<div class="ask-side-list" id="ask-side-list"></div>' +
    '</aside>' +
    '<div class="ask-main" id="ask-main"></div>' +
    '</div>';
  renderAskSide();
  renderAskChat();
}

function renderAskSide(): void {
  const listEl = document.getElementById('ask-side-list');
  if (!listEl) return;
  if (askThreads.length === 0) {
    listEl.innerHTML = '<p class="hint">还没有会话。点「＋ 新会话」开始提问。</p>';
    return;
  }
  listEl.innerHTML = askThreads.map((t) => {
    const active = t.id === askActiveId;
    return '<div class="ask-item' + (active ? ' active' : '') + '" data-thread="' + t.id + '">' +
      '<button class="ask-item-main" data-action="ask-open" data-thread="' + t.id + '" title="' + esc(t.title) + '">' + esc(t.title) + '</button>' +
      '<button class="ask-item-op" data-action="ask-rename" data-thread="' + t.id + '" title="重命名会话">✎</button>' +
      '<button class="ask-item-op danger" data-action="ask-del" data-thread="' + t.id + '" title="删除会话">✕</button>' +
      '</div>';
  }).join('');
}

function renderAskChat(): void {
  const main = document.getElementById('ask-main');
  if (!main) return;
  const existing = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (existing && askActiveId) {
    askDraft = existing.value;
    persistEntityDraft(askDraftEntity(askActiveId), askDraft);
  }
  const scopeEl = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeEl) askScope = scopeEl.value;
  const full = askThreads.length >= ASK_MAX_THREADS;
  const thread = activeAskThread();
  if (!thread) {
    main.innerHTML =
      '<div class="ask-welcome"><h3>问第二大脑</h3>' +
      '<p>基于工作 vault 召回<strong>带来源</strong>的事实回答：做过什么、为什么这样决定、接下来最该做什么。</p>' +
      '<p class="hint">例如：「网课项目最近的决策是什么？」 · 追问如：「那后来呢？」</p>' +
      '<button class="primary" data-action="ask-new"' + (full ? ' disabled title="已达 10 个会话上限"' : '') + '>＋ 开始新对话</button>' +
      '</div>';
    return;
  }
  askDraft = loadEntityDraft<string>(askDraftEntity(thread.id), Date.now(), remoteVersion?.workspace_id) ?? '';
  const bubbles = thread.messages.map((m) =>
    m.role === 'user'
      ? '<div class="chat-msg user"><div class="bubble">' + esc(m.text).replace(/\n/g, '<br>') + '</div></div>'
      : '<div class="chat-msg ai"><div class="bubble">' + m.text + '</div></div>'
  ).join('');
  const showTyping = askBusy && thread.id === askBusyThreadId;
  const typing = showTyping ? '<div class="chat-msg ai"><div class="bubble typing">思考中…</div></div>' : '';
  const errorBubble = askErrors[thread.id]
    ? '<div class="chat-msg ai"><div class="bubble"><p class="err-text">' + esc(askErrors[thread.id]) + '</p><p class="hint">问题未加入下一轮上下文，可以直接重试。</p></div></div>'
    : '';
  const scopeOptions = (state?.projects ?? [])
    .filter((p) => p.registered)
    .map((p) =>
      '<option value="' + esc(p.name) + '"' + (askScope === p.name ? ' selected' : '') + '>' +
      esc(projectDisplayName(p)) + (p.is_thread ? '（线程）' : '') +
      (projectDisplayName(p) !== p.name ? ' · ' + esc(p.name) : '') + '</option>'
    )
    .join('');
  main.innerHTML =
    '<div class="ask-chat" id="ask-chat">' + bubbles + errorBubble + typing + '</div>' +
    '<div class="ask-inputbar">' +
    '<form class="ask" id="ask-form" autocomplete="off">' +
    '<div class="ask-scope-row"><label class="hint">检索范围</label>' +
    '<select id="ask-scope"><option value="">全部（整个第二大脑）</option>' + scopeOptions + '</select></div>' +
    '<textarea id="ask-input" rows="2" placeholder="问第二大脑…（Enter 提问，Shift+Enter 换行）"></textarea>' +
    '<div class="form-row"><span class="hint ask-keyhint">Enter 提问 · Shift+Enter 换行</span>' +
    '<button class="primary" type="submit"' + (askBusy ? ' disabled' : '') + '>提问</button></div>' +
    '</form></div>';
  bindAskInput();
  const inputEl = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (inputEl) inputEl.value = askDraft;
  const scopeSet = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeSet) scopeSet.value = askScope;
  const chat = document.getElementById('ask-chat');
  if (chat?.lastElementChild) chat.lastElementChild.scrollIntoView({ block: 'nearest' });
}

function bindAskInput(): void {
  const form = document.getElementById('ask-form') as HTMLFormElement | null;
  if (form) form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void askSubmit();
  });
  const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (!input) return;
  input.addEventListener('input', () => {
    askDraft = input.value;
    if (askActiveId) persistEntityDraft(askDraftEntity(askActiveId), askDraft);
  });
  // Enter 提问（中文输入法组词时的回车不触发）；Shift+Enter 换行。
  input.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || ev.shiftKey) return;
    if (ev.isComposing || ev.keyCode === 229) return;
    ev.preventDefault();
    void askSubmit();
  });
}

async function askSubmit(): Promise<void> {
  const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (!input || askBusy) return;
  const q = input.value.trim();
  if (!q) return;
  let thread = activeAskThread();
  if (!thread) {
    thread = newAskThread();
    if (!thread) return;
  }
  if (thread.messages.length === 0) thread.title = makeThreadTitle(q);
  const history = askHistoryOf(thread);
  const scopeInput = document.getElementById('ask-scope') as HTMLSelectElement | null;
  if (scopeInput) askScope = scopeInput.value;
  const pendingMessage: AskMsg = { role: 'user', text: q, ts: new Date().toISOString(), sources: [] };
  thread.messages.push(pendingMessage);
  input.value = '';
  askDraft = '';
  clearEntityDraft(askDraftEntity(thread.id), remoteVersion?.workspace_id);
  delete askErrors[thread.id];
  askBusy = true;
  askBusyThreadId = thread.id;
  saveAskStore();
  renderAskSide();
  renderAskChat();
  let staleCompletion = false;
  const restoreFailedQuestion = (message: string): void => {
    const pendingIndex = thread.messages.lastIndexOf(pendingMessage);
    if (pendingIndex >= 0) thread.messages.splice(pendingIndex, 1);
    askDraft = q;
    persistEntityDraft(askDraftEntity(thread.id), askDraft);
    askErrors[thread.id] = message;
  };
  try {
    const r = await mutation(() => api<AskResponse>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history, project: askScope || null }),
    }));
    if (!r.ok || !r.answer_html) {
      restoreFailedQuestion(r.message ?? '提问失败');
      return;
    }
    const html = r.answer_html;
    thread.messages.push({
      role: 'ai',
      text: html,
      ts: new Date().toISOString(),
      sources: r.source_ids ?? [],
    });
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) {
      staleCompletion = true;
    } else {
      restoreFailedQuestion(String(err));
    }
  } finally {
    askBusy = false;
    askBusyThreadId = null;
    if (!staleCompletion) {
      saveAskStore();
      renderAskSide();
      renderAskChat();
    }
  }
}

function beginAskRename(threadId: string): void {
  const item = document.querySelector<HTMLElement>('.ask-item[data-thread="' + threadId + '"]');
  const thread = askThreads.find((t) => t.id === threadId);
  if (!item || !thread) return;
  const input = document.createElement('input');
  input.className = 'ask-rename-input';
  input.value = thread.title;
  input.maxLength = 40;
  item.innerHTML = '';
  item.appendChild(input);
  input.focus();
  input.select();
  const commit = (): void => {
    const value = input.value.trim();
    if (value) thread.title = value;
    saveAskStore();
    renderAskSide();
  };
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      commit();
    } else if (ev.key === 'Escape') {
      renderAskSide();
    }
  });
  input.addEventListener('blur', commit);
}


function renderReview(view: HTMLElement): void {
  if (!review) {
    view.innerHTML = reviewLoadError
      ? '<div class="empty load-error"><p>审批数据读取失败：' + esc(reviewLoadError) + '</p><button class="primary" data-action="retry-review">重试读取</button></div>'
      : '<div class="loading">加载审批页…</div>';
    return;
  }
  const readNotice = reviewLoadError
    ? '<div class="msg err">本次审批读取失败，保留上次成功数据' +
      (lastReviewReadAt ? ' · 最近成功读取于 ' + esc(lastReviewReadAt) : '') + '。可稍后重试。</div>'
    : '';
  view.innerHTML = readNotice + reviewHtml(
    review,
    state?.status.pending_review ?? 0,
    state?.day ?? '',
    state?.projects ?? [],
    externalActions,
    externalActionsError,
  );
  view.querySelectorAll<HTMLFormElement>('.edit-form').forEach((form) => {
    const candidateId = String(new FormData(form).get('candidate_id') ?? '');
    const fields = reviewDrafts[candidateId];
    if (!fields) return;
    for (const [name, value] of Object.entries(fields)) {
      const input = form.elements.namedItem(name);
      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement || input instanceof HTMLSelectElement) {
        input.value = value;
      }
    }
  });
  view.oninput = () => saveCurrentDraftSnapshot();
  view.onchange = () => saveCurrentDraftSnapshot();
}


function renderProjects(view: HTMLElement): void {
  if (!state) {
    view.innerHTML = '<div class="loading">加载中…</div>';
    return;
  }
  const projects = state.projects;
  const today = state.day;
  const query = (view.querySelector<HTMLInputElement>('#project-search'))?.value ?? '';
  const total = projects.length;
  const onHome = projects.filter((p) => p.registered && p.status === 'active').length;
  const fresh = projects.filter((p) => !p.registered).length;
  const archived = projects.filter((p) => p.status === 'archived').length;
  view.innerHTML =
    '<div class="section-head"><h3 class="section-title">全部项目</h3>' +
    '<span class="hint">共 ' + total + ' · 在工作台 ' + onHome + ' · 新 ' + fresh + ' · 已归档 ' + archived + '</span></div>' +
    '<div class="project-toolbar">' +
    '<input id="project-search" type="search" placeholder="搜索项目名…" value="' + esc(query) + '">' +
    '<details class="thread-create" title="业务线程不需要 Work 文件夹/git 仓库，直接在 vault 建档">' +
    '<summary class="ghost">＋ 新建知识线程</summary>' +
    '<form class="thread-create-form">' +
    '<input name="project_id" placeholder="项目 ID，如 finance-ops" required pattern="[A-Za-z0-9_-]+" title="字母/数字/下划线/连字符">' +
    '<input name="aliases" placeholder="别名（逗号分隔，可选）：财务运营, Finance Ops">' +
    '<button class="ok" type="submit">建档</button>' +
    '</form></details>' +
    '</div>' +
    '<div id="projects-list"></div>';
  const listEl = document.getElementById('projects-list') as HTMLElement;
  listEl.innerHTML = projectsListHtml(query, projects, today, true);
  const search = view.querySelector<HTMLInputElement>('#project-search');
  search?.addEventListener('input', () => {
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(search.value, projects, today, true);
  });
}

// ---------- 使用指南（第 5 页签；内容构建时从 WEB_USAGE_GUIDE.md 同步内置） ----------

function guideSummaryHtml(q: string): string {
  // <summary> 只允许短语内容：转义后仅放行行内代码
  const safe = esc(q);
  return safe.replace(/`([^`]+?)`/g, '<code>$1</code>');
}

let guideCache: string | null = null;

function guideBodyHtml(): string {
  if (guideCache) return guideCache;
  const lines = guideMd.split('\n');
  const faqIdx = lines.findIndex((l) => /^#{1,4}\s*.*常见问题/.test(l));
  let html = mdToHtml((faqIdx === -1 ? lines : lines.slice(0, faqIdx)).join('\n'));
  if (faqIdx !== -1) {
    const rest = lines.slice(faqIdx + 1);
    const tailIdx = rest.findIndex((l) => /^#{1,4}\s/.test(l));
    const qaLines = tailIdx === -1 ? rest : rest.slice(0, tailIdx);
    const tail = tailIdx === -1 ? [] : rest.slice(tailIdx);
    const items: { q: string; a: string[] }[] = [];
    let cur: { q: string; a: string[] } | null = null;
    for (const line of qaLines) {
      const qm = line.match(/^\*\*Q[:：]\s*(.+?)\s*\*\*$/);
      if (qm) {
        cur = { q: qm[1].trim(), a: [] };
        items.push(cur);
        continue;
      }
      if (!cur || !line.trim()) continue;
      cur.a.push(line);
    }
    const faqHtml = items
      .map(
        (it) =>
          '<details class="faq-item"><summary>' + guideSummaryHtml(it.q) + '</summary>' +
          (it.a.length ? '<div class="faq-answer">' + mdToHtml(it.a.join('\n')) + '</div>' : '') +
          '</details>'
      )
      .join('');
    html += '<h3>常见问题</h3>' + faqHtml;
    if (tail.length) html += mdToHtml(tail.join('\n'));
  }
  guideCache = html;
  return html;
}

function renderGuide(view: HTMLElement): void {
  view.innerHTML = '<div class="guide">' + guideBodyHtml() + '</div>';
}

interface ProfileSummaryPayload {
  workspace_id: string;
  workspace_short_code: string;
  display_name: string;
  path: string;
  compatibility: string;
  device_role: string;
  active: boolean;
  provider_status: Record<string, string>;
  sync_summary: { state: string; pending_commits: number | null; last_sync_at?: string | null };
  remote_url?: string | null;
}

interface ProfileListPayload {
  profiles: ProfileSummaryPayload[];
  current_device_id?: string | null;
}

interface AutomationJobPayload {
  enabled: boolean;
  hour: number;
  minute: number;
  weekdays: number[];
  last_run_at?: string | null;
  last_status: string;
  last_detail?: string | null;
  next_run_at?: string | null;
}

interface AutomationSettingsPayload {
  workspace_id: string;
  jobs: Record<string, AutomationJobPayload>;
}

interface RemoteNormalizationPreviewPayload {
  plan_id: string;
  old_url: string;
  candidate_url: string;
  branch: string;
  candidate_fetched: boolean;
  candidate_ahead: number;
  candidate_behind: number;
}

interface AcceptancePreflightPayload {
  ok: boolean;
  report: string;
  checks: Array<{ name: string; status: string; detail: string }>;
}

const AUTOMATION_LABELS: Record<string, string> = {
  brief: '晨间简报',
  weekly: '每周复盘',
  'meeting-sync': '会议同步',
};
const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

function automationJobHtml(job: string, schedule: AutomationJobPayload): string {
  const time = String(schedule.hour).padStart(2, '0') + ':' + String(schedule.minute).padStart(2, '0');
  const statusLabels: Record<string, string> = {
    never: '尚未运行', success: '运行成功', degraded: '降级完成', failed: '运行失败',
    'not-primary': '本机不是主设备', skipped: '本次跳过',
  };
  const detail = schedule.last_detail ? '<div class="meta automation-detail">' + esc(schedule.last_detail) + '</div>' : '';
  const copy = schedule.last_detail
    ? '<button class="ghost" type="button" data-action="automation-copy" data-summary="' + esc(schedule.last_detail) + '">复制错误摘要</button>'
    : '';
  return '<form class="card automation-form" data-job="' + esc(job) + '">' +
    '<div class="automation-row"><div><strong>' + esc(AUTOMATION_LABELS[job] ?? job) + '</strong>' +
    '<div class="meta">最近：' + esc(statusLabels[schedule.last_status] ?? schedule.last_status) +
    (schedule.last_run_at ? ' · ' + esc(schedule.last_run_at) : '') + '</div>' + detail + '</div>' +
    '<label class="automation-enabled"><input name="enabled" type="checkbox"' + (schedule.enabled ? ' checked' : '') + '>启用</label></div>' +
    '<div class="automation-controls"><label>时间 <input name="time" type="time" value="' + time + '"></label>' +
    '<span class="meta">星期</span>' + WEEKDAY_LABELS.map((label, index) =>
      '<label class="weekday"><input name="weekday" type="checkbox" value="' + index + '"' +
      (schedule.weekdays.includes(index) ? ' checked' : '') + '>' + label + '</label>').join('') + '</div>' +
    '<div class="row"><button class="primary" type="submit">保存</button>' +
    '<button class="ghost" type="button" data-action="automation-run" data-job="' + esc(job) + '">立即运行</button>' + copy + '</div></form>';
}

function httpsCandidate(url: string | null | undefined): string {
  if (!url) return '';
  if (url.startsWith('https://')) return url;
  const scp = url.match(/^git@github\.com:(.+)$/);
  return scp ? 'https://github.com/' + scp[1] : '';
}

async function previewGitRemoteNormalization(): Promise<void> {
  const candidate = (document.getElementById('remote-candidate-url') as HTMLInputElement | null)?.value.trim() ?? '';
  const username = (document.getElementById('remote-github-username') as HTMLInputElement | null)?.value.trim() ?? '';
  const pat = (document.getElementById('remote-github-pat') as HTMLInputElement | null)?.value ?? '';
  if (!candidate || !username || !pat) {
    toast('请填写 HTTPS 地址、GitHub username 和 workspace-scoped PAT', 'err');
    return;
  }
  try {
    const result = await api<RemoteNormalizationPreviewPayload>('/api/settings/git/remote/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_url: candidate, git_username: username, pat }),
    });
    const output = document.getElementById('remote-normalization-result');
    if (output) {
      output.innerHTML = '<div class="success">预览通过：候选仓库已认证、workspace marker、分支/upstream 和 fetch 均通过。' +
        '<br>当前：' + esc(result.old_url) + '<br>候选：' + esc(result.candidate_url) +
        '<br>branch：' + esc(result.branch) + ' · ahead ' + result.candidate_ahead + ' · behind ' + result.candidate_behind +
        '<div class="row"><button class="primary" type="button" data-action="git-remote-apply" data-plan="' + esc(result.plan_id) + '">确认并转换</button>' +
        '<button class="ghost" type="button" data-action="git-remote-rollback">取消</button></div></div>';
    }
    toast('候选 remote 预览通过；尚未修改本机配置', 'ok');
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function applyGitRemoteNormalization(planId: string): Promise<void> {
  if (!window.confirm('确认将 origin 和本机 profile 转换为 HTTPS？不会提交、推送或修改 vault 内容。')) return;
  const username = (document.getElementById('remote-github-username') as HTMLInputElement | null)?.value.trim() ?? '';
  const patInput = document.getElementById('remote-github-pat') as HTMLInputElement | null;
  const pat = patInput?.value ?? '';
  try {
    const result = await api<{ new_url: string }>('/api/settings/git/remote/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId, git_username: username, pat }),
    });
    if (patInput) patInput.value = '';
    const output = document.getElementById('remote-normalization-result');
    if (output) output.innerHTML = '<div class="success">转换完成：' + esc(result.new_url) +
      '<br>未提交、未推送、未修改 vault。若需撤销，可使用“回滚最近一次转换”。</div>';
    toast('Git remote 已转换为 HTTPS', 'ok');
    void renderSettings(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function rollbackGitRemoteNormalization(): Promise<void> {
  if (!window.confirm('确认回滚最近一次 remote 转换？')) return;
  try {
    const result = await api<{ restored_url: string }>('/api/settings/git/remote/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true }),
    });
    const output = document.getElementById('remote-normalization-result');
    if (output) output.innerHTML = '<div class="success">已恢复：' + esc(result.restored_url) + '</div>';
    toast('remote 转换已回滚', 'ok');
    void renderSettings(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function runAcceptancePreflight(): Promise<void> {
  try {
    const result = await api<AcceptancePreflightPayload>('/api/settings/acceptance-preflight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const output = document.getElementById('acceptance-preflight-result');
    if (output) output.innerHTML = '<pre class="diagnostics-output">' + esc(result.report) + '</pre>';
    toast(result.ok ? '验收预检通过' : '验收预检未通过，请查看报告', result.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function legacyRenderSettings(view: HTMLElement): Promise<void> {
  view.innerHTML = '<div class="loading">正在读取工作台设置…</div>';
  try {
    const [response, automation] = await Promise.all([
      api<ProfileListPayload>('/api/settings/profiles'),
      api<AutomationSettingsPayload>('/api/settings/automation'),
    ]);
    const activeProfile = response.profiles.find((profile) => profile.active);
    const candidateUrl = httpsCandidate(activeProfile?.remote_url);
    view.innerHTML = '<section class="block"><div class="section-head"><h2 class="section-title">工作台设置</h2>' +
      '<button class="ghost" data-action="settings-doctor">离线检查</button>' +
      '<button class="ghost" data-action="settings-doctor-online">在线检查（会访问网络）</button></div>' +
      '<p class="hint">一次只打开一个工作台。切换会先完成安全检查，再由本机服务重启到目标工作台。</p>' +
      response.profiles.map((profile) =>
        '<article class="card entry ' + (profile.active ? 'ok' : '') + '"><div class="entry-top"><strong>' + esc(profile.display_name) +
        '</strong><span class="badge">' + esc(profile.active ? '当前' : profile.workspace_short_code) + '</span></div>' +
        '<p class="meta">兼容性：' + esc(profile.compatibility) + ' · 设备：' + esc(profile.device_role) + '</p>' +
        '<p class="meta">路径：' + esc(profile.path) + '</p><p class="meta">同步：' +
        esc(profile.sync_summary.state + ' · 待推送 ' + String(profile.sync_summary.pending_commits ?? '—')) +
        '</p><p class="meta">Provider：' +
        esc(Object.entries(profile.provider_status).map(([key, value]) => key + ' ' + value).join(' · ')) + '</p>' +
        (profile.active && profile.compatibility === 'read-only-upgrade-required' && response.current_device_id
          ? '<button class="primary" data-action="workspace-migrate" data-device="' + esc(response.current_device_id) + '">升级工作区 schema</button>'
          : '') +
        (profile.active ? '' : '<button class="primary" data-action="profile-switch" data-workspace="' + esc(profile.workspace_id) + '">切换到此工作台</button><button class="ghost" data-action="profile-remove" data-workspace="' + esc(profile.workspace_id) + '">移除此 Mac 上的工作台</button>') +
        '</article>',
      ).join('') + '</section>' +
      '<section class="block"><h3 class="section-title">生产 Git remote 规范化</h3>' +
      '<p class="hint">生产模式只接受 HTTPS。这里会先在临时 clone 中验证认证、仓库身份、workspace marker、分支/upstream 和 fetch；确认后才更新 origin、profile 和 workspace-scoped Keychain。不会记录 PAT，不会提交、推送或改动 vault。</p>' +
      '<form id="remote-normalization-form" autocomplete="off"><div class="grid2">' +
      '<label>候选 HTTPS remote<input id="remote-candidate-url" type="url" value="' + esc(candidateUrl) + '" placeholder="https://github.com/owner/repo.git"></label>' +
      '<label>GitHub username<input id="remote-github-username" autocomplete="username" placeholder="你的 GitHub 用户名"></label>' +
      '<label>workspace-scoped PAT<input id="remote-github-pat" type="password" autocomplete="new-password" placeholder="只在本次验证/转换中使用"></label></div>' +
      '<div class="row"><button class="primary" type="button" data-action="git-remote-preview">预览 HTTPS 转换</button>' +
      '<button class="ghost" type="button" data-action="git-remote-rollback">回滚最近一次转换</button></div></form>' +
      '<div id="remote-normalization-result"></div></section>' +
      '<section class="block"><h3 class="section-title">只读 acceptance preflight</h3>' +
      '<p class="hint">统一检查 App/build、production backend、HTTPS remote、凭据、双后端 dirty 一致性、fetch、ahead/behind、schema 路径、备份和 automation role。报告已脱敏，可复制给支持人员。</p>' +
      '<button class="ghost" type="button" data-action="acceptance-preflight">运行只读预检</button><div id="acceptance-preflight-result"></div></section>' +
      '<section class="block"><h3 class="section-title">App 内自动化</h3><p class="hint">只在这台 Mac 本地运行。只有 workspace 的 automation-primary 会执行写入；辅助设备会安全跳过。</p>' +
      Object.entries(automation.jobs).map(([job, schedule]) => automationJobHtml(job, schedule)).join('') + '</section>' +
      '<section class="block"><h3 class="section-title">更新</h3><label class="automation-enabled"><input id="auto-update-check" type="checkbox"' +
      (localStorage.getItem('wb.update.auto-check') !== 'false' ? ' checked' : '') +
      '>每天自动检查更新（只提示，不会自动安装）</label><p class="hint">更新前会检查 workspace schema；公开更新仓库只提供完整性，不提供保密性。</p></section>' +
      '<section class="block"><h3 class="section-title">Provider 设置</h3><p class="hint">非秘密配置写入当前 workspace profile；秘密只在提交时进入该 workspace 的 Keychain，不会回显。</p>' +
      '<form id="provider-settings-form" autocomplete="off"><div class="grid2">' +
      '<label>类型<select id="provider-kind"><option value="model">模型</option><option value="feishu">飞书</option><option value="git">Git</option></select></label>' +
      '<label>能力/账号<input id="provider-capability" placeholder="qa 或 shared"></label>' +
      '<label>模型 ID / App ID / 用户名<input id="provider-primary" placeholder="按类型填写"></label>' +
      '<label>服务地址 / Redirect URI / Host<input id="provider-secondary" placeholder="按类型填写"></label>' +
      '<label>秘密（可选）<input id="provider-secret" type="password" autocomplete="new-password"></label></div>' +
      '<button class="primary" type="submit">保存 Provider 设置</button></form></section>' +
      '<section class="block"><h3 class="section-title">诊断与支持</h3>' +
      '<p class="hint">诊断包只包含版本、架构、状态摘要、同步计数和脱敏错误，不包含会议正文、提示词、模型响应或凭据。</p>' +
      '<div class="row"><button class="ghost" data-action="diagnostics-preview">查看诊断包清单</button>' +
      '<button class="ghost" data-action="diagnostics-export">导出诊断包</button>' +
      '<button class="ghost" data-action="diagnostics-open-log">打开日志目录</button></div>' +
      '<div id="diagnostics-preview"></div></section>';
    const form = document.getElementById('provider-settings-form') as HTMLFormElement | null;
    form?.addEventListener('submit', (event) => {
      event.preventDefault();
      const kind = (document.getElementById('provider-kind') as HTMLSelectElement).value;
      const capability = (document.getElementById('provider-capability') as HTMLInputElement).value.trim();
      const primary = (document.getElementById('provider-primary') as HTMLInputElement).value.trim();
      const secondary = (document.getElementById('provider-secondary') as HTMLInputElement).value.trim();
      const secret = (document.getElementById('provider-secret') as HTMLInputElement).value;
      const settings: Record<string, unknown> = kind === 'model'
        ? { capability, model_id: primary, base_url: secondary }
        : kind === 'feishu'
          ? { app_id: primary, redirect_uri: secondary }
          : { git_username: primary, host: secondary };
      void api<{ secret_saved: boolean }>('/api/settings/provider', {
        method: 'POST', body: JSON.stringify({ provider: kind, settings, secret: secret || null }),
      }).then(() => { (document.getElementById('provider-secret') as HTMLInputElement).value = ''; toast('Provider 设置已保存', 'ok'); })
        .catch((err: unknown) => toast(String(err), 'err'));
    });
    view.querySelectorAll<HTMLFormElement>('.automation-form').forEach((automationForm) => {
      automationForm.addEventListener('submit', (event) => {
        event.preventDefault();
        void saveAutomationForm(automationForm);
      });
    });
    document.getElementById('auto-update-check')?.addEventListener('change', (event) => {
      const enabled = (event.target as HTMLInputElement).checked;
      localStorage.setItem('wb.update.auto-check', enabled ? 'true' : 'false');
      sendNativeMessage({ type: 'updateAutoCheckChanged', enabled });
      toast(enabled ? '已开启每天自动检查更新' : '已关闭自动检查更新', 'ok');
    });
  } catch (err) {
    view.innerHTML = '<div class="error">设置暂时无法读取：' + esc(String(err)) + '</div>';
  }
}

async function renderSettings(view: HTMLElement): Promise<void> {
  await renderSettingsFeature(view, {
    api,
    mutation,
    toast,
    refresh: () => { void renderSettings(view); },
  });
}

async function saveAutomationForm(form: HTMLFormElement): Promise<void> {
  const time = (form.elements.namedItem('time') as HTMLInputElement).value || '08:00';
  const [hour, minute] = time.split(':').map(Number);
  const weekdays = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked'))
    .map((input) => Number(input.value));
  try {
    await api('/api/settings/automation', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job: form.dataset.job,
        enabled: (form.elements.namedItem('enabled') as HTMLInputElement).checked,
        hour, minute, weekdays,
      }),
    });
    const anyEnabled = Boolean(document.querySelector('.automation-form input[name="enabled"]:checked'));
    sendNativeMessage({ type: 'automationSettingsChanged', enabled: anyEnabled });
    toast('自动化设置已保存', 'ok');
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function runAutomationJob(job: string): Promise<void> {
  try {
    const result = await mutation(() => api<{ ok: boolean; status: string; detail?: string | null }>(
      '/api/settings/automation/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job }),
      },
    ));
    toast(result.detail ? result.status + '：' + result.detail : '自动化任务已完成：' + result.status, result.ok ? 'ok' : 'err');
    const view = document.getElementById('view-settings');
    if (view) void renderSettings(view);
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function copyAutomationSummary(summary: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(summary);
    toast('错误摘要已复制', 'ok');
  } catch {
    toast('复制失败，请手动记录摘要：' + summary, 'err');
  }
}

async function switchProfile(workspaceId: string): Promise<void> {
  const prepared = await api<{ plan_id: string }>('/api/settings/profile/prepare', {
    method: 'POST', body: JSON.stringify({ workspace_id: workspaceId }),
  });
  const committed = await api<{ restart_required: boolean }>('/api/settings/profile/commit', {
    method: 'POST', body: JSON.stringify({ plan_id: prepared.plan_id }),
  });
  clearDraftSnapshot(remoteVersion?.workspace_id);
  workspaceStore.dispose();
  apiClient.dispose();
  if (committed.restart_required && sendNativeMessage({ type: 'quit' })) return;
  window.location.reload();
}

async function migrateWorkspace(deviceId: string): Promise<void> {
  if (!window.confirm('迁移前必须确认同步状态 ready、工作树干净且远端可达。确定由当前 Mac 执行？')) return;
  try {
    const result = await mutation(() => api<{ status: string; restart_required?: boolean }>('/api/workspace/migration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed_device_id: deviceId }),
    }));
    toast(result.status === 'already-current' ? '工作区已经是最新 schema' : '工作区迁移完成，即将重新打开', 'ok');
    if (result.status !== 'already-current' && sendNativeMessage({ type: 'quit' })) return;
    window.location.reload();
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function runSettingsDoctor(online = false): Promise<void> {
  const result = await api<{ ok: boolean; checks: { name: string; status: string; detail: string }[] }>(
    '/api/settings/doctor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ online }),
    },
  );
  const failed = result.checks.filter((check) => check.status === 'fail').length;
  const label = online ? '在线检查' : '离线检查';
  toast(failed ? label + '发现 ' + failed + ' 项问题' : label + '完成', failed ? 'err' : 'ok');
}


async function reconcileExternalAction(operationId: string, decision: string, remoteId?: string): Promise<void> {
  try {
    const r = await mutation(() => api<{ ok: boolean; message?: string }>(
      '/api/external-actions/' + encodeURIComponent(operationId) + '/reconcile',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, remote_id: remoteId, confirm_retry: decision === 'retry' }),
      },
    ));
    toast(r.ok ? '外部写回状态已更新' : (r.message ?? '核对失败'), r.ok ? 'ok' : 'err');
    if (r.ok) await refreshExternalActions();
  } catch (err) {
    toast(String(err), 'err');
  }
}

// ---------- 全局事件（审批页操作） ----------

document.addEventListener('click', (ev) => {
  const btn = (ev.target as HTMLElement).closest<HTMLElement>('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action ?? '';
  if (action === 'go-review') {
    tab = 'review';
    render();
    return;
  }
  if (action === 'retry-update') {
    if (!remoteVersion || remoteVersion.frontend_build === CLIENT_BUILD) return;
    try {
      window.sessionStorage.removeItem('wb.update.last-target');
      window.sessionStorage.removeItem('wb.update.last-attempt-at');
    } catch {
      // 存储不可用时仍允许再次尝试导航。
    }
    saveCurrentDraftSnapshot();
    reloadToBuild(remoteVersion.frontend_build);
    return;
  }
  if (action === 'copy-diagnostics') {
    void copyDiagnostics();
    return;
  }
  if (action === 'diagnostics-preview') {
    void previewDiagnostics();
    return;
  }
  if (action === 'diagnostics-export') {
    void exportDiagnostics();
    return;
  }
  if (action === 'diagnostics-open-log') {
    if (sendNativeMessage({ type: 'openLogDirectory' })) {
      toast('已打开日志目录', 'ok');
    } else {
      toast('日志目录位于 ~/Library/Logs', 'info');
    }
    return;
  }
  if (action === 'sync-retry') {
    void retrySync();
    return;
  }
  if (action === 'sync-conflict-details') {
    void showSyncConflictDetails();
    return;
  }
  if (action === 'sync-conflict-preview') {
    void previewSyncConflictRecovery();
    return;
  }
  if (action === 'sync-conflict-apply') {
    void applySyncConflictRecovery();
    return;
  }
  if (action === 'sync-conflict-export') {
    void exportSyncConflictPackage();
    return;
  }
  if (action === 'sync-export') {
    void exportSyncSnapshot();
    return;
  }
  if (action === 'goto-projects') {
    tab = 'projects';
    render();
    return;
  }
  if (action === 'profile-switch') {
    const workspaceId = btn.dataset.workspace ?? '';
    if (workspaceId) void switchProfile(workspaceId).catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (action === 'workspace-migrate') {
    const deviceId = btn.dataset.device ?? '';
    if (deviceId) void migrateWorkspace(deviceId);
    return;
  }
  if (action === 'git-remote-preview') {
    void previewGitRemoteNormalization();
    return;
  }
  if (action === 'git-remote-apply') {
    const planId = btn.dataset.plan ?? '';
    if (planId) void applyGitRemoteNormalization(planId);
    return;
  }
  if (action === 'git-remote-rollback') {
    void rollbackGitRemoteNormalization();
    return;
  }
  if (action === 'acceptance-preflight') {
    void runAcceptancePreflight();
    return;
  }
  if (action === 'profile-remove') {
    const workspaceId = btn.dataset.workspace ?? '';
    if (!workspaceId || !window.confirm('只移除本机 profile/runtime，不删除 vault、远端或 Keychain。确定继续？')) return;
    void api('/api/settings/profile/remove', {
      method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, confirmed: true }),
    }).then(() => { toast('本机 profile 已移除', 'ok'); void renderSettings(document.getElementById('view-settings') as HTMLElement); })
      .catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (action === 'automation-run') {
    const job = btn.dataset.job ?? '';
    if (job) void runAutomationJob(job);
    return;
  }
  if (action === 'automation-copy') {
    void copyAutomationSummary(btn.dataset.summary ?? '');
    return;
  }
  if (action === 'settings-doctor') {
    void runSettingsDoctor().catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (action === 'settings-doctor-online') {
    if (!window.confirm('在线检查会访问 provider，并可能轮换飞书 token。确定继续？')) return;
    void runSettingsDoctor(true).catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (action === 'reopen-onboarding') {
    window.location.href = '/onboarding';
    return;
  }
  if (action === 'feishu-reauth') {
    void api<{ authorize_url: string }>('/api/settings/feishu/authorize-url', { method: 'POST' })
      .then((result) => { window.location.href = result.authorize_url; })
      .catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (action === 'project-activate') {
    void setProjectState('activate', btn.dataset.name ?? '');
    return;
  }
  if (action === 'project-archive') {
    const name = btn.dataset.name ?? '';
    if (btn.dataset.confirm && !window.confirm('归档后将从首页移除（文件夹与笔记不动），可在「项目」页随时恢复。确定归档「' + name + '」？')) {
      return;
    }
    void setProjectState('archive', name);
    return;
  }
  if (action === 'open-log') {
    openLogModal(btn.dataset.project ?? '');
    return;
  }
  if (action === 'open-artifact') {
    openArtifactModal(btn.dataset.project ?? '');
    return;
  }
  if (action === 'open-view') {
    void showProjectView(btn.dataset.name ?? '');
    return;
  }
  if (action === 'run-brief') {
    void runBrief();
    return;
  }
  if (action === 'task-complete') {
    void completeTask(btn);
    return;
  }
  if (action === 'task-edit') {
    openRowEditModal('task', {
      id: btn.dataset.task ?? '',
      title: btn.dataset.title ?? '',
      due: btn.dataset.due ?? '',
    });
    return;
  }
  if (action === 'meeting-edit') {
    openRowEditModal('meeting', {
      id: btn.dataset.event ?? '',
      title: btn.dataset.title ?? '',
      start: tsToDatetimeLocal(btn.dataset.start),
      end: tsToDatetimeLocal(btn.dataset.end) || plusMinutesInput(btn.dataset.start, 60),
    });
    return;
  }
  if (action === 'close-modal') {
    requestModalClose();
    return;
  }
  if (action === 'plan') {
    void planApply(false);
    return;
  }
  if (action === 'apply') {
    void planApply(true);
    return;
  }
  if (action === 'retry-state') {
    void refreshState();
    return;
  }
  if (action === 'retry-review') {
    void refreshReview();
    return;
  }
  if (action === 'external-recheck') {
    void reconcileExternalAction(btn.dataset.operation ?? '', 'recheck');
    return;
  }
  if (action === 'external-confirm-created') {
    const remoteId = window.prompt('请输入飞书侧已创建对象的 ID：');
    if (remoteId?.trim()) void reconcileExternalAction(btn.dataset.operation ?? '', 'succeeded', remoteId.trim());
    return;
  }
  if (action === 'external-confirm-not-found') {
    if (window.confirm('确认飞书侧没有创建该对象？确认后仍需再次点击“确认后重试”才能重新创建。')) {
      void reconcileExternalAction(btn.dataset.operation ?? '', 'not-found');
    }
    return;
  }
  if (action === 'external-retry') {
    if (window.confirm('再次确认飞书侧未创建，并允许重新创建？')) {
      void reconcileExternalAction(btn.dataset.operation ?? '', 'retry');
    }
    return;
  }
  if (action === 'decide') {
    const card = btn.closest<HTMLElement>('.entry');
    if (!card) return;
    void decide(card.dataset.id ?? '', btn.dataset.decision ?? 'pending');
    return;
  }
  if (action === 'group-decide') {
    const gi = Number(btn.dataset.group ?? '-1');
    const group = review?.groups[gi];
    if (!group) return;
    const decision = btn.dataset.decision ?? 'pending';
    const pendingEntries = group.entries.filter((e) => e.decision === 'pending');
    const entries = decision === 'approved'
      ? pendingEntries.filter((e) => e.actionable && !!e.route)
      : pendingEntries;
    const blocked = decision === 'approved' ? pendingEntries.length - entries.length : 0;
    const note = blocked > 0 ? blocked + ' 条因依据或落点不完整未纳入批准' : '';
    const ids = entries
      .map((e) => e.candidate_id);
    void batchDecide(ids, decision, note);
    return;
  }
  if (action === 'reject-expired') {
    const today = state?.day ?? '';
    const ids = (review?.groups ?? [])
      .flatMap((g) => g.entries)
      .filter((e) => e.decision === 'pending' && !!e.due_date && !!today && e.due_date < today)
      .map((e) => e.candidate_id);
    void batchDecide(ids, 'rejected');
    return;
  }
  if (action === 'ask-new') {
    askDraft = '';
    const thread = newAskThread();
    renderAsk(askView());
    const input = document.getElementById('ask-input') as HTMLTextAreaElement | null;
    if (thread && input) input.focus();
    return;
  }
  if (action === 'ask-open') {
    askDraft = '';
    askActiveId = btn.dataset.thread ?? null;
    saveAskStore();
    renderAsk(askView());
    return;
  }
  if (action === 'ask-del') {
    deleteAskThread(btn.dataset.thread ?? '');
    return;
  }
  if (action === 'ask-rename') {
    beginAskRename(btn.dataset.thread ?? '');
    return;
  }
  if (action === 'toggle-edit') {
    const box = btn.closest<HTMLElement>('.entry')?.querySelector<HTMLElement>('.edit-box');
    if (box) box.hidden = !box.hidden;
  }
});

document.addEventListener('submit', (ev) => {
  const form = ev.target as HTMLFormElement;
  if (form.classList.contains('thread-create-form')) {
    ev.preventDefault();
    const data = new FormData(form);
    const projectId = String(data.get('project_id') ?? '').trim();
    if (!projectId) {
      toast('请输入项目 ID', 'err');
      return;
    }
    const aliases = String(data.get('aliases') ?? '')
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    void mutation(async () => {
      const r = await api<{ ok: boolean; message: string }>('/api/projects/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, aliases }),
      });
      toast(r.message, r.ok ? 'ok' : 'err');
      if (r.ok) form.reset();
      void refreshAll();
    }).catch((err: unknown) => toast(String(err), 'err'));
    return;
  }
  if (!form.classList.contains('edit-form')) return;
  ev.preventDefault();
  const data = new FormData(form);
  const body: Record<string, string> = {};
  data.forEach((v, k) => { body[k] = String(v); });
  const saveAndApprove = (ev.submitter as HTMLElement | null)?.dataset?.action === 'save-approve';
  void mutation(async () => {
    const r = await api<{ ok: boolean; message: string }>('/api/review/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      toast(r.message, 'err');
      return;
    }
    if (!saveAndApprove) {
      toast(r.message, 'ok');
      void refreshReview();
      return;
    }
    // 保存并批准：落点未定与后端 apply 的「缺少 route」守卫一致，禁止直接批准。
    if (!body.route) {
      toast('已保存。落点未定无法批准——请选好落点后再批准', 'info');
      void refreshReview();
      return;
    }
    try {
      const d = await api<{ ok: boolean; message: string }>('/api/review/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: String(body.candidate_id ?? ''), decision: 'approved' }),
      });
      if (d.ok) {
        toast('✓ 已保存并批准 —— 仅标记，点「应用（写回）」才真正写回/建任务', 'ok');
      } else {
        toast(d.message, 'err');
      }
    } catch (err) {
      toast(String(err), 'err');
    }
    void refreshReview();
    void refreshState();
  }).catch((err: unknown) => toast(String(err), 'err'));
});

async function decide(candidateId: string, decision: string): Promise<void> {
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/review/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    }));
    if (r.ok) {
      const verb = decision === 'approved' ? '已批准' : decision === 'rejected' ? '已拒绝' : '已改回待确认';
      const tip = decision === 'approved' ? '—— 仅标记，点「应用（写回）」才真正写回/建任务' : '';
      toast('✓ ' + verb + tip, 'ok');
    } else {
      toast(r.message, 'err');
    }
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshReview();
  void refreshState();
}

async function batchDecide(candidateIds: string[], decision: string, note = ''): Promise<void> {
  if (candidateIds.length === 0) {
    toast('没有可操作的条目', 'info');
    return;
  }
  const REVIEW_BATCH_LIMIT = 100;
  if (candidateIds.length > REVIEW_BATCH_LIMIT) {
    toast('本次批量操作包含 ' + candidateIds.length + ' 条，超过单批上限 100 条，未执行；请缩小范围后重试', 'err');
    return;
  }
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string; updated?: number }>('/api/review/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds, decision }),
    }));
    if (r.ok) {
      const verb = decision === 'approved' ? '批准' : decision === 'rejected' ? '拒绝' : '改回待确认';
      const tip = decision === 'approved' ? '—— 仅标记，点「应用（写回）」才真正写回/建任务' : '';
      toast('✓ 已批量' + verb + ' ' + (r.updated ?? '') + ' 条' + (note ? ' · ' + note : '') + tip, 'ok');
    } else {
      toast(r.message, 'err');
    }
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshReview();
  void refreshState();
}

async function setProjectState(action: 'activate' | 'archive', name: string): Promise<void> {
  if (!name) return;
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/projects/' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }));
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshAll();
}

/** 追加推进日志弹窗：多选关联线程/项目 + 粘贴文本 → AI 消化入各线程。 */
interface LogDraft {
  projects: string[];
  text: string;
}

function openLogModal(defaultProject: string): void {
  const registered = (state?.projects ?? []).filter((p) => p.registered);
  const saved = loadEntityDraft<LogDraft>('log:' + defaultProject, Date.now(), remoteVersion?.workspace_id);
  const selectedProjects = saved?.projects ?? (defaultProject ? [defaultProject] : []);
  const boxes = registered
    .map((p) =>
      '<label class="log-proj"><input type="checkbox" name="log-proj" value="' + esc(p.name) + '"' +
      (selectedProjects.includes(p.name) ? ' checked' : '') + '>' + esc(projectDisplayName(p)) +
      (projectDisplayName(p) !== p.name ? ' <span class="hint">' + esc(p.name) + '</span>' : '') +
      (p.is_thread ? ' <span class="hint">(线程)</span>' : '') + '</label>'
    )
    .join('');
  openModal(
    '<h3>追加推进日志</h3>' +
    '<p class="hint">粘贴一段推进/沟通摘录/跟进（文本即可，语音请先自行转写）。可勾选多个关联的线程或项目；' +
    'AI 会整理摘要并归入各线程。模型不可用时只存原文，绝不丢。</p>' +
    '<form id="log-form">' +
    '<div class="log-projs">' + (boxes || '<span class="hint">还没有已建档的项目，先在「项目」页建档。</span>') + '</div>' +
    '<textarea id="log-text" rows="8" required placeholder="今天和木子/冯老师沟通了什么、定了什么、下一步做什么…">' +
    esc(saved?.text ?? '') + '</textarea>' +
    '<div class="row"><button class="primary" type="submit">保存日志</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  const modal = document.getElementById('modal') as HTMLElement | null;
  if (modal) {
    modal.dataset.draftEntity = 'log:' + defaultProject;
    modal.dataset.draftDirty = saved ? '1' : '0';
  }
  const persistLogDraft = (): void => {
    const text = (document.getElementById('log-text') as HTMLTextAreaElement | null)?.value ?? '';
    const projects = Array.from(document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]:checked')).map((i) => i.value);
    persistEntityDraft('log:' + defaultProject, { projects, text });
  };
  document.getElementById('log-form')?.addEventListener('input', persistLogDraft);
  document.getElementById('log-form')?.addEventListener('change', persistLogDraft);
  document.getElementById('log-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitLog();
  });
}

async function submitLog(): Promise<void> {
  const text = ((document.getElementById('log-text') as HTMLTextAreaElement | null)?.value ?? '').trim();
  const projects = Array.from(
    document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]:checked')
  ).map((i) => i.value);
  if (!text) {
    toast('日志内容为空', 'err');
    return;
  }
  if (projects.length === 0) {
    toast('至少勾选一个线程/项目', 'err');
    return;
  }
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/threads/logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projects, text }),
    }));
    if (r.ok) {
      const entity = document.getElementById('modal')?.dataset.draftEntity;
      if (entity) clearEntityDraft(entity, remoteVersion?.workspace_id);
      closeModal();
    }
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
}

/** AI 产物入库弹窗：选线程 + 粘贴阶段总结/PRD/背景包全文 → 自动命名与摘要索引。 */
interface ArtifactDraft {
  project: string;
  title: string;
  text: string;
  syncState: boolean;
}

function openArtifactModal(defaultProject: string): void {
  const registered = (state?.projects ?? []).filter((p) => p.registered);
  const saved = loadEntityDraft<ArtifactDraft>('artifact:' + defaultProject, Date.now(), remoteVersion?.workspace_id);
  const options = registered
    .map((p) =>
      '<option value="' + esc(p.name) + '"' + (p.name === defaultProject ? ' selected' : '') + '>' +
      esc(projectDisplayName(p)) + (projectDisplayName(p) !== p.name ? '（' + esc(p.name) + '）' : '') + '</option>'
    )
    .join('');
  openModal(
    '<h3>存入 AI 产物 / 导入文档</h3>' +
    '<p class="hint">粘贴和 AI 长对话产出的阶段总结 / 背景包 / PRD / 时间线全文，<strong>或直接选择本地 .md/.txt 文件</strong>；' +
    '系统自动命名、生成摘要索引并归入所选线程档案。<strong>也可以直接把文件从访达拖进本窗口</strong>。</p>' +
    '<form id="artifact-form">' +
    '<div class="form-row"><label>归入线程/项目</label>' +
    '<select id="artifact-project">' + (options || '<option value="">（无已建档项目）</option>') + '</select></div>' +
    '<input id="artifact-title" placeholder="标题（可选；留空则 AI 自动起）">' +
    '<div class="form-row artifact-file-row"><label class="ghost artifact-pick" for="artifact-file">📄 选择本地文件' +
    '<input id="artifact-file" type="file" accept=".md,.txt" class="visually-hidden"></label>' +
    '<span class="hint" id="artifact-file-name"></span></div>' +
    '<textarea id="artifact-text" rows="10" required placeholder="把整份文档粘贴在这里，或点上方按钮读入本地文件…"></textarea>' +
    '<label class="hint artifact-to-state"><input type="checkbox" id="artifact-to-state"> ' +
    '保存后先预览并确认把本文档摘要同步为主档案「当前状态」（会覆盖原内容，旧版可在 vault git 找回）</label>' +
    '<div class="row"><button class="primary" type="submit">存入档案</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  document.getElementById('artifact-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitArtifact();
  });
  const savedProject = saved?.project || defaultProject;
  const projectInput = document.getElementById('artifact-project') as HTMLSelectElement | null;
  const titleInput = document.getElementById('artifact-title') as HTMLInputElement | null;
  const textArea = document.getElementById('artifact-text') as HTMLTextAreaElement | null;
  const stateInput = document.getElementById('artifact-to-state') as HTMLInputElement | null;
  if (projectInput && savedProject) projectInput.value = savedProject;
  if (titleInput) titleInput.value = saved?.title ?? '';
  if (textArea) textArea.value = saved?.text ?? '';
  if (stateInput) stateInput.checked = saved?.syncState ?? false;
  const modal = document.getElementById('modal') as HTMLElement | null;
  if (modal) {
    modal.dataset.draftEntity = 'artifact:' + defaultProject;
    modal.dataset.draftDirty = saved ? '1' : '0';
  }
  const persistArtifactDraft = (): void => {
    persistEntityDraft('artifact:' + defaultProject, {
      project: (document.getElementById('artifact-project') as HTMLSelectElement | null)?.value ?? '',
      title: (document.getElementById('artifact-title') as HTMLInputElement | null)?.value ?? '',
      text: (document.getElementById('artifact-text') as HTMLTextAreaElement | null)?.value ?? '',
      syncState: !!(document.getElementById('artifact-to-state') as HTMLInputElement | null)?.checked,
    });
  };
  document.getElementById('artifact-form')?.addEventListener('input', persistArtifactDraft);
  document.getElementById('artifact-form')?.addEventListener('change', persistArtifactDraft);
  const readArtifactFile = (file: File): void => {
    const reader = new FileReader();
    reader.onload = () => {
      const content = String(reader.result ?? '');
      const titleInput = document.getElementById('artifact-title') as HTMLInputElement | null;
      const textArea = document.getElementById('artifact-text') as HTMLTextAreaElement | null;
      if (titleInput && !titleInput.value.trim()) {
        titleInput.value = file.name.replace(/\.(md|txt)$/i, '');
      }
      if (textArea) textArea.value = content;
      const nameEl = document.getElementById('artifact-file-name');
      if (nameEl) nameEl.textContent = '已读入：' + file.name + '（' + content.length + ' 字符）';
      persistArtifactDraft();
    };
    reader.onerror = () => toast('读取文件失败', 'err');
    reader.readAsText(file, 'utf-8');
  };
  const fileInput = document.getElementById('artifact-file') as HTMLInputElement | null;
  fileInput?.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) readArtifactFile(file);
  });
  // 拖放读入（绕过系统文件选择框：WKWebView 对 picker 的兼容问题）
  const dropTarget = document.getElementById('artifact-form') as HTMLElement | null;
  dropTarget?.addEventListener('dragover', (ev) => {
    ev.preventDefault();
    dropTarget.classList.add('artifact-drop');
  });
  dropTarget?.addEventListener('dragleave', () => dropTarget.classList.remove('artifact-drop'));
  dropTarget?.addEventListener('drop', (ev) => {
    ev.preventDefault();
    dropTarget.classList.remove('artifact-drop');
    const file = ev.dataTransfer?.files?.[0];
    if (file) {
      readArtifactFile(file);
      toast('已读取文件：' + file.name, 'ok');
    }
  });
}

async function submitArtifact(): Promise<void> {
  const text = ((document.getElementById('artifact-text') as HTMLTextAreaElement | null)?.value ?? '').trim();
  const project = ((document.getElementById('artifact-project') as HTMLSelectElement | null)?.value ?? '').trim();
  const title = ((document.getElementById('artifact-title') as HTMLInputElement | null)?.value ?? '').trim();
  const syncState = !!((document.getElementById('artifact-to-state') as HTMLInputElement | null)?.checked);
  if (!text) {
    toast('产物内容为空', 'err');
    return;
  }
  if (!project) {
    toast('请选择归入的线程/项目', 'err');
    return;
  }
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string; summary?: string }>('/api/threads/artifacts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, text, title: title || null }),
    }));
    if (!r.ok) {
      toast(r.message, 'err');
      return;
    }
    let extra = '';
    if (syncState) {
      const stateText = r.summary || title || text.slice(0, 80).replace(/\s+/g, ' ');
      const preview = stateText.length > 1200 ? stateText.slice(0, 1200) + '\n…（预览已截断）' : stateText;
      const confirmed = window.confirm(
        '产物已保存。\n\n即将把以下内容写入主档案「当前状态」：\n\n' + preview + '\n\n确认继续？',
      );
      if (confirmed) {
        const s = await mutation(() => api<{ ok: boolean; message: string }>('/api/threads/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project, text: stateText }),
        }));
        extra = s.ok ? ' · 已同步当前状态' : '（当前状态同步失败：' + s.message + '）';
      } else {
        extra = ' · 已保存产物，未修改当前状态';
      }
    }
    const modal = document.getElementById('modal') as HTMLElement | null;
    const draftEntity = modal?.dataset.draftEntity;
    if (draftEntity) clearEntityDraft(draftEntity, remoteVersion?.workspace_id);
    if (draftEntity !== 'artifact:' + project) {
      clearEntityDraft('artifact:' + project, remoteVersion?.workspace_id);
    }
    closeModal();
    toast(r.message + extra, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
}

/** 线视图（P2）：渲染项目/线程的档案区块 + 时间线。 */
function projectViewHtml(v: ProjectView): string {
  const order = ['当前状态', '下一步', '阻塞', '跟进事项', '决策记录'];
  const blockSections = order.map((label) => {
    const lines = v.blocks[label] ?? [];
    if (lines.length === 0) return '';
    const rows = lines.map((raw) => {
      let text = raw;
      let mark = '';
      if (text.startsWith('- [ ] ')) { mark = '☐ '; text = text.slice(6); }
      else if (text.startsWith('- [x] ')) { mark = '☑ '; text = text.slice(6); }
      else if (text.startsWith('- ')) { text = text.slice(2); }
      return '<li>' + mark + esc(text) + '</li>';
    }).join('');
    const extra = label === '跟进事项' && v.followup_pending > 0
      ? ' <span class="badge warn">' + v.followup_pending + ' 条待闭环</span>'
      : (label === '下一步' && lines.length === 0 ? '' : '');
    return '<div class="pv-block"><h4>' + esc(label) + extra + '</h4><ul>' + rows + '</ul></div>';
  }).join('');
  const timeline = v.timeline.length
    ? '<ul class="pv-timeline">' + v.timeline.map((t) =>
        '<li class="tl-kind-' + esc(t.kind) + '">' +
        '<span class="tl-date">' + esc(t.date) + '</span>' +
        '<span class="tl-label">' + esc(t.label) + '</span>' +
        '<span class="tl-title">' + esc(t.title) + '</span>' +
        (t.snippet ? '<div class="tl-snippet">' + esc(t.snippet) + '</div>' : '') +
        '</li>'
      ).join('') + '</ul>'
    : '<p class="hint">还没有推进日志/产物/关联会议——用下方「✎ 日志」「存产物」开始积累。</p>';
  const inboxNote = v.inbox_pending > 0
    ? '<p class="hint">📥 线程 inbox 有 ' + v.inbox_pending + ' 条待处理</p>' : '';
  const statusBadge = v.status === 'archived' ? '已归档' : '在工作台';
  const disp = (v.title && v.title.trim()) || v.name;
  return (
    '<div class="pv">' +
    '<div class="pv-head">' +
    '<div><h3 class="project-name" id="pv-title">' + esc(disp) + '</h3>' +
    (disp !== v.name ? '<div class="hint">档案 ID：' + esc(v.name) + '</div>' : '') +
    '<div class="hint">状态：' + esc(statusBadge) + (v.updated ? ' · 更新于 ' + esc(v.updated) : '') + '</div>' +
    inboxNote + '</div>' +
    '<div class="row">' +
    '<button class="ok" data-action="pv-log" title="追加推进日志">✎ 日志</button>' +
    '<button class="ghost" id="pv-rename" title="修改显示名（不改档案 ID / 文件夹 / git）">✎ 显示名</button>' +
    '<button class="ghost" data-action="pv-artifact" title="把 AI 产物存入本档案">存产物</button>' +
    '<button class="ghost" data-action="pv-refresh" title="重新加载">↻ 刷新</button>' +
    '</div></div>' +
    '<div class="pv-blocks">' + blockSections + '</div>' +
    '<div class="pv-timeline-wrap"><h4>时间线</h4>' + timeline + '</div>' +
    '<div class="row"><button class="primary" data-action="pv-close">关闭</button></div>' +
    '</div>'
  );
}

/** 打开某项目/线程的线视图（模态内展示，含 日志/产物/刷新/关闭 操作）。 */
async function showProjectView(name: string): Promise<void> {
  if (!name) return;
  let view: ProjectView;
  try {
    view = await api<ProjectView>('/api/projects/view?name=' + encodeURIComponent(name));
  } catch (err) {
    toast(String(err), 'err');
    return;
  }
  if (!view.ok) {
    toast(view.message ?? '打开失败', 'err');
    return;
  }
  const modal = activateModal(projectViewHtml(view));
  modal.querySelector('[data-action="pv-close"]')?.addEventListener('click', closeModal);
  modal.querySelector('[data-action="pv-refresh"]')?.addEventListener('click', () => { void showProjectView(name); });
  modal.querySelector('[data-action="pv-log"]')?.addEventListener('click', () => openLogModal(name));
  modal.querySelector('[data-action="pv-artifact"]')?.addEventListener('click', () => openArtifactModal(name));

  const renameBtn = modal.querySelector<HTMLButtonElement>('#pv-rename');
  renameBtn?.addEventListener('click', () => {
    const titleBox = modal.querySelector('#pv-title');
    if (!titleBox) return;
    const cur = (view.title && view.title.trim()) || view.name;
    const wrap = document.createElement('div');
    wrap.className = 'pv-rename';
    const input = document.createElement('input');
    input.value = cur;
    input.maxLength = 60;
    input.placeholder = '显示名（如：活满报名系统）';
    const save = document.createElement('button');
    save.className = 'ok';
    save.type = 'button';
    save.textContent = '保存';
    const cancel = document.createElement('button');
    cancel.className = 'ghost';
    cancel.type = 'button';
    cancel.textContent = '取消';
    wrap.append(input, save, cancel);
    titleBox.replaceWith(wrap);
    input.focus();
    input.select();
    const commit = (): void => {
      const value = input.value.trim();
      if (!value) {
        toast('显示名不能为空', 'err');
        return;
      }
      void mutation(async () => {
        const r = await api<{ ok: boolean; message: string }>('/api/projects/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: view.name, title: value }),
        });
        toast(r.message, r.ok ? 'ok' : 'err');
        if (r.ok) {
          void showProjectView(view.name);
          void refreshState();
        }
      }).catch((err: unknown) => toast(String(err), 'err'));
    };
    save.addEventListener('click', commit);
    cancel.addEventListener('click', () => { void showProjectView(view.name); });
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        commit();
      } else if (ev.key === 'Escape') {
        void showProjectView(view.name);
      }
    });
  });
}

// ---------- 撤销系统改动（P0'） ----------

interface WbCommitItem {
  sha: string;
  short_sha: string;
  message: string;
  time: string;
  files: string[];
}

interface UndoHistoryPayload {
  ok: boolean;
  commits?: WbCommitItem[];
  note?: string | null;
  message?: string;
}

interface UndoDiffPayload {
  ok: boolean;
  diff?: string;
  message?: string;
}

const UNDO_FLYNOTE =
  '还原只作用于 vault 文件；飞书侧已产生的副作用（已建任务/会议、已完成状态）不可撤销、不受本次还原影响。';

async function openUndoModal(): Promise<void> {
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement;
  const modal = document.getElementById('modal') as HTMLElement;
  modal.innerHTML = '<div class="loading">正在读取系统自动提交…</div>';
  backdrop.hidden = false;
  let history: UndoHistoryPayload;
  try {
    history = await api<UndoHistoryPayload>('/api/undo/history');
  } catch (err) {
    modal.innerHTML = '<h3>撤销系统改动</h3><p class="msg err">' + esc(String(err)) + '</p>';
    return;
  }
  if (!history.ok || !history.commits) {
    modal.innerHTML =
      '<h3>撤销系统改动</h3><p class="msg err">' + esc(history.message ?? '读取失败') + '</p>';
    return;
  }
  if (history.commits.length === 0) {
    modal.innerHTML =
      '<h3>撤销系统改动</h3>' +
      '<p>' + esc(history.note ?? '暂无系统自动提交') + '</p>' +
      '<p class="hint">每次系统写回成功都会自动留痕（git 提交，消息以 wb: 开头），可在此一键还原。' + UNDO_FLYNOTE + '</p>';
    return;
  }
  const rows = history.commits.map((c) =>
    '<div class="undo-commit">' +
    '<div class="undo-head"><strong>' + esc(c.message) + '</strong>' +
    '<span class="hint">' + esc(c.short_sha) + ' · ' + esc(c.time.replace('T', ' ').slice(0, 16)) + '</span></div>' +
    '<div class="hint undo-files">触碰文件：' + esc(c.files.join('、')) + '</div>' +
    '<button class="ghost" data-undo="diff" data-sha="' + c.sha + '">查看差异</button> ' +
    '<button class="ok" data-undo="revert" data-sha="' + c.sha + '">还原此提交</button>' +
    '<pre class="undo-diff" hidden></pre>' +
    '</div>'
  ).join('');
  modal.innerHTML =
    '<h3>撤销系统改动</h3>' +
    '<p class="hint">' + UNDO_FLYNOTE + ' 工作树有未提交人工改动的文件会被拒绝还原。</p>' + rows;
  modal.querySelectorAll<HTMLElement>('[data-undo]').forEach((btn) => {
    const sha = btn.dataset.sha ?? '';
    if (btn.dataset.undo === 'diff') {
      btn.addEventListener('click', () => { void loadUndoDiff(btn, sha); });
    } else if (btn.dataset.undo === 'revert') {
      btn.addEventListener('click', () => { void doUndoRevert(sha); });
    }
  });
}

async function loadUndoDiff(btn: HTMLElement, sha: string): Promise<void> {
  const row = btn.closest<HTMLElement>('.undo-commit');
  const pre = row?.querySelector<HTMLElement>('.undo-diff');
  if (!pre) return;
  if (!pre.hidden && pre.textContent) {
    pre.hidden = true;
    return;
  }
  pre.hidden = false;
  pre.textContent = '正在读取差异…';
  try {
    const r = await api<UndoDiffPayload>('/api/undo/diff?sha=' + encodeURIComponent(sha));
    pre.textContent = r.ok ? (r.diff ?? '') : ('读取失败：' + (r.message ?? ''));
  } catch (err) {
    pre.textContent = String(err);
  }
}

async function doUndoRevert(sha: string): Promise<void> {
  if (!window.confirm('确定还原该次系统改动？' + UNDO_FLYNOTE)) return;
  try {
    const r = await mutation(() =>
      api<{ ok: boolean; message: string }>('/api/undo/revert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sha }),
      })
    );
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) {
      closeModal();
      void refreshAll();
    }
  } catch (err) {
    toast(String(err), 'err');
  }
}
async function runBrief(): Promise<void> {
  toast('正在生成今日简报…', 'info');
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/run/brief', { method: 'POST' }));
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshState();
}

/** 「今日」待办任务行的一键完成：写回飞书成功后刷新（快照镜像 → 行消失、进「最近完成」）。 */
async function completeTask(btn: HTMLElement): Promise<void> {
  const guid = btn.dataset.task ?? '';
  const row = btn.closest<HTMLElement>('.bf-task');
  if (!guid || !row) return;
  const doneBtn = btn as HTMLButtonElement;
  doneBtn.disabled = true;
  doneBtn.classList.add('busy');
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/tasks/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: guid }),
    }));
    toast(r.message, r.ok ? 'ok' : 'err');
    if (!r.ok) {
      doneBtn.disabled = false;
      doneBtn.classList.remove('busy');
      return;
    }
    void refreshState();
  } catch (err) {
    toast(String(err), 'err');
    doneBtn.disabled = false;
    doneBtn.classList.remove('busy');
  }
}

/** unix 秒（字符串）→ 本地 datetime-local 输入值（YYYY-MM-DDTHH:MM）；无效返回空串。 */
function tsToDatetimeLocal(ts: string | null | undefined): string {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const d = new Date(seconds * 1000);
  const pad = (x: number): string => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

/** unix 秒 + 分钟偏移 → datetime-local 输入值（结束时间缺省 = 开始 + 60 分钟）。 */
function plusMinutesInput(ts: string | null | undefined, minutes: number): string {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const d = new Date((seconds + minutes * 60) * 1000);
  const pad = (x: number): string => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

/** 打开任务/会议的行内编辑弹窗（改动直接写回飞书本体）。 */
function openRowEditModal(kind: 'task' | 'meeting', seed: Record<string, string>): void {
  const hint = kind === 'task'
    ? '<p class="hint">改动直接写回飞书任务本体；清空截止 = 移除截止日期。</p>'
    : '<p class="hint">改动直接写回飞书日历事件（个人日程，不邀请他人）。</p>';
  const body = kind === 'task'
    ? '<label>标题</label><input id="row-edit-summary" required value="' + esc(seed.title ?? '') + '">' +
      '<div class="form-row"><label>截止日期</label><input id="row-edit-due" type="date" value="' +
      esc(seed.due ?? '') + '"></div>'
    : '<label>标题</label><input id="row-edit-summary" required value="' + esc(seed.title ?? '') + '">' +
      '<div class="grid2">' +
      '<div><label>开始时间</label><input id="row-edit-start" type="datetime-local" required value="' +
      esc(seed.start ?? '') + '"></div>' +
      '<div><label>结束时间</label><input id="row-edit-end" type="datetime-local" required value="' +
      esc(seed.end ?? '') + '"></div>' +
      '</div>';
  openModal(
    '<h3>' + (kind === 'task' ? '编辑任务' : '编辑会议') + '</h3>' + hint +
    '<form id="row-edit-form">' + body +
    '<div class="row"><button class="primary" type="submit">保存</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  const form = document.getElementById('row-edit-form') as HTMLFormElement | null;
  form?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitRowEdit(kind, seed.id ?? '');
  });
}

/** 行内编辑提交：任务/会议 → PATCH 写回飞书 + 快照镜像 → 刷新「今日」。 */
async function submitRowEdit(kind: 'task' | 'meeting', id: string): Promise<void> {
  if (!id) {
    toast('缺少目标 id', 'err');
    return;
  }
  const summaryInput = document.getElementById('row-edit-summary') as HTMLInputElement | null;
  const summary = (summaryInput?.value ?? '').trim();
  if (!summary) {
    toast('标题不能为空', 'err');
    return;
  }
  const url = kind === 'task' ? '/api/tasks/update' : '/api/meetings/update';
  const body: Record<string, string> = kind === 'task'
    ? {
        task_id: id,
        summary,
        due_date: (document.getElementById('row-edit-due') as HTMLInputElement | null)?.value ?? '',
      }
    : {
        event_id: id,
        summary,
        start_at: (document.getElementById('row-edit-start') as HTMLInputElement | null)?.value ?? '',
        end_at: (document.getElementById('row-edit-end') as HTMLInputElement | null)?.value ?? '',
      };
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
    closeModal();
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) void refreshState();
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function planApply(exec: boolean): Promise<void> {
  if (exec && !reviewPlanReady) {
    toast('请先查看最新预演，再确认写回', 'info');
    return;
  }
  const planResult = document.getElementById('plan-result');
  try {
    const r = await mutation(() => api<{
      ok: boolean;
      message?: string;
      plan_text?: string;
      executed?: boolean;
      applied?: number;
      rejected?: number;
      failed?: number;
      external_actions?: ExternalAction[];
    }>(
      exec ? '/api/review/apply' : '/api/review/plan',
      { method: 'POST' },
    ));
    if (!r.ok) {
      reviewPlanReady = false;
      toast(r.message ?? '操作失败', 'err');
      return;
    }
    const text = r.plan_text ?? '';
    const title = exec
      ? (typeof r.failed === 'number' && r.failed > 0 ? '部分完成：仍有条目需处理' : '完成：已应用')
      : '预演计划（未写入）';
    openModal(
      '<h3>' + title + '</h3><pre>' + esc(text) + '</pre>' +
      (exec
        ? '<p class="hint">已应用 ' + String(r.applied ?? 0) + ' 条 · 已拒绝 ' + String(r.rejected ?? 0) +
          ' 条 · 失败 ' + String(r.failed ?? 0) + ' 条。失败项和未知外部结果请在审批页继续处理。</p>'
        : '<div class="row"><button class="primary" data-action="apply">确认应用（写回项目/建任务/归档）</button></div>')
    );
    reviewPlanReady = !exec;
    if (exec) {
      reviewPlanReady = false;
      if (r.external_actions) externalActions = r.external_actions;
      toast(typeof r.failed === 'number' && r.failed > 0 ? '应用部分完成，请查看失败项' : '应用完成', r.failed ? 'info' : 'ok');
      void refreshReview();
      void refreshState();
    }
  } catch (err) {
    toast(String(err), 'err');
    if (planResult) planResult.innerHTML = '<div class="msg err">' + esc(String(err)) + '</div>';
  }
}

function activateModal(html: string, includeCloseButton = false): HTMLElement {
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement;
  const modal = document.getElementById('modal') as HTMLElement;
  if (backdrop.hidden) {
    modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  modal.innerHTML = html;
  backdrop.hidden = false;
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('tabindex', '-1');
  const heading = modal.querySelector<HTMLElement>('h2, h3');
  if (heading) {
    if (!heading.id) heading.id = 'modal-title';
    modal.setAttribute('aria-labelledby', heading.id);
  } else {
    modal.removeAttribute('aria-labelledby');
  }
  if (includeCloseButton) {
    const close = document.createElement('button');
    close.className = 'ghost close-modal';
    close.textContent = '关闭';
    close.style.marginTop = '12px';
    modal.appendChild(close);
    close.addEventListener('click', requestModalClose);
  }
  const first = modal.querySelector<HTMLElement>('button, input, select, textarea, [tabindex="0"]');
  (first ?? modal).focus();
  return modal;
}

function openModal(html: string): void {
  const modal = activateModal(html, true);
  modal.dataset.draftDirty = '0';
  delete modal.dataset.draftEntity;
  modal.oninput = () => {
    if (modal.dataset.draftEntity) modal.dataset.draftDirty = '1';
  };
  modal.onchange = () => {
    if (modal.dataset.draftEntity) modal.dataset.draftDirty = '1';
  };
}

function closeModal(): void {
  (document.getElementById('modal-backdrop') as HTMLElement).hidden = true;
  modalReturnFocus?.focus();
  modalReturnFocus = null;
}

function requestModalClose(): void {
  const modal = document.getElementById('modal') as HTMLElement | null;
  const hasDraft = modal?.dataset.draftDirty === '1';
  if (hasDraft && !window.confirm('当前弹层里有未保存内容。继续关闭并放弃草稿吗？')) return;
  closeModal();
}

// ---------- 数据 ----------

async function refreshState(): Promise<boolean> {
  const requestId = ++latestStateRequest;
  try {
    const nextState = await api<StatePayload>('/api/state');
    if (requestId !== latestStateRequest) return false;
    state = nextState;
    stateLoadError = null;
    lastStateReadAt = new Date().toLocaleString('zh-CN', { hour12: false });
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) return false;
    stateLoadError = String(err);
    if (tab === 'today') renderToday(document.getElementById('view-today') as HTMLElement);
    return false;
  }
  const dayPill = document.getElementById('day-pill');
  if (dayPill) dayPill.textContent = state.day;
  const badge = document.getElementById('tab-badge-review');
  if (badge) badge.textContent = state.status.pending_review > 0 ? String(state.status.pending_review) : '';
  if (tab === 'today') renderToday(document.getElementById('view-today') as HTMLElement);
  else if (tab === 'projects') {
    renderProjects(document.getElementById('view-projects') as HTMLElement);
  }
  return true;
}

async function refreshReview(): Promise<boolean> {
  const requestId = ++latestReviewRequest;
  saveCurrentDraftSnapshot();
  try {
    const nextReview = await api<ReviewPayload>('/api/review');
    if (requestId !== latestReviewRequest) return false;
    review = nextReview;
    reviewLoadError = null;
    lastReviewReadAt = new Date().toLocaleString('zh-CN', { hour12: false });
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) return false;
    reviewLoadError = String(err);
    if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
    return false;
  }
  await refreshExternalActions();
  if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
  return true;
}

async function refreshExternalActions(): Promise<void> {
  try {
    const data = await api<{ ok: boolean; actions?: ExternalAction[] }>('/api/external-actions');
    if (data.ok) {
      externalActions = data.actions ?? [];
      externalActionsError = null;
    } else {
      externalActionsError = '服务端没有返回可用状态';
    }
    if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
  } catch (err) {
    // 外部状态查询失败不阻断审批页本身，但必须在页面上可见。
    if (isStaleWorkspaceResponse(err)) return;
    externalActionsError = String(err);
    if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
  }
}

async function refreshAll(): Promise<{ state: boolean; review: boolean }> {
  const [stateOk, reviewOk] = await Promise.all([refreshState(), refreshReview()]);
  return { state: stateOk, review: reviewOk };
}

function conflictKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    'append-only-event': '活动事件（自动收集）',
    'generated-view': '派生视图（重建）',
    'unknown-generated-view': '未知派生视图（保留双方）',
    'manual-markdown': 'Markdown（人工选择）',
    'opaque-binary': '未知/二进制（保留双方）',
  };
  return labels[kind] ?? kind;
}

function conflictSelectionLabel(choice: ConflictSelection): string {
  const labels: Record<string, string> = {
    'keep-local': '保留本机',
    'keep-remote': '采用远端',
    'preserve-both': '保留双方副本',
  };
  return labels[choice] ?? '请选择处理方式';
}

function conflictRevision(revision: string): string {
  return revision.length > 12 ? revision.slice(0, 12) + '…' : revision;
}

function conflictEventSummary(event: Record<string, string> | null | undefined): string {
  if (!event || event.parse_status) return '';
  return '设备 ' + (event.device_id ?? '—') + ' · 时间 ' + (event.occurred_at ?? '—') +
    ' · 操作 ' + (event.causation_operation_id ?? '—');
}

function conflictDigestSummary(item: ConflictPathDetail): string {
  if (item.kind === 'append-only-event') {
    return [conflictEventSummary(item.local_event), conflictEventSummary(item.remote_event)].filter(Boolean).join(' / ');
  }
  if (item.local_sha256 || item.remote_sha256) {
    return '摘要 本机 ' + conflictRevision(item.local_sha256 ?? '—') + ' · 远端 ' + conflictRevision(item.remote_sha256 ?? '—');
  }
  return '';
}

function conflictSelectionsPayload(): Record<string, string> {
  return Object.fromEntries(Object.entries(conflictSelections).filter(([, choice]) => choice)) as Record<string, string>;
}

function missingConflictSelections(): string[] {
  return conflictDetails?.paths.filter((item) => !item.automatic && !conflictSelections[item.path]).map((item) => item.path) ?? [];
}

function renderSyncConflictModal(): void {
  const modal = document.getElementById('modal') as HTMLElement | null;
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement | null;
  if (!modal || !backdrop || !conflictDetails) return;
  const details = conflictDetails;
  const missing = missingConflictSelections();
  const preparation = conflictPreparation;
  const message = conflictMessage
    ? '<div class="msg ' + (preparation?.ok ? 'ok' : 'err') + '">' + esc(conflictMessage) + '</div>' : '';
  const pathRows = details.paths.map((item) => {
    const changedOn = item.changed_on.map((side) => side === 'local' ? '本机' : '远端').join('、');
    const metadata = conflictDigestSummary(item);
    const selector = item.automatic
      ? '<span class="conflict-auto">' + esc(item.action === 'rebuild' ? '合并后重建' : '自动收集') + '</span>'
      : '<label class="conflict-choice"><span class="sr-only">' + esc(item.path) + '处理方式</span>' +
        '<select data-conflict-path="' + esc(item.path) + '"' + (conflictBusy ? ' disabled' : '') + '>' +
        '<option value="">请选择处理方式</option>' +
        ((item.kind === 'unknown-generated-view' || item.kind === 'opaque-binary')
          ? ['preserve-both'] as ConflictSelection[]
          : ['keep-local', 'keep-remote', 'preserve-both'] as ConflictSelection[]).map((choice) =>
          '<option value="' + choice + '"' + (conflictSelections[item.path] === choice ? ' selected' : '') + '>' +
          conflictSelectionLabel(choice) + '</option>').join('') + '</select></label>';
    return '<div class="conflict-path"><div class="conflict-path-main"><code>' + esc(item.path) + '</code>' +
      '<span class="hint">' + esc(conflictKindLabel(item.kind)) + ' · 变更：' + esc(changedOn) + '</span>' +
      (metadata ? '<span class="hint conflict-metadata">' + esc(metadata) + '</span>' : '') + '</div>' +
      '<div class="conflict-path-action">' + selector + '</div></div>';
  }).join('');
  const status = preparation
    ? '<div class="conflict-preflight"><strong>' + (preparation.ok ? '临时预检通过' : '临时预检未通过') + '</strong>' +
      '<span>事件 ' + preparation.event_count + ' · 聚合 ' + preparation.aggregate_count +
      ' · 重建视图 ' + preparation.rebuilt_view_count + ' · 候选文件 ' + preparation.candidate_path_count + '</span>' +
      (preparation.error_code ? '<span class="hint">原因：' + esc(preparation.error_code) + '</span>' : '') + '</div>' : '';
  modal.innerHTML = '<h3>同步冲突详情</h3>' +
    '<p class="hint">当前处于保护态。这里只读取已存在的分叉快照，不展示正文；确认前不会修改 vault。</p>' +
    '<div class="conflict-revisions"><span>共同基线 <code>' + esc(conflictRevision(details.base_revision)) + '</code></span>' +
    '<span>本机 <code>' + esc(conflictRevision(details.local.revision)) + '</code></span>' +
    '<span>远端 <code>' + esc(conflictRevision(details.remote.revision)) + '</code></span></div>' +
    '<div class="conflict-summary">自动处理 ' + details.automatic_path_count + ' 项 · 需要选择 ' + details.manual_path_count + ' 项</div>' +
    '<div class="conflict-paths">' + (pathRows || '<p class="hint">没有可处理的分叉文件。</p>') + '</div>' + message + status +
    '<p class="hint conflict-safety">恢复只会创建普通的本地双父提交，并尝试普通同步；不会 force-push、reset、rebase 或 stash。若远端已再次变化，仍会回到保护态。</p>' +
    '<div class="row"><button class="primary" data-action="sync-conflict-preview"' +
    (conflictBusy || missing.length > 0 ? ' disabled' : '') + '>临时预检（不写入）</button>' +
    (preparation?.ok ? '<button class="ok" data-action="sync-conflict-apply"' + (conflictBusy ? ' disabled' : '') + '>确认恢复并创建提交</button>' : '') +
    '<button class="ghost" data-action="sync-conflict-export"' + (conflictBusy ? ' disabled' : '') + '>导出冲突包</button>' +
    '<button class="ghost" data-action="copy-diagnostics"' + (conflictBusy ? ' disabled' : '') + '>复制诊断</button>' +
    '<button class="ghost" data-action="close-modal"' + (conflictBusy ? ' disabled' : '') + '>稍后处理</button></div>';
  backdrop.hidden = false;
  modal.querySelectorAll<HTMLSelectElement>('[data-conflict-path]').forEach((select) => {
    select.addEventListener('change', () => {
      const path = select.dataset.conflictPath ?? '';
      if (path) conflictSelections[path] = select.value as ConflictSelection;
      conflictMessage = null;
      renderSyncConflictModal();
    });
  });
}

async function showSyncConflictDetails(): Promise<void> {
  const modal = document.getElementById('modal') as HTMLElement | null;
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement | null;
  if (!modal || !backdrop) return;
  modal.innerHTML = '<div class="loading">正在读取分叉详情（只读）…</div>';
  backdrop.hidden = false;
  conflictDetails = null;
  conflictPreparation = null;
  conflictMessage = null;
  conflictBusy = false;
  try {
    const data = await api<SyncConflictDetailsPayload>('/api/sync/conflict/details');
    if (!data.ok || !data.available || !data.details) {
      modal.innerHTML = '<h3>无法读取同步冲突</h3><p class="msg err">' + esc(data.reason ?? '当前已不在冲突保护态，请刷新同步状态。') + '</p>' +
        '<div class="row"><button class="ghost" data-action="close-modal">关闭</button></div>';
      return;
    }
    conflictDetails = data.details;
    conflictSelections = Object.fromEntries(data.details.paths.filter((item) => !item.automatic).map((item) => [item.path, '']));
    renderSyncConflictModal();
  } catch (err) {
    modal.innerHTML = '<h3>无法读取同步冲突</h3><p class="msg err">' + esc(String(err)) + '</p>' +
      '<div class="row"><button class="ghost" data-action="close-modal">关闭</button></div>';
  }
}

function conflictRecoveryRequest(confirmed: boolean): Record<string, unknown> {
  if (!conflictDetails) throw new Error('缺少分叉快照');
  return {
    base_revision: conflictDetails.base_revision,
    local_revision: conflictDetails.local.revision,
    remote_revision: conflictDetails.remote.revision,
    selections: conflictSelectionsPayload(),
    confirmed,
  };
}

function conflictSelectionRequest(): Record<string, unknown> {
  if (!conflictDetails) throw new Error('缺少分叉快照');
  return {
    base_revision: conflictDetails.base_revision,
    local_revision: conflictDetails.local.revision,
    remote_revision: conflictDetails.remote.revision,
    selections: conflictSelectionsPayload(),
  };
}

async function previewSyncConflictRecovery(): Promise<void> {
  if (!conflictDetails || conflictBusy) return;
  const missing = missingConflictSelections();
  if (missing.length) {
    conflictMessage = '请先为所有人工文件选择处理方式。';
    renderSyncConflictModal();
    return;
  }
  conflictBusy = true;
  conflictMessage = '正在临时环境预检，当前 vault 不会写入…';
  renderSyncConflictModal();
  try {
    const request = conflictRecoveryRequest(false);
    if (conflictDetails.manual_path_count > 0) {
      const selection = await api<{ ok: boolean; selection?: { error_code?: string | null }; reason?: string }>(
        '/api/sync/conflict/selection/validate',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conflictSelectionRequest()) },
      );
      if (!selection.ok) {
        conflictMessage = selection.reason ?? selection.selection?.error_code ?? '人工选择未通过校验。';
        conflictBusy = false;
        renderSyncConflictModal();
        return;
      }
    }
    const data = await api<SyncConflictRecoveryPayload>('/api/sync/conflict/recover', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
    });
    conflictPreparation = data.preparation ?? null;
    conflictMessage = data.preparation?.ok
      ? '预检完成。请确认后才会写回并创建提交。'
      : data.reason ?? '恢复准备未完成。';
  } catch (err) {
    conflictMessage = String(err);
  } finally {
    conflictBusy = false;
    renderSyncConflictModal();
  }
}

async function applySyncConflictRecovery(): Promise<void> {
  if (!conflictDetails || !conflictPreparation?.ok || conflictBusy) return;
  if (!window.confirm('确认将预检结果写回当前 vault，创建普通的本地双父合并提交，并尝试普通同步？')) return;
  conflictBusy = true;
  let committed = false;
  conflictMessage = '正在写回并创建本地恢复提交…';
  renderSyncConflictModal();
  try {
    const data = await mutation(() => api<SyncConflictRecoveryPayload>('/api/sync/conflict/recover', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(conflictRecoveryRequest(true)),
    }));
    if (data.recovery?.status === 'committed') {
      committed = true;
      closeModal();
      const auditFailed = data.recovery.audit?.status === 'failed';
      const message = auditFailed
        ? (data.push?.ok
          ? '恢复提交已同步，但脱敏审计记录未完成。'
          : '恢复提交已创建；普通同步与脱敏审计记录均未完成。')
        : (data.push?.ok
          ? '恢复提交已创建并完成普通同步。'
          : '恢复提交已创建，普通同步暂未完成，请稍后点击“立即重试”。');
      toast(message, data.push?.ok && !auditFailed ? 'ok' : 'info');
      await Promise.all([refreshSyncBanner(), refreshState()]);
      return;
    }
    conflictMessage = data.reason ?? '恢复未提交：' + (data.recovery?.error_code ?? data.recovery?.status ?? '未知原因');
  } catch (err) {
    conflictMessage = String(err);
  } finally {
    conflictBusy = false;
    if (!committed && conflictDetails) renderSyncConflictModal();
  }
}

async function refreshSyncBanner(): Promise<void> {
  const el = document.getElementById('sync-banner') as HTMLElement | null;
  if (!el) return;
  try {
    const data = await api<SyncStatusPayload>('/api/sync/status');
    const interesting = data.state !== 'ready' && data.state !== 'unconfigured';
    el.hidden = !interesting;
    if (interesting) {
      const rows = [
        ['状态', data.state],
        ['待推送', String(data.pending_commits ?? 0)],
        ['最后成功', data.last_sync_at ?? '—'],
        ['本地领先', String(data.ahead ?? 0)],
        ['远端领先', String(data.behind ?? 0)],
        ['分支', data.branch ?? '—'],
        ['远端主机', data.remote_host ?? '—'],
        ['仓库', (data.repo_states ?? []).join('、') || '—'],
        ['主设备', data.automation_primary_device_id ?? '—'],
        ['主设备代际', String(data.automation_primary_generation ?? '—')],
        ['下一步', data.next_step ?? '—'],
      ];
      const conflictAction = data.state === 'diverged-protected'
        ? '<button class="ghost" data-action="sync-conflict-details">查看冲突详情</button>' : '';
      el.innerHTML = '<div class="sync-title">同步状态</div>' +
        '<div class="sync-grid">' + rows.map(([label, value]) =>
          '<span class="sync-label">' + esc(label) + '</span><span>' + esc(value) + '</span>').join('') +
        '</div>' +
        (data.detail ? '<div class="sync-detail">' + esc(data.detail) + '</div>' : '') +
        '<div class="sync-actions">' + conflictAction + '<button class="ghost" data-action="sync-retry">立即重试</button>' +
        '<button class="ghost" data-action="sync-export">导出本机副本</button></div>';
    }
  } catch {
    el.hidden = true;
  }
}

async function retrySync(): Promise<void> {
  try {
    const data = await mutation(() => api<{ ok: boolean; message?: string }>('/api/sync/run', { method: 'POST' }));
    toast(data.ok ? '同步完成' : (data.message ?? '同步失败'), data.ok ? 'ok' : 'err');
    await Promise.all([refreshSyncBanner(), refreshState()]);
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function exportSyncSnapshot(): Promise<void> {
  try {
    const data = await api<SyncStatusPayload>('/api/sync/export');
    const content = JSON.stringify(data, null, 2) + '\n';
    if (sendNativeMessage({
      type: 'saveTextFile',
      filename: 'summitworkbench-sync-status.json',
      content,
    })) {
      toast('请选择保存位置', 'info');
      return;
    }
    const blob = new Blob([content], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'summitworkbench-sync-status.json';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(link.href);
      link.remove();
    }, 1000);
  } catch (err) {
    toast(String(err), 'err');
  }
}

async function exportSyncConflictPackage(): Promise<void> {
  try {
    const response = await fetch('/api/sync/conflict/export', { cache: 'no-store' });
    if (!response.ok) throw new Error('冲突包导出失败（HTTP ' + response.status + '）');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await response.blob());
    link.download = 'summitworkbench-sync-recovery.zip';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
    toast('冲突包已准备下载', 'ok');
  } catch (err) {
    toast(String(err), 'err');
  }
}

// ---------- 启动（由 main.ts composition root 调用） ----------

export function mountLegacyWorkbench(): void {
  renderShell();
  setMutationIdleHandler(async (targetBuild) => {
    saveCurrentDraftSnapshot();
    reloadToBuild(targetBuild);
  });
  window.addEventListener('focus', () => { void checkVersion('focus'); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void checkVersion('visible');
  });

  async function startApp(): Promise<void> {
    await checkVersion('startup');
    restoredDraft = loadDraftSnapshot(Date.now(), remoteVersion?.workspace_id);
    await refreshAll();
    if (restoredDraft) render();
  }

  void startApp();
  void refreshSyncBanner();
  window.setInterval(() => { void checkVersion('interval'); }, 60000);
  window.setInterval(() => { void refreshSyncBanner(); }, 60000);
}
