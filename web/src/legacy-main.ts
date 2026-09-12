import './style.css';

import {
  api,
  disposeApiClient,
  isStaleWorkspaceResponse,
  onConnectionRestored,
} from './api/request';
import { workspaceStore } from './core/workspace-store';
import { mutation, deferReloadUntilMutationsComplete, isMutationInFlight, setMutationIdleHandler } from './lifecycle/connection';
import {
  clearDraftSnapshot,
  loadDraftSnapshot,
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
import { esc } from './md';
import { type BriefData } from './brief-card';
import { projectDetailHtml, projectsListHtml } from './features/projects';
import type { ProjectListFilter, ProjectState, ProjectView } from './features/projects';
import { reviewHtml } from './features/review';
import type { ExternalAction, ReviewEntry, ReviewFilter, ReviewPayload } from './features/review';
import {
  applyTabChrome,
  closeModal,
  focusVisibleProjectLink,
  mountShell,
  openModal,
  rejectOversizeText,
  requestModalClose,
  toast,
  viewElement,
} from './features/shell';
import {
  askNewThread,
  askOpenThread,
  beginAskRename,
  deleteAskThread,
  getAskDraft,
  mountAsk,
  openSource,
  reloadAskStore,
  renderAsk,
  resetAskForWorkspace,
  setAskDraft,
} from './features/ask';
import {
  applySyncConflictRecovery,
  exportSyncConflictPackage,
  exportSyncSnapshot,
  mountSyncBanner,
  previewSyncConflictRecovery,
  refreshSyncBanner,
  retrySync,
  showSyncConflictDetails,
} from './features/sync';
import { mountUndo, openUndoModal } from './features/undo';
import { mountGuide } from './features/guide';
import { renderSettings as renderSettingsFeature } from './features/settings';
import {
  mountThreads,
  openArtifactModal,
  openLogModal,
} from './features/threads';
import { mountToday, plusMinutesInput, tsToDatetimeLocal, type ImportReceipt } from './features/today';

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

interface DiagnosticsPreviewPayload {
  ok: boolean;
  files: Array<{ name: string; description: string }>;
  snapshot: Record<string, unknown>;
}

let state: StatePayload | null = null;
let review: ReviewPayload | null = null;
let externalActions: ExternalAction[] = [];
let tab: Tab = 'today';
let importing = false;
let importOpen = false;
let capturing = false;
let draftStorageWarningShown = false;
let importResults: ImportReceipt[] = [];
let stateLoadError: string | null = null;
let reviewLoadError: string | null = null;
let externalActionsError: string | null = null;
let reviewPlanReady = false;
/** apply（写回）在途保护：双击/重复点击不能发出第二次 /api/review/apply */
let reviewApplyBusy = false;
let reviewFilter: ReviewFilter = 'all';
let reviewSelectedIds = new Set<string>();
let projectDetail: ProjectView | null = null;
let projectDetailLoading = false;
let projectDetailError: string | null = null;
let projectDetailName = '';
let projectListQuery = '';
let projectListFilter: ProjectListFilter = 'all';
interface ProjectReturnContext {
  tab: Tab;
  query: string;
  filter: ProjectListFilter;
  scrollY: number;
}
let projectReturnContext: ProjectReturnContext | null = null;
let projectFocusAfterRenderName: string | null = null;
let lastStateReadAt: string | null = null;
let lastReviewReadAt: string | null = null;
let reviewDrafts: Record<string, ReviewDraftFields> = {};
let latestStateRequest = 0;
let latestReviewRequest = 0;
let latestExternalActionsRequest = 0;
/** 项目详情读取序号：离开/切换详情后，过期响应不得复活旧详情 */
let latestProjectViewRequest = 0;

let remoteVersion: VersionPayload | null = null;
let lastServerInstance: string | null = null;
let versionCheckPromise: Promise<void> | null = null;
let restoredDraft: DraftSnapshot | null = null;
// null = 尚未按任何 workspace 载入过；服务端省略 workspace_id 时回退为 'unknown'，也必须载入一次。
let loadedAskWorkspace: string | null = null;

function persistEntityDraft<T>(entity: string, value: T): void {
  if (saveEntityDraft(entity, value, remoteVersion?.workspace_id)) return;
  if (!draftStorageWarningShown) {
    draftStorageWarningShown = true;
    toast('浏览器暂时无法保存草稿；请先完成当前编辑再切页', 'err');
  }
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
  if (ask) setAskDraft(ask.value);
  const saved = persistDraftSnapshot({
    schema: 1,
    saved_at: new Date().toISOString(),
    source_build: CLIENT_BUILD,
    tab,
    scroll_y: window.scrollY,
    capture_text: capture?.value ?? '',
    ask_draft: getAskDraft(),
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
  setAskDraft(draft.ask_draft);
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
    resetAskForWorkspace();
    reviewFilter = 'all';
    reviewSelectedIds.clear();
    // 旧工作区的预演/在途写回标记不得带入新工作区。
    reviewPlanReady = false;
    reviewApplyBusy = false;
    reviewDrafts = {};
    restoredDraft = null;
    importResults = [];
    importOpen = false;
    // 失效在途的详情读取，避免旧工作区响应把错误写进新工作区页面。
    latestProjectViewRequest += 1;
    projectDetail = null;
    projectDetailLoading = false;
    projectDetailError = null;
    projectDetailName = '';
    projectListQuery = '';
    projectListFilter = 'all';
    projectReturnContext = null;
    loadedAskWorkspace = workspaceId;
    reloadAskStore();
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
  applyTabChrome(tab);
  if (tab === 'today') {
    renderToday(viewElement('today') as HTMLElement);
  } else if (tab === 'review') {
    renderReview(viewElement('review') as HTMLElement);
  } else if (tab === 'projects') {
    renderProjects(viewElement('projects') as HTMLElement);
  } else if (tab === 'guide') {
    mountGuide(viewElement('guide') as HTMLElement);
  } else if (tab === 'settings') {
    void renderSettings(viewElement('settings') as HTMLElement);
  } else {
    renderAsk(viewElement('ask') as HTMLElement);
  }
  applyRestoredDraft();
}

function renderToday(view: HTMLElement): void {
  mountToday(view, state, {
    importing,
    importOpen,
    capturing,
    loadError: stateLoadError,
    importResults,
    readStatus: { lastSuccessfulAt: lastStateReadAt, error: stateLoadError },
    health: healthTone(),
    actions: {
      capture: async (text) => {
        if (capturing) return { ok: false };
        if (rejectOversizeText(text)) return { ok: false };
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
      importFiles: async (files) => {
        if (importing || files.length === 0) return;
        const supported = files.filter((file) => file.name.toLowerCase().endsWith('.md') || file.name.toLowerCase().endsWith('.txt'));
        const unsupported = files.filter((file) => !supported.includes(file));
        if (unsupported.length) {
          importResults = importResults.concat(unsupported.map((file) => ({
            fileName: file.name,
            bytes: file.size,
            status: 'error' as const,
            message: '仅支持 .md / .txt 逐字稿文件',
          })));
        }
        if (supported.length === 0) {
          renderToday(view);
          return;
        }
        if (supported.length > 1) toast('已加入 ' + supported.length + ' 个文件，将按顺序处理', 'info');
        importing = true;
        const start = importResults.length;
        importResults = importResults.concat(supported.map((file) => ({
          fileName: file.name,
          bytes: file.size,
          status: 'processing' as const,
          message: '排队中…',
        })));
        renderToday(view);
        for (const [offset, file] of supported.entries()) {
          const receiptIndex = start + offset;
          importResults[receiptIndex] = { ...importResults[receiptIndex], message: '正在处理…' };
          renderToday(view);
          const form = new FormData();
          form.append('file', file);
          try {
            const result = await mutation(() => api<{
              ok: boolean;
              status?: 'success' | 'partial' | 'failed';
              message: string;
              details?: string[];
              estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
            }>('/api/meetings/import', {
              method: 'POST', body: form,
            }));
            const status: ImportReceipt['status'] = result.status === 'partial'
              ? 'partial' : result.status === 'failed' || !result.ok ? 'error' : 'success';
            importResults[receiptIndex] = {
              fileName: file.name,
              bytes: file.size,
              status,
              message: result.message,
              details: result.details,
              estimate: result.estimate,
            };
            toast(result.message, status === 'success' ? 'ok' : status === 'partial' ? 'info' : 'err');
          } catch (err) {
            importResults[receiptIndex] = { fileName: file.name, bytes: file.size, status: 'error', message: String(err) };
            toast(String(err), 'err');
          }
          renderToday(view);
        }
        importing = false;
        renderToday(view);
        void refreshState();
      },
      toggleImport: (open) => { importOpen = open; },
      refresh: () => { void refreshState(); },
    },
  });
  if (projectFocusAfterRenderName && focusVisibleProjectLink(projectFocusAfterRenderName)) {
    projectFocusAfterRenderName = null;
  }
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
    { filter: reviewFilter, selectedIds: reviewSelectedIds },
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
  const filter = view.querySelector<HTMLSelectElement>('#review-status-filter');
  filter?.addEventListener('change', () => {
    const next = filter.value;
    if (next !== 'all' && next !== 'pending' && next !== 'approved' && next !== 'rejected') return;
    reviewFilter = next;
    reviewSelectedIds.clear();
    renderReview(view);
    view.querySelector<HTMLSelectElement>('#review-status-filter')?.focus();
  });
  view.querySelectorAll<HTMLInputElement>('[data-review-select]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      const id = checkbox.dataset.reviewSelect ?? '';
      if (!id) return;
      if (checkbox.checked) reviewSelectedIds.add(id);
      else reviewSelectedIds.delete(id);
      renderReview(view);
      const next = Array.from(view.querySelectorAll<HTMLInputElement>('[data-review-select]'))
        .find((candidate) => candidate.dataset.reviewSelect === id);
      next?.focus();
    });
  });
}


function renderProjects(view: HTMLElement): void {
  if (!state) {
    view.innerHTML = '<div class="loading">加载中…</div>';
    return;
  }
  if (projectDetailLoading) {
    view.innerHTML = '<div class="section-head"><button class="ghost" data-action="project-detail-back">← 返回项目</button></div>' +
      '<div class="loading">正在读取「' + esc(projectDetailName) + '」详情…</div>';
    return;
  }
  if (projectDetail) {
    view.innerHTML = projectDetailHtml(
      projectDetail,
      projectReturnContext?.tab === 'today' ? '返回今日' : '返回项目列表',
    );
    bindProjectDetail(view, projectDetail);
    return;
  }
  if (projectDetailError) {
    view.innerHTML = '<div class="empty load-error"><p>项目详情读取失败：' + esc(projectDetailError) + '</p>' +
      '<button class="ghost" data-action="project-detail-back">返回项目</button></div>';
    return;
  }
  const projects = state.projects;
  const today = state.day;
  const query = projectListQuery;
  const total = projects.length;
  const onHome = projects.filter((p) => p.registered && p.status === 'active').length;
  const fresh = projects.filter((p) => !p.registered).length;
  const archived = projects.filter((p) => p.status === 'archived').length;
  view.innerHTML =
    '<div class="section-head"><h3 class="section-title">全部项目</h3>' +
    '<span class="hint">共 ' + total + ' · 在工作台 ' + onHome + ' · 新 ' + fresh + ' · 已归档 ' + archived + '</span></div>' +
    '<div class="project-toolbar">' +
    '<input id="project-search" type="search" placeholder="搜索项目名…" value="' + esc(query) + '">' +
    '<label class="project-filter"><span class="hint">显示</span><select id="project-status-filter">' +
    '<option value="all"' + (projectListFilter === 'all' ? ' selected' : '') + '>全部项目</option>' +
    '<option value="active"' + (projectListFilter === 'active' ? ' selected' : '') + '>在工作台</option>' +
    '<option value="new"' + (projectListFilter === 'new' ? ' selected' : '') + '>新文件夹</option>' +
    '<option value="archived"' + (projectListFilter === 'archived' ? ' selected' : '') + '>已归档</option>' +
    '</select></label>' +
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
  listEl.innerHTML = projectsListHtml(query, projects, today, true, projectListFilter);
  if (projectFocusAfterRenderName && focusVisibleProjectLink(projectFocusAfterRenderName)) {
    projectFocusAfterRenderName = null;
  }
  const search = view.querySelector<HTMLInputElement>('#project-search');
  search?.addEventListener('input', () => {
    projectListQuery = search.value;
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(projectListQuery, projects, today, true, projectListFilter);
  });
  view.querySelector<HTMLSelectElement>('#project-status-filter')?.addEventListener('change', (event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (value !== 'all' && value !== 'active' && value !== 'new' && value !== 'archived') return;
    projectListFilter = value;
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(projectListQuery, projects, today, true, projectListFilter);
  });
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

const FEISHU_STATE_KEY = 'wb.feishu.state';

/**
 * 飞书授权回跳后的结果提示。
 *
 * 分发包内置了应用凭据，同事本机没有可改的配置：授权失败时必须把「找谁、做什么」
 * 显示出来（最常见的失败是管理员还没把他加入应用「可用范围」），而不是静默回到设置页。
 */
async function reportFeishuCallbackResult(view: HTMLElement): Promise<void> {
  const outcome = new URLSearchParams(window.location.search).get('feishu');
  if (outcome !== 'failed' && outcome !== 'connected') return;
  const target = view.querySelector('#feishu-result');
  const state = sessionStorage.getItem(FEISHU_STATE_KEY) ?? '';
  sessionStorage.removeItem(FEISHU_STATE_KEY);
  let message: string;
  let kind: 'ok' | 'err';
  if (outcome === 'connected') {
    message = '飞书已连接 ✓';
    kind = 'ok';
  } else {
    message = '飞书授权未完成，请重新点击「授权飞书」';
    kind = 'err';
    if (state) {
      try {
        const status = await api<{ status: string; reason?: string | null }>(
          '/api/settings/feishu/status?state=' + encodeURIComponent(state),
        );
        if (status.reason) message = status.reason;
      } catch (_) {
        // 状态已过期：退回兜底文案，不阻断设置页
      }
    }
  }
  if (target) {
    const box = document.createElement('p');
    box.className = kind === 'ok' ? 'hint' : 'error';
    box.textContent = message;
    target.replaceChildren(box);
  }
  toast(message, kind);
  // 清掉查询串：刷新或切换页签时不重复提示
  window.history.replaceState(null, '', window.location.pathname + window.location.hash);
}

async function renderSettings(view: HTMLElement): Promise<void> {
  await renderSettingsFeature(view, {
    api,
    mutation,
    toast,
    refresh: () => { void renderSettings(view); },
  });
  await reportFeishuCallbackResult(view);
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
  disposeApiClient();
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

function selectedReviewEntries(): ReviewEntry[] {
  const byId = new Map((review?.groups ?? []).flatMap((group) => group.entries).map((entry) => [entry.candidate_id, entry]));
  return Array.from(reviewSelectedIds)
    .map((id) => byId.get(id))
    .filter((entry): entry is ReviewEntry => Boolean(entry && entry.decision === 'pending'));
}

function batchSelectedReview(decision: 'approved' | 'rejected'): void {
  const picked = selectedReviewEntries();
  const selected = picked.filter((entry) =>
    decision === 'rejected' || (entry.actionable && !!entry.route),
  );
  if (decision === 'approved' && selected.length === 0) {
    toast('选中的候选缺少依据或落点，未批准', 'info');
    return;
  }
  const blocked = decision === 'approved' ? picked.length - selected.length : 0;
  const note = blocked > 0 ? blocked + ' 条因依据或落点不完整未纳入批准' : '';
  reviewSelectedIds.clear();
  void batchDecide(selected.map((entry) => entry.candidate_id), decision, note);
}

// ---------- 全局事件（审批页操作） ----------

document.addEventListener('click', (ev) => {
  const btn = (ev.target as HTMLElement).closest<HTMLElement>('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action ?? '';
  btn.focus();
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
  if (action === 'source-open') {
    void openSource(btn.dataset.sourceId ?? '');
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
  if (action === 'sync-refresh') {
    void refreshSyncBanner();
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
  if (action === 'project-detail-back') {
    backFromProjectDetail();
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
    void api<{ authorize_url: string; state?: string }>('/api/settings/feishu/authorize-url', { method: 'POST' })
      .then((result) => {
        // 记住 state，才能在回跳失败时取回具体原因（见 reportFeishuCallbackResult）
        if (result.state) sessionStorage.setItem(FEISHU_STATE_KEY, result.state);
        window.location.href = result.authorize_url;
      })
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
  if (action === 'review-select-all') {
    const selectable = (review?.groups ?? [])
      .flatMap((group) => group.entries)
      .filter((entry) => entry.decision === 'pending' && (reviewFilter === 'all' || reviewFilter === 'pending'))
      .map((entry) => entry.candidate_id);
    const allSelected = selectable.length > 0 && selectable.every((id) => reviewSelectedIds.has(id));
    selectable.forEach((id) => {
      if (allSelected) reviewSelectedIds.delete(id);
      else reviewSelectedIds.add(id);
    });
    renderReview(document.getElementById('view-review') as HTMLElement);
    return;
  }
  if (action === 'review-batch') {
    const decision = btn.dataset.decision;
    if (decision === 'approved' || decision === 'rejected') batchSelectedReview(decision);
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
    askNewThread();
    return;
  }
  if (action === 'ask-open') {
    askOpenThread(btn.dataset.thread ?? null);
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
  // 决定变化后旧预演失效：必须重新「检查并写回」才能应用。
  reviewPlanReady = false;
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
  // 批量决定同样使旧预演失效。
  reviewPlanReady = false;
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

function bindProjectDetail(container: HTMLElement, current: ProjectView): void {
  container.querySelector('[data-action="pv-refresh"]')?.addEventListener('click', () => { void showProjectView(current.name); });
  container.querySelector('[data-action="pv-log"]')?.addEventListener('click', () => openLogModal(current.name));
  container.querySelector('[data-action="pv-artifact"]')?.addEventListener('click', () => openArtifactModal(current.name));
  const renameBtn = container.querySelector<HTMLButtonElement>('#pv-rename');
  renameBtn?.addEventListener('click', () => {
    const titleBox = container.querySelector('#pv-title');
    if (!titleBox) return;
    const cur = (current.title && current.title.trim()) || current.name;
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
    const reload = (): void => { void showProjectView(current.name); };
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
          body: JSON.stringify({ name: current.name, title: value }),
        });
        toast(r.message, r.ok ? 'ok' : 'err');
        if (r.ok) {
          reload();
          void refreshState();
        }
      }).catch((err: unknown) => toast(String(err), 'err'));
    };
    save.addEventListener('click', commit);
    cancel.addEventListener('click', reload);
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        commit();
      } else if (ev.key === 'Escape') {
        reload();
      }
    });
  });
}

async function showProjectView(name: string): Promise<void> {
  if (!name) return;
  if (!projectReturnContext) {
    projectReturnContext = {
      tab,
      query: projectListQuery,
      filter: projectListFilter,
      scrollY: window.scrollY,
    };
  }
  const requestId = ++latestProjectViewRequest;
  projectDetailName = name;
  projectDetail = null;
  projectDetailError = null;
  projectDetailLoading = true;
  tab = 'projects';
  render();
  window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  try {
    const next = await api<ProjectView>('/api/projects/view?name=' + encodeURIComponent(name));
    if (requestId !== latestProjectViewRequest) return;
    if (!next.ok) {
      projectDetailError = next.message ?? '打开失败';
      return;
    }
    projectDetail = next;
  } catch (err) {
    if (requestId !== latestProjectViewRequest || isStaleWorkspaceResponse(err)) return;
    projectDetailError = String(err);
  } finally {
    if (requestId === latestProjectViewRequest) {
      projectDetailLoading = false;
      if (tab === 'projects') {
        render();
        document.querySelector<HTMLElement>('[data-action="project-detail-back"]')?.focus();
      }
    }
  }
}

function backFromProjectDetail(): void {
  // 失效在途详情读取：返回/切换后，过期响应不得把详情重新推回页面。
  latestProjectViewRequest += 1;
  const context = projectReturnContext;
  const name = projectDetailName;
  projectFocusAfterRenderName = name || null;
  projectDetail = null;
  projectDetailError = null;
  projectDetailLoading = false;
  projectDetailName = '';
  projectReturnContext = null;
  tab = context?.tab ?? 'projects';
  projectListQuery = context?.query ?? projectListQuery;
  projectListFilter = context?.filter ?? projectListFilter;
  render();
  window.setTimeout(() => {
    window.scrollTo({ top: context?.scrollY ?? 0, behavior: 'instant' as ScrollBehavior });
    if (projectFocusAfterRenderName && focusVisibleProjectLink(projectFocusAfterRenderName)) {
      projectFocusAfterRenderName = null;
    }
  }, 0);
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
let rowEditSubmitting = false;

async function submitRowEdit(kind: 'task' | 'meeting', id: string): Promise<void> {
  if (rowEditSubmitting) return;
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
  // 双击「保存」不能对飞书本体发出两次 PATCH。
  rowEditSubmitting = true;
  const submitButton = document.querySelector<HTMLButtonElement>('#row-edit-form button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
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
  } finally {
    rowEditSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}

async function planApply(exec: boolean): Promise<void> {
  if (exec && reviewApplyBusy) return;
  if (exec && !reviewPlanReady) {
    toast('请先查看最新预演，再确认写回', 'info');
    return;
  }
  if (exec) {
    reviewApplyBusy = true;
    document.querySelectorAll<HTMLButtonElement>('#modal [data-action="apply"]').forEach((button) => {
      button.disabled = true;
    });
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
  } finally {
    if (exec) reviewApplyBusy = false;
  }
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
  const requestId = ++latestExternalActionsRequest;
  try {
    const data = await api<{ ok: boolean; actions?: ExternalAction[] }>('/api/external-actions');
    if (requestId !== latestExternalActionsRequest) return;
    if (data.ok) {
      externalActions = data.actions ?? [];
      externalActionsError = null;
    } else {
      externalActionsError = '服务端没有返回可用状态';
    }
    if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
  } catch (err) {
    // 外部状态查询失败不阻断审批页本身，但必须在页面上可见。
    if (isStaleWorkspaceResponse(err) || requestId !== latestExternalActionsRequest) return;
    externalActionsError = String(err);
    if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
  }
}

async function refreshAll(): Promise<{ state: boolean; review: boolean }> {
  const [stateOk, reviewOk] = await Promise.all([refreshState(), refreshReview()]);
  return { state: stateOk, review: reviewOk };
}

// ---------- 启动（由 main.ts composition root 调用） ----------

export function mountLegacyWorkbench(): void {
  mountShell({
    onSelectTab: (next) => { tab = next; render(); },
    onRefresh: () => {
      void Promise.all([refreshAll(), refreshSyncBanner()]).then(([result]) => {
        toast(result.state && result.review ? '已刷新' : '刷新未完成：保留了可用的旧数据', result.state && result.review ? 'ok' : 'err');
      });
    },
    onCheckUpdates: () => {
      if (sendNativeMessage({ type: 'checkForUpdates' })) {
        toast('正在检查更新', 'info');
      } else {
        toast('更新检查仅支持已安装的 macOS App', 'info');
      }
    },
    onUndo: () => { void openUndoModal(); },
    onQuit: () => {
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
    },
  });
  mountUndo({ refreshAll });
  mountThreads({
    projects: () => state?.projects ?? [],
    workspaceId: () => remoteVersion?.workspace_id,
    persistEntityDraft,
  });
  mountSyncBanner({
    refreshState,
    workspaceId: () => remoteVersion?.workspace_id,
    persistEntityDraft,
  });
  mountAsk({
    projects: () => state?.projects ?? [],
    workspaceId: () => remoteVersion?.workspace_id,
    persistEntityDraft,
  });
  // 连接恢复后重查一次版本（原 apiClient 的 onSuccess 回调，§4.5）。
  onConnectionRestored(() => { void checkVersion('connection-restored'); });
  setMutationIdleHandler(async (targetBuild) => {
    saveCurrentDraftSnapshot();
    reloadToBuild(targetBuild);
  });
  window.addEventListener('focus', () => { void checkVersion('focus'); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    void checkVersion('visible');
    void refreshSyncBanner();
  });

  async function startApp(): Promise<void> {
    await checkVersion('startup');
    restoredDraft = loadDraftSnapshot(Date.now(), remoteVersion?.workspace_id);
    await refreshAll();
    if (restoredDraft) render();
  }

  // 60 秒自动刷新只发生在可见页；隐藏页暂停读取，回到前台时由 visibilitychange 立即补一次。
  void startApp();
  void refreshSyncBanner();
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void checkVersion('interval');
  }, 60000);
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void refreshSyncBanner();
  }, 60000);
}
