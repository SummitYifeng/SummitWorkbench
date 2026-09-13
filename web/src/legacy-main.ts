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
  CLIENT_BUILD,
  reloadToBuild,
  setVersionStatus,
  shouldPreventReload,
  validateVersionPayload,
  type VersionPayload,
} from './lifecycle/version';
import { notifyClientReady, sendNativeMessage } from './lifecycle/native-bridge';
import { esc } from './md';
import { type BriefData } from './brief-card';
import type { ProjectState } from './features/projects';
import type { ExternalAction, ReviewPayload } from './features/review';
import {
  applyTabChrome,
  mountShell,
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
  autoSyncIfIdle,
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
import {
  completeTask,
  createTodayActions,
  mountToday,
  mountTodayActions,
  openRowEditModal,
  plusMinutesInput,
  resetTodayForWorkspace,
  runBrief,
  todayUi,
  tsToDatetimeLocal,
  type TodayActions,
} from './features/today';

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
let draftStorageWarningShown = false;
let todayActions: TodayActions | null = null;
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
  setVersionStatus('checking', remoteVersion);
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
    resetTodayForWorkspace();
    resetProjectsForWorkspace();
    loadedAskWorkspace = workspaceId;
    reloadAskStore();
  }
  if (remote.frontend_build === CLIENT_BUILD) {
    setVersionStatus('synced', remoteVersion);
    notifyClientReady(CLIENT_BUILD, remote.server_instance);
    if (instanceChanged) await refreshAll();
    return;
  }

  saveCurrentDraftSnapshot();
  if (shouldPreventReload(window.sessionStorage, remote.frontend_build, Date.now())) {
    setVersionStatus('failed', remoteVersion);
    return;
  }
  if (isMutationInFlight()) {
    setVersionStatus('update-pending', remoteVersion);
    deferReloadUntilMutationsComplete(remote.frontend_build);
    return;
  }
  reloadToBuild(remote.frontend_build, remote);
}

function checkVersion(reason: string): Promise<void> {
  if (versionCheckPromise) return versionCheckPromise;
  versionCheckPromise = doCheckVersion(reason)
    .catch(() => setVersionStatus('reconnecting', remoteVersion))
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
  todayActions ??= createTodayActions(view);
  mountToday(view, state, {
    importing: todayUi.importing,
    importOpen: todayUi.importOpen,
    capturing: todayUi.capturing,
    loadError: stateLoadError,
    importResults: todayUi.importResults,
    readStatus: { lastSuccessfulAt: lastStateReadAt, error: stateLoadError },
    health: healthTone(),
    actions: todayActions,
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
    reloadToBuild(remoteVersion.frontend_build, remoteVersion);
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
    onSync: () => { void retrySync(); },
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
  mountTodayActions({
    api,
    mutation,
    toast,
    refreshState,
    renderToday,
  });
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
    reloadToBuild(targetBuild, remoteVersion);
  });
  window.addEventListener('focus', () => { void checkVersion('focus'); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    void checkVersion('visible');
    // D6：回到前台时先读状态，若仍是 ready（干净、无保护态）就真正拉一次远端。
    void autoSyncIfIdle();
  });

  async function startApp(): Promise<void> {
    await checkVersion('startup');
    restoredDraft = loadDraftSnapshot(Date.now(), remoteVersion?.workspace_id);
    await refreshAll();
    if (restoredDraft) render();
  }

  // 60 秒自动刷新只发生在可见页；隐藏页暂停读取，回到前台时由 visibilitychange 立即补一次。
  void startApp();
  // D6：启动后也拉一次——只读为主的设备打开即是新的。
  void autoSyncIfIdle();
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void checkVersion('interval');
  }, 60000);
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void autoSyncIfIdle();
  }, 60000);
}
