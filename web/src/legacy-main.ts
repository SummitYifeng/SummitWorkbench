import './style.css';

import {
  api,
  disposeApiClient,
  isStaleWorkspaceResponse,
  onConnectionRestored,
} from './api/request';
import { workspaceStore } from './core/workspace-store';
import { formatBusinessTime } from './core/time';
import { mutation, deferReloadUntilMutationsComplete, isMutationInFlight, setMutationIdleHandler } from './lifecycle/connection';
import {
  clearEntityDraft,
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
import { publishOperationFeedback, unresolvedOperationIds } from './features/shell/operation-feedback';
import { publishDraftStatus } from './features/shell/operation-feedback';
import { clearServerDraft } from './lifecycle/server-drafts';
import { type BriefData } from './brief-card';
import { createDiagnosticsActions } from './features/diagnostics';
import type { ProjectState } from './features/projects';
import type { ExternalAction, ReviewPayload } from './features/review';
import {
  applyTabChrome,
  mountShell,
  openModal,
  registerModalCloseHook,
  requestModalClose,
  toast,
  viewElement,
} from './features/shell';
import { invalidateSourceReads, openSource } from './features/source-reader';
import {
  mountThreads,
  openArtifactModal,
  openLogModal,
} from './features/threads';
import {
  archiveProject,
  backFromProjectDetail,
  mountProjects,
  projectDisplayName,
  renderProjects,
  resetProjectsForWorkspace,
  revealQueuedProjectFocus,
  setProjectState,
  showProjectView,
  submitProjectCreate,
} from './features/projects';
import {
  approveContent,
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
  submitReviewEdit,
  updatePendingMeetingDate,
} from './features/review';
import {
  authorizeFeishu,
  copyAutomationSummary,
  mountSettings,
  removeProfile,
  renderSettingsView,
  reopenOnboarding,
  runSettingsDoctor,
  runSettingsDoctorOnline,
  switchProfile,
} from './features/settings';
import {
  completeTask,
  createTodayActions,
  mountToday,
  mountTodayActions,
  openInboxPromoteModal,
  openJournalLogModal,
  openJournalThoughtModal,
  openRowEditModal,
  plusMinutesInput,
  resetTodayForWorkspace,
  runBrief,
  retryImport,
  todayUi,
  requestInboxSuggestion,
  tsToDatetimeLocal,
  type InboxItem,
  type ProjectChoice,
  type TodayActions,
} from './features/today';

type Tab = 'today' | 'review' | 'projects' | 'settings';

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

let state: StatePayload | null = null;
let review: ReviewPayload | null = null;
let externalActions: ExternalAction[] = [];
let tab: Tab = 'today';
let draftStorageWarningShown = false;
let todayActions: TodayActions | null = null;
let stateLoadError: string | null = null;
// 收件箱待处理条目：跟着 `refreshState()` 一起读（`GET /api/inbox`，**纯读、不调模型**），
// 渲染时直接用缓存，避免列表渲染触发任何模型调用（成本约定，第九阶段）。
let inboxItems: InboxItem[] = [];
let inboxLoadError: string | null = null;
let reviewLoadError: string | null = null;
let externalActionsError: string | null = null;
let lastStateReadAt: string | null = null;
let lastReviewReadAt: string | null = null;
let reviewDrafts: Record<string, ReviewDraftFields> = {};
let latestStateRequest = 0;
let latestReviewRequest = 0;
let latestExternalActionsRequest = 0;

let remoteVersion: VersionPayload | null = null;
const diagnostics = createDiagnosticsActions({
  api,
  fetch,
  toast,
  clientBuild: CLIENT_BUILD,
  getVersion: () => remoteVersion,
  escapeHtml: esc,
});
let lastServerInstance: string | null = null;
let versionCheckPromise: Promise<void> | null = null;
let restoredDraft: DraftSnapshot | null = null;
// null = 尚未按任何 workspace 载入过；服务端省略 workspace_id 时回退为 'unknown'，也必须载入一次。
let loadedWorkspaceId: string | null = null;
interface BackendDraft {
  type: string;
  id: string;
  value: Record<string, unknown>;
  edited_at: string;
}
const backendDrafts = new Map<string, BackendDraft>();
const draftTimers = new Map<string, number>();
const draftValues = new Map<string, { type: string; id: string; value: Record<string, unknown> }>();
const draftWrites = new Map<string, Promise<void>>();

function backendDraftKey(type: string, id: string): string {
  return type + ':' + id;
}

function scheduleBackendDraft(
  type: string,
  id: string,
  value: Record<string, unknown>,
  delayMs = 500,
): void {
  if (!remoteVersion?.workspace_id || !id) return;
  const key = backendDraftKey(type, id);
  draftValues.set(key, { type, id, value });
  const oldTimer = draftTimers.get(key);
  if (oldTimer !== undefined) window.clearTimeout(oldTimer);
  publishDraftStatus('正在保存草稿…');
  draftTimers.set(key, window.setTimeout(() => {
    draftTimers.delete(key);
    const current = draftValues.get(key);
    if (!current) return;
    const previous = draftWrites.get(key) ?? Promise.resolve();
    const write = previous.catch(() => undefined).then(async () => {
      const url = '/api/drafts/' + encodeURIComponent(backendDraftKey(type, id));
      // A successful submit can clear a draft while its debounce timer is waiting behind an
      // earlier write. Do not let that stale value start a PUT after the clear event.
      if (draftValues.get(key) !== current) return;
      const result = await api<{ ok: boolean; draft?: BackendDraft; message?: string }>(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(current),
      });
      if (!result.ok || !result.draft) throw new Error(result.message ?? '草稿暂未保存');
      // If the clear raced with this in-flight PUT, remove its late server-side write. If a newer
      // value exists, its serialized PUT will replace this one, so deleting here would lose it.
      if (draftValues.get(key) !== current) {
        backendDrafts.delete(key);
        if (!draftValues.has(key)) await api<{ ok: boolean }>(url, { method: 'DELETE' });
        return;
      }
      backendDrafts.set(key, result.draft);
      const modal = document.getElementById('modal');
      if (draftValues.get(key) === current && modal?.dataset.draftEntity === type + ':' + id) {
        modal.dataset.draftDirty = '0';
      }
      publishDraftStatus('草稿已保存在本机');
    }).catch(() => {
      publishDraftStatus('草稿暂未保存在本机；编辑内容仍在当前页面，请复制后再离开。', true);
    });
    draftWrites.set(key, write);
    void write.finally(() => {
      if (draftWrites.get(key) === write) draftWrites.delete(key);
    });
  }, delayMs));
}

function restoreModalDraft(event: Event): void {
  const modal = (event as CustomEvent<HTMLElement>).detail;
  const form = modal?.querySelector<HTMLFormElement>('form[data-draft-type][data-draft-id]');
  if (!form) return;
  const type = form.dataset.draftType ?? '';
  const id = form.dataset.draftId ?? '';
  modal.dataset.draftEntity = type + ':' + id;
  if (!modal.dataset.draftDirty) modal.dataset.draftDirty = '0';
  const draft = backendDrafts.get(backendDraftKey(type, id));
  if (!draft || !window.confirm('发现一份保存在本机的草稿（' + draft.edited_at + '）。要恢复到当前表单吗？')) return;
  const ids: Record<string, Record<string, string>> = {
    'journal-log': { did: 'journal-did', remaining: 'journal-remaining', reflection: 'journal-reflection', blockers: 'journal-blockers' },
    'journal-thought': { problem: 'journal-problem', thinking: 'journal-thinking', conclusion: 'journal-conclusion', summary: 'journal-summary' },
    'inbox-promote': { project: 'inbox-project', block: 'inbox-block', due_date: 'inbox-due', start_date: 'inbox-start', problem: 'inbox-problem', thinking: 'inbox-thinking', conclusion: 'inbox-conclusion', summary: 'inbox-summary' },
    'task-edit': { summary: 'row-edit-summary', due_date: 'row-edit-due' },
    'meeting-edit': { summary: 'row-edit-summary', start_at: 'row-edit-start', end_at: 'row-edit-end' },
    'thread-log': { text: 'log-text' },
    artifact: { project: 'artifact-project', title: 'artifact-title', text: 'artifact-text' },
  };
  for (const [field, value] of Object.entries(draft.value)) {
    if (field === 'target') {
      const radio = form.querySelector<HTMLInputElement>('input[name="inbox-target"][value="' + String(value) + '"]');
      if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change', { bubbles: true })); }
      continue;
    }
    if (field === 'projects' && Array.isArray(value)) {
      const select = form.querySelector<HTMLSelectElement>('select[multiple]');
      if (select) Array.from(select.options).forEach((option) => { option.selected = value.includes(option.value); });
      form.querySelectorAll<HTMLInputElement>('input[name="log-proj"]').forEach((input) => {
        input.checked = value.includes(input.value);
      });
      form.querySelectorAll<HTMLInputElement>('input[name="journal-project"]').forEach((input) => {
        input.checked = value.includes(input.value);
      });
      continue;
    }
    const elementId = ids[type]?.[field] ?? field;
    const input = document.getElementById(elementId);
    if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement || input instanceof HTMLSelectElement) {
      input.value = typeof value === 'string' ? value : String(value);
    }
  }
  modal.dataset.draftDirty = '0';
  publishDraftStatus('已恢复本机草稿；内容尚未提交。');
}

function openDraftManager(): void {
  const labels: Record<string, string> = {
    'quick-note': '快速记录', 'journal-log': '工作日志', 'journal-thought': '工作思考',
    'inbox-promote': '收件箱提升', 'review-edit': '审批修改', 'project-edit': '项目修改',
    'task-edit': '任务修改', 'meeting-edit': '会议修改', 'thread-log': '项目记录', artifact: '导入文档',
  };
  const entries = [...backendDrafts.values()];
  const body = entries.length ? entries.map((draft, index) => {
    const key = backendDraftKey(draft.type, draft.id);
    return '<details class="draft-manager-item"><summary>' + esc(labels[draft.type] ?? '草稿') +
      ' · ' + esc(draft.id) + ' · ' + esc(draft.edited_at) + '</summary>' +
      '<pre class="draft-manager-content">' + esc(JSON.stringify(draft.value, null, 2)) + '</pre>' +
      '<div class="row"><button type="button" class="ghost" data-action="draft-copy" data-draft-index="' + index + '">复制内容</button>' +
      '<button type="button" class="ghost" data-action="draft-delete" data-draft-index="' + index + '">删除草稿</button></div>' +
      '<span class="visually-hidden" data-draft-key="' + esc(key) + '"></span></details>';
  }).join('') : '<p>当前工作区没有未完成草稿。</p>';
  openModal('<h3>本机草稿</h3><p class="hint">草稿仅保存在这台 Mac，编辑后七天到期。恢复不会自动提交。</p>' + body);
  document.querySelectorAll<HTMLButtonElement>('[data-action="draft-copy"]').forEach((button) => {
    button.addEventListener('click', () => {
      const draft = entries[Number(button.dataset.draftIndex)];
      if (!draft) return;
      void navigator.clipboard.writeText(JSON.stringify(draft.value, null, 2))
        .then(() => toast('草稿内容已复制', 'ok'))
        .catch(() => toast('无法访问剪贴板；可直接选择并复制草稿内容。', 'err'));
    });
  });
  document.querySelectorAll<HTMLButtonElement>('[data-action="draft-delete"]').forEach((button) => {
    button.addEventListener('click', () => {
      const draft = entries[Number(button.dataset.draftIndex)];
      if (!draft || !window.confirm('确定删除这份本机草稿？')) return;
      void clearServerDraft(api, draft.type, draft.id).then(() => {
        openDraftManager();
        publishDraftStatus('已删除所选本机草稿');
      }).catch(() => publishDraftStatus('草稿暂未删除；请恢复连接后重试。', true));
    });
  });
}

document.addEventListener('swb:modal-opened', restoreModalDraft);
document.addEventListener('swb:modal-close-choice', (event) => {
  const detail = (event as CustomEvent<{
    choice: string;
    modal: HTMLElement;
    finish: (close: boolean, message?: string) => void;
  }>).detail;
  if (!detail) return;
  const { choice, modal, finish } = detail;
  const entity = modal.dataset.draftEntity ?? '';
  const separator = entity.indexOf(':');
  if (choice === 'discard') {
    const perform = async (): Promise<void> => {
      if (separator >= 0) {
        const type = entity.slice(0, separator);
        const id = entity.slice(separator + 1);
        await clearServerDraft(api, type, id);
        clearEntityDraft(entity, remoteVersion?.workspace_id);
      }
      modal.dataset.draftDirty = '0';
      finish(true);
    };
    void perform().catch(() => finish(false, '草稿暂未删除；请恢复连接后重试。'));
    return;
  }
  if (choice !== 'keep') return;
  const form = modal.querySelector<HTMLFormElement>('form[data-draft-type][data-draft-id]');
  const input = form?.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>('input:not([type="file"]), textarea, select');
  if (input && typeof input.dispatchEvent === 'function' && typeof Event !== 'undefined') {
    modal.dataset.draftDirty = '1';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
  if (separator < 0) {
    finish(false, '这类内容暂不支持本机草稿；请复制后再关闭。');
    return;
  }
  const started = Date.now();
  const confirmSaved = (): void => {
    if (modal.dataset.draftDirty !== '1') {
      finish(true);
      return;
    }
    if (Date.now() - started > 15_000) {
      finish(false, '草稿尚未确认保存；请保持编辑页打开并检查连接。');
      return;
    }
    window.setTimeout(confirmSaved, 100);
  };
  window.setTimeout(confirmSaved, 100);
});
document.addEventListener('swb:draft-cleared', (event) => {
  const detail = (event as CustomEvent<{ type: string; id: string }>).detail;
  if (!detail) return;
  const key = backendDraftKey(detail.type, detail.id);
  backendDrafts.delete(key);
  draftValues.delete(key);
  const timer = draftTimers.get(key);
  if (timer !== undefined) window.clearTimeout(timer);
  draftTimers.delete(key);
});

const persistDraftInput = (event: Event): void => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) return;
  if (target.id === 'capture-input') {
    scheduleBackendDraft('quick-note', 'quick', { text: target.value });
    return;
  }
  const form = target.closest<HTMLFormElement>('form');
  if (!form) return;
  let type = form.dataset.draftType;
  let id = form.dataset.draftId;
  if (form.classList.contains('edit-form')) {
    type = 'review-edit';
    id = String(new FormData(form).get('candidate_id') ?? '');
  }
  if (!type || !id) return;
  const fields = new FormData(form);
  const values: Record<string, unknown> = {};
  for (const [field, value] of fields.entries()) {
    if (typeof value === 'string' && field !== 'candidate_id') values[field] = value;
  }
  if (type === 'journal-log') {
    values.did = (form.querySelector('#journal-did') as HTMLTextAreaElement | null)?.value ?? '';
    values.remaining = (form.querySelector('#journal-remaining') as HTMLTextAreaElement | null)?.value ?? '';
    values.reflection = (form.querySelector('#journal-reflection') as HTMLTextAreaElement | null)?.value ?? '';
    values.blockers = (form.querySelector('#journal-blockers') as HTMLTextAreaElement | null)?.value ?? '';
    values.projects = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="journal-project"]:checked')).map((input) => input.value);
  }
  if (type === 'journal-thought') {
    for (const [field, elementId] of Object.entries({ problem: 'journal-problem', thinking: 'journal-thinking', conclusion: 'journal-conclusion', summary: 'journal-summary' })) {
      values[field] = (form.querySelector('#' + elementId) as HTMLInputElement | HTMLTextAreaElement | null)?.value ?? '';
    }
    values.projects = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="journal-project"]:checked')).map((input) => input.value);
  }
  if (type === 'inbox-promote') {
    values.target = form.querySelector<HTMLInputElement>('input[name="inbox-target"]:checked')?.value ?? 'thought';
    for (const [field, elementId] of Object.entries({ project: 'inbox-project', block: 'inbox-block', due_date: 'inbox-due', start_date: 'inbox-start', problem: 'inbox-problem', thinking: 'inbox-thinking', conclusion: 'inbox-conclusion', summary: 'inbox-summary' })) {
      const element = form.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>('#' + elementId);
      if (element) values[field] = element.value;
    }
    values.id = id;
  }
  if (type === 'task-edit') {
    values.summary = (form.querySelector('#row-edit-summary') as HTMLInputElement | null)?.value ?? '';
    values.due_date = (form.querySelector('#row-edit-due') as HTMLInputElement | null)?.value ?? '';
  }
  if (type === 'meeting-edit') {
    values.summary = (form.querySelector('#row-edit-summary') as HTMLInputElement | null)?.value ?? '';
    values.start_at = (form.querySelector('#row-edit-start') as HTMLInputElement | null)?.value ?? '';
    values.end_at = (form.querySelector('#row-edit-end') as HTMLInputElement | null)?.value ?? '';
  }
  if (type === 'thread-log') {
    values.text = (form.querySelector('#log-text') as HTMLTextAreaElement | null)?.value ?? '';
    values.projects = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="log-proj"]:checked')).map((input) => input.value);
  }
  if (type === 'artifact') {
    values.project = (form.querySelector('#artifact-project') as HTMLInputElement | null)?.value ?? '';
    values.title = (form.querySelector('#artifact-title') as HTMLInputElement | null)?.value ?? '';
    values.syncState = !!form.querySelector<HTMLInputElement>('#artifact-to-state')?.checked;
    if (!form.querySelector<HTMLInputElement>('#artifact-file')?.files?.length) {
      values.text = (form.querySelector('#artifact-text') as HTMLTextAreaElement | null)?.value ?? '';
    } else {
      delete values.text;
    }
  }
  if ((type === 'artifact') && form.querySelector<HTMLInputElement>('#artifact-file')?.files?.length) {
    delete values.text;
  }
  scheduleBackendDraft(type, id, values);
};
document.addEventListener('input', persistDraftInput);
document.addEventListener('change', persistDraftInput);

function persistEntityDraft<T>(entity: string, value: T): void {
  const saved = saveEntityDraft(entity, value, remoteVersion?.workspace_id);
  if (!saved && !draftStorageWarningShown) {
    draftStorageWarningShown = true;
    toast('浏览器暂时无法保存草稿；请先完成当前编辑再切页', 'err');
  }
  const separator = entity.indexOf(':');
  if (separator < 0) return;
  const prefix = entity.slice(0, separator);
  const id = entity.slice(separator + 1);
  if (prefix === 'log') scheduleBackendDraft('thread-log', id, value as Record<string, unknown>);
  if (prefix === 'artifact') scheduleBackendDraft('artifact', id, value as Record<string, unknown>);
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
      sink_target: String(data.get('sink_target') ?? ''),
    };
  });
  if (editForms.length > 0) reviewDrafts = reviewForms;
  const persistedReviewForms = editForms.length > 0 ? reviewForms : reviewDrafts;
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  const saved = persistDraftSnapshot({
    schema: 1,
    saved_at: new Date().toISOString(),
    source_build: CLIENT_BUILD,
    tab,
    scroll_y: window.scrollY,
    capture_text: capture?.value ?? '',
    review_forms: persistedReviewForms,
  }, remoteVersion?.workspace_id);
  if (capture?.value) scheduleBackendDraft('quick-note', 'quick', { text: capture.value }, 0);
  for (const [candidateId, fields] of Object.entries(persistedReviewForms)) {
    scheduleBackendDraft('review-edit', candidateId, fields as unknown as Record<string, unknown>, 0);
  }
  if (!saved && !draftStorageWarningShown) {
    draftStorageWarningShown = true;
    toast('浏览器暂时无法保存草稿；版本更新仍会继续，但请先完成当前编辑', 'err');
  }
}

async function loadBackendDrafts(): Promise<void> {
  backendDrafts.clear();
  const result = await api<{ ok: boolean; drafts?: BackendDraft[] }>('/api/drafts');
  if (!result.ok || !result.drafts) throw new Error('读取本机草稿失败');
  for (const draft of result.drafts) backendDrafts.set(backendDraftKey(draft.type, draft.id), draft);

  // 一次性迁移旧标签页快照；仅当后端版本不比快照新时迁移。
  const legacy = loadDraftSnapshot(Date.now(), remoteVersion?.workspace_id);
  if (legacy) {
    let migrated = true;
    const legacyValues: Array<{ type: string; id: string; value: Record<string, unknown> }> = [];
    if (legacy.capture_text) legacyValues.push({ type: 'quick-note', id: 'quick', value: { text: legacy.capture_text } });
    for (const [id, fields] of Object.entries(legacy.review_forms)) {
      legacyValues.push({ type: 'review-edit', id, value: fields as unknown as Record<string, unknown> });
    }
    const legacyEditedAt = Date.parse(legacy.saved_at);
    for (const draft of legacyValues) {
      const key = backendDraftKey(draft.type, draft.id);
      const existing = backendDrafts.get(key);
      if (existing && Date.parse(existing.edited_at) >= legacyEditedAt) continue;
      try {
        const saved = await api<{ ok: boolean; draft?: BackendDraft }>('/api/drafts/' + encodeURIComponent(key), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(draft),
        });
        if (!saved.ok || !saved.draft) { migrated = false; continue; }
        backendDrafts.set(key, saved.draft);
      } catch { migrated = false; }
    }
    if (migrated) clearDraftSnapshot(remoteVersion?.workspace_id);
    else publishDraftStatus('旧草稿迁移未完成；原草稿仍保留在当前浏览器。', true);
  }

  const drafts = [...backendDrafts.values()];
  if (!drafts.length) return;
  if (!window.confirm('发现 ' + drafts.length + ' 份本机草稿（七天内编辑）。确定后恢复快速记录和审批表单；其它表单打开时仍会逐份询问。')) {
    publishDraftStatus('有本机草稿尚未恢复；打开相应表单时仍可选择恢复。');
    return;
  }
  const quick = backendDrafts.get(backendDraftKey('quick-note', 'quick'));
  const reviewForms: Record<string, ReviewDraftFields> = {};
  for (const draft of drafts) {
    if (draft.type === 'review-edit') reviewForms[draft.id] = draft.value as unknown as ReviewDraftFields;
    if (draft.type === 'thread-log') saveEntityDraft('log:' + draft.id, draft.value, remoteVersion?.workspace_id);
    if (draft.type === 'artifact') saveEntityDraft('artifact:' + draft.id, draft.value, remoteVersion?.workspace_id);
  }
  if (quick || Object.keys(reviewForms).length) {
    restoredDraft = {
      schema: 1,
      saved_at: new Date().toISOString(),
      source_build: CLIENT_BUILD,
      tab,
      scroll_y: window.scrollY,
      capture_text: typeof quick?.value.text === 'string' ? quick.value.text : '',
      review_forms: reviewForms,
    };
  }
  publishDraftStatus('本机草稿已载入；恢复内容不会自动提交。');
}

function applyRestoredDraft(): void {
  const draft = restoredDraft;
  if (!draft) return;
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  if (capture) capture.value = draft.capture_text;
  reviewDrafts = draft.review_forms;
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

async function doCheckVersion(_reason: string): Promise<void> {
  setVersionStatus('checking', remoteVersion);
  const response = await fetch('/api/version', { cache: 'no-store' });
  if (!response.ok) throw new Error('读取版本信息失败（HTTP ' + response.status + '）');
  const remote = validateVersionPayload(await response.json());
  const instanceChanged = lastServerInstance !== null && lastServerInstance !== remote.server_instance;
  lastServerInstance = remote.server_instance;
  remoteVersion = remote;
  const workspaceId = remote.workspace_id ?? 'unknown';
  workspaceStore.setWorkspace(workspaceId);
  const changedWorkspace = loadedWorkspaceId !== null && loadedWorkspaceId !== workspaceId;
  if (loadedWorkspaceId !== workspaceId) {
    state = null;
    review = null;
    stateLoadError = null;
    reviewLoadError = null;
    lastStateReadAt = null;
    lastReviewReadAt = null;
    resetReviewForWorkspace();
    reviewDrafts = {};
    restoredDraft = null;
    resetTodayForWorkspace();
    resetProjectsForWorkspace();
    backendDrafts.clear();
    loadedWorkspaceId = workspaceId;
    if (changedWorkspace) {
      void loadBackendDrafts().then(() => render()).catch(() => {
        publishDraftStatus('新工作区的草稿暂时无法读取。', true);
      });
    }
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
  } else {
    void renderSettingsView(viewElement('settings') as HTMLElement);
  }
  applyRestoredDraft();
}

/** 「今日」页两个新入口的项目候选：name = 规范 ID，title = 中文显示名。 */
function todayProjectChoices(): ProjectChoice[] {
  return (state?.projects ?? []).map((project) => ({
    name: project.name,
    title: projectDisplayName(project),
  }));
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
    inboxItems,
    inboxError: inboxLoadError,
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
  if (action === 'drafts-open') {
    openDraftManager();
    return;
  }
  if (action === 'operation-query') {
    const operationId = btn.dataset.operationId ?? '';
    if (!operationId) return;
    const queryButton = btn as HTMLButtonElement;
    queryButton.disabled = true;
    void api<{
      status?: string;
      response?: Record<string, unknown>;
      message?: string;
    }>('/api/operations/' + encodeURIComponent(operationId)).then((receipt) => {
      if (receipt.status === 'completed' && receipt.response) {
        publishOperationFeedback(operationId, receipt.response);
      } else {
        toast(receipt.message ?? '结果仍在核实中，请稍后再查。', 'info');
      }
    }).catch((error: unknown) => toast(error, 'err')).finally(() => { queryButton.disabled = false; });
    return;
  }
  if (action === 'copy-diagnostics') {
    void diagnostics.copyDiagnostics();
    return;
  }
  if (action === 'diagnostics-preview') {
    void diagnostics.previewDiagnostics();
    return;
  }
  if (action === 'diagnostics-export') {
    void diagnostics.exportDiagnostics();
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
    if (workspaceId) void switchProfile(workspaceId).catch((err: unknown) => toast(err, 'err'));
    return;
  }
  if (action === 'profile-remove') {
    removeProfile(btn.dataset.workspace ?? '');
    return;
  }
  if (action === 'automation-copy') {
    void copyAutomationSummary(btn.dataset.summary ?? '');
    return;
  }
  if (action === 'settings-doctor') {
    void runSettingsDoctor().catch((err: unknown) => toast(err, 'err'));
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
  if (action === 'import-retry') {
    void retryImport(btn.dataset.jobId ?? '');
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
  if (action === 'journal-log') {
    openJournalLogModal(todayProjectChoices());
    return;
  }
  if (action === 'journal-thought') {
    openJournalThoughtModal(todayProjectChoices());
    return;
  }
  if (action === 'inbox-promote') {
    const item = inboxItems.find((entry) => entry.id === (btn.dataset.id ?? ''));
    if (!item) {
      toast('这条已不在收件箱（可能刚被提升或手工删除）', 'err');
      void refreshState();
      return;
    }
    openInboxPromoteModal(item, todayProjectChoices());
    return;
  }
  if (action === 'inbox-ai-suggest') {
    // 只有这里的显式点击才调模型（见 features/today/inbox.ts 的成本约定）。
    void requestInboxSuggestion(btn.dataset.id ?? '');
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
  if (action === 'content-approve') {
    void approveContent(btn.dataset.path ?? '', btn.dataset.digest ?? '', btn.dataset.title ?? '当前内容');
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
  if (action === 'toggle-edit') {
    const box = btn.closest<HTMLElement>('.entry')?.querySelector<HTMLElement>('.edit-box');
    if (box) box.hidden = !box.hidden;
  }
});

document.addEventListener('submit', (ev) => {
  const form = ev.target as HTMLFormElement;
  if (form.classList.contains('pending-meeting-date-form')) {
    ev.preventDefault();
    void updatePendingMeetingDate(form, { api, mutation, toast, refreshReview, refreshState });
    return;
  }
  if (form.classList.contains('thread-create-form')) {
    ev.preventDefault();
    submitProjectCreate(form, {
      api,
      mutation,
      toast,
      refreshAll,
    });
    return;
  }
  if (!form.classList.contains('edit-form')) return;
  ev.preventDefault();
  submitReviewEdit(form, ev.submitter as HTMLElement | null, {
    api,
    mutation,
    toast,
    refreshReview,
    refreshState,
  });
});


// ---------- 数据 ----------

async function refreshState(): Promise<boolean> {
  const requestId = ++latestStateRequest;
  try {
    const nextState = await api<StatePayload>('/api/state');
    if (requestId !== latestStateRequest) return false;
    state = nextState;
    stateLoadError = null;
    lastStateReadAt = formatBusinessTime(new Date().toISOString());
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) return false;
    stateLoadError = String(err);
    if (tab === 'today') renderToday(document.getElementById('view-today') as HTMLElement);
    return false;
  }
  await refreshInbox(requestId);
  if (requestId !== latestStateRequest) return false;
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

/**
 * 读收件箱待处理条目（`GET /api/inbox`）。
 *
 * **纯读**：这个请求只做解析与本地启发式，绝不触发模型（成本约定）。读失败也不阻断今日页
 * ——条目清空、把原因交给渲染层显示成一句提示，页面其余部分照常可用。
 */
async function refreshInbox(requestId: number): Promise<void> {
  try {
    const payload = await api<{ ok: boolean; items?: InboxItem[]; message?: string }>('/api/inbox');
    if (requestId !== latestStateRequest) return;
    inboxItems = payload.ok ? (payload.items ?? []) : [];
    inboxLoadError = payload.ok ? null : (payload.message ?? '收件箱读取失败');
  } catch (err) {
    if (isStaleWorkspaceResponse(err)) return;
    if (requestId !== latestStateRequest) return;
    inboxItems = [];
    inboxLoadError = String(err);
  }
}

async function refreshReview(): Promise<boolean> {
  const requestId = ++latestReviewRequest;
  saveCurrentDraftSnapshot();
  try {
    const nextReview = await api<ReviewPayload>('/api/review');
    if (requestId !== latestReviewRequest) return false;
    review = nextReview;
    reviewLoadError = null;
    lastReviewReadAt = formatBusinessTime(new Date().toISOString());
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
    onSelectTab: (next) => {
      const changed = tab !== next;
      tab = next;
      render();
      if (changed && next === 'review') void refreshReview();
    },
    onRefresh: () => {
      void refreshAll().then((result) => {
        toast(result.state && result.review ? '已刷新' : '刷新未完成：保留了可用的旧数据', result.state && result.review ? 'ok' : 'err');
      });
    },
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
        toast(err, 'err');
        window.setTimeout(() => window.close(), 800);
      });
    },
  });
  for (const operationId of unresolvedOperationIds()) {
    void api<{
      status?: string;
      response?: Record<string, unknown>;
    }>('/api/operations/' + encodeURIComponent(operationId)).then((receipt) => {
      if (receipt.status === 'completed' && receipt.response) {
        publishOperationFeedback(operationId, receipt.response);
      }
    }).catch(() => { /* keep the unresolved receipt visible; the user may retry reading */ });
  }
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
  // 来源弹层的在途读取必须在关闭时作废（§4.4）；原由 mountAsk 注册，问答下线后在此注册。
  registerModalCloseHook(invalidateSourceReads);
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
  });

  async function startApp(): Promise<void> {
    await checkVersion('startup');
    const legacyFallback = loadDraftSnapshot(Date.now(), remoteVersion?.workspace_id);
    restoredDraft = null;
    try {
      await loadBackendDrafts();
    } catch {
      restoredDraft = legacyFallback;
      publishDraftStatus('本机草稿暂时无法读取；当前浏览器中已有的草稿仍保留。', true);
    }
    await refreshAll();
    if (restoredDraft) render();
  }

  // 60 秒自动刷新只发生在可见页；隐藏页暂停读取，回到前台时由 visibilitychange 立即补一次。
  void startApp();
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    void checkVersion('interval');
  }, 60000);
  window.setInterval(() => {
    if (document.visibilityState !== 'visible') return;
  }, 60000);
}
