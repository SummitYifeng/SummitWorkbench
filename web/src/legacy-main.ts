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
import type { ProjectState } from './features/projects';
import type { ExternalAction, ReviewPayload } from './features/review';
import {
  applyTabChrome,
  closeModal,
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
import {
  mountThreads,
  openArtifactModal,
  openLogModal,
} from './features/threads';
import {
  archiveProject,
  backFromProjectDetail,
  mountProjects,
  renderProjects,
  resetProjectsForWorkspace,
  revealQueuedProjectFocus,
  setProjectState,
  showProjectView,
} from './features/projects';
import {
  batchSelectedReview,
  confirmExternalCreated,
  confirmExternalNotFound,
  decide,
  decideGroup,
  mountReview,
  planApply,
  reconcileExternalAction,
  rejectExpired,
  renderReviewView,
  resetReviewForWorkspace,
  retryExternalAction,
  selectAllReview,
} from './features/review';
import {
  applyGitRemoteNormalization,
  authorizeFeishu,
  copyAutomationSummary,
  migrateWorkspace,
  mountSettings,
  previewGitRemoteNormalization,
  removeProfile,
  renderSettingsView,
  reopenOnboarding,
  rollbackGitRemoteNormalization,
  runAcceptancePreflight,
  runAutomationJob,
  runSettingsDoctor,
  runSettingsDoctorOnline,
  switchProfile,
} from './features/settings';
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
let lastStateReadAt: string | null = null;
let lastReviewReadAt: string | null = null;
let reviewDrafts: Record<string, ReviewDraftFields> = {};
let latestStateRequest = 0;
let latestReviewRequest = 0;
let latestExternalActionsRequest = 0;

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
    resetReviewForWorkspace();
    reviewDrafts = {};
    restoredDraft = null;
    importResults = [];
    importOpen = false;
    resetProjectsForWorkspace();
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
    renderReviewView();
  } else if (tab === 'projects') {
    renderProjects(viewElement('projects') as HTMLElement, state);
  } else if (tab === 'guide') {
    mountGuide(viewElement('guide') as HTMLElement);
  } else if (tab === 'settings') {
    void renderSettingsView(viewElement('settings') as HTMLElement);
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
  revealQueuedProjectFocus();
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
    removeProfile(btn.dataset.workspace ?? '');
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
    runSettingsDoctorOnline();
    return;
  }
  if (action === 'reopen-onboarding') {
    reopenOnboarding();
    return;
  }
  if (action === 'feishu-reauth') {
    authorizeFeishu();
    return;
  }
  if (action === 'project-activate') {
    void setProjectState('activate', btn.dataset.name ?? '');
    return;
  }
  if (action === 'project-archive') {
    archiveProject(btn.dataset.name ?? '', !!btn.dataset.confirm);
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
    selectAllReview();
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
    confirmExternalCreated(btn.dataset.operation ?? '');
    return;
  }
  if (action === 'external-confirm-not-found') {
    confirmExternalNotFound(btn.dataset.operation ?? '');
    return;
  }
  if (action === 'external-retry') {
    retryExternalAction(btn.dataset.operation ?? '');
    return;
  }
  if (action === 'decide') {
    const card = btn.closest<HTMLElement>('.entry');
    if (!card) return;
    void decide(card.dataset.id ?? '', btn.dataset.decision ?? 'pending');
    return;
  }
  if (action === 'group-decide') {
    decideGroup(Number(btn.dataset.group ?? '-1'), btn.dataset.decision ?? 'pending');
    return;
  }
  if (action === 'reject-expired') {
    rejectExpired();
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
    renderProjects(document.getElementById('view-projects') as HTMLElement, state);
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
    if (tab === 'review') renderReviewView();
    return false;
  }
  await refreshExternalActions();
  if (tab === 'review') renderReviewView();
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
    if (tab === 'review') renderReviewView();
  } catch (err) {
    // 外部状态查询失败不阻断审批页本身，但必须在页面上可见。
    if (isStaleWorkspaceResponse(err) || requestId !== latestExternalActionsRequest) return;
    externalActionsError = String(err);
    if (tab === 'review') renderReviewView();
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
  mountSettings({
    api,
    mutation,
    toast,
    refresh: () => { void renderSettingsView(viewElement('settings') as HTMLElement); },
    workspaceId: () => remoteVersion?.workspace_id,
    clearDraftSnapshot,
    disposeApiClient,
    disposeWorkspaceStore: () => { workspaceStore.dispose(); },
  });
  mountReview({
    assemble: () => ({
      review,
      loadError: reviewLoadError,
      lastReadAt: lastReviewReadAt,
      pendingReview: state?.status.pending_review ?? 0,
      day: state?.day ?? '',
      projects: state?.projects ?? [],
      externalActions,
      externalActionsError,
      drafts: reviewDrafts,
    }),
    setReview: (payload) => { review = payload; },
    setExternalActions: (actions) => { externalActions = actions; },
    saveDraftSnapshot: saveCurrentDraftSnapshot,
    render: () => render(),
    refreshState,
    refreshReview,
  });
  mountProjects({
    currentTab: () => tab,
    setTab: (next) => { tab = next; },
    render: () => render(),
    refreshAll,
    refreshState,
  });
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
