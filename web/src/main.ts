import './style.css';

import { mutation, deferReloadUntilMutationsComplete, isMutationInFlight, setMutationIdleHandler } from './lifecycle/connection';
import {
  clearDraftSnapshot,
  loadDraftSnapshot,
  saveDraftSnapshot as persistDraftSnapshot,
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
import { esc, mdToHtml } from './md';
// 使用指南（WEB_USAGE_GUIDE.md 由 npm run sync-guide 在构建前同步；随包内置，离线可看）
import guideMd from './guide.md?raw';

type Tab = 'today' | 'review' | 'ask' | 'projects' | 'guide';

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
interface ProjectState {
  name: string;
  dirty: boolean;
  ahead: number;
  behind: number;
  has_upstream: boolean;
  inbox_pending: number;
  next_step: string | null;
  git_error: string | null;
  /** ADR 0023：已建档（有效 project-main 档案）与否及其 status */
  registered: boolean;
  status: string | null;
}
interface StatePayload {
  day: string;
  status: StatusState;
  brief_md: string | null;
  brief_generated: boolean;
  inbox_pending: number;
  projects: ProjectState[];
  runtime?: {
    frontend_build: string;
    server_version: string;
    server_instance: string;
  };
}
interface ReviewEntry {
  candidate_id: string;
  kind: string;
  description: string;
  target_project: string | null;
  route: string | null;
  due_date: string | null;
  evidence: string | null;
  decision: string;
  historical: boolean;
  actionable: boolean;
  ai_original: string;
  meeting_date: string;
  meeting_title: string;
  note_link: string;
  transcript_link: string;
  apply_error: string | null;
}
interface ReviewGroup {
  meeting_date: string;
  meeting_title: string;
  entries: ReviewEntry[];
}
interface ReviewPayload {
  groups: ReviewGroup[];
  errors: string[];
}

const KIND_LABELS: Record<string, string> = {
  decision: '决策',
  'action-item': '行动项',
  'project-status-change': '状态变化',
  'task-create': '建任务',
};
const ROUTE_LABELS: Record<string, string> = {
  'feishu-task': '飞书任务',
  'project-main': '项目主笔记',
  'project-inbox': '项目 inbox',
  'global-inbox': '全局 inbox',
};
const DECISION_LABELS: Record<string, string> = {
  pending: '待确认',
  approved: '已批准',
  rejected: '已拒绝',
};

let state: StatePayload | null = null;
let review: ReviewPayload | null = null;
let tab: Tab = 'today';
let importing = false;
let versionStatus: VersionStatus = 'checking';
let remoteVersion: VersionPayload | null = null;
let lastServerInstance: string | null = null;
let versionCheckPromise: Promise<void> | null = null;
let connectionHadFailure = false;
let restoredDraft: DraftSnapshot | null = null;

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

const ASK_STORAGE_KEY = 'wb.ask.threads.v1';
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

const app = document.getElementById('app') as HTMLElement;
const toasts = document.getElementById('toasts') as HTMLElement;

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  try {
    const resp = await fetch(url, init);
    if (!resp.ok) {
      connectionHadFailure = true;
      throw new Error('请求失败：HTTP ' + resp.status);
    }
    if (connectionHadFailure && url !== '/api/version') {
      connectionHadFailure = false;
      void checkVersion('connection-restored');
    }
    return (await resp.json()) as T;
  } catch (err) {
    connectionHadFailure = true;
    throw err;
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
  document.querySelectorAll<HTMLFormElement>('.edit-form').forEach((form) => {
    const data = new FormData(form);
    const candidateId = String(data.get('candidate_id') ?? '');
    if (!candidateId) return;
    reviewForms[candidateId] = {
      description: String(data.get('description') ?? ''),
      target_project: String(data.get('target_project') ?? ''),
      route: String(data.get('route') ?? ''),
      due_date: String(data.get('due_date') ?? ''),
    };
  });
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  const ask = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (ask) askDraft = ask.value;
  persistDraftSnapshot({
    schema: 1,
    saved_at: new Date().toISOString(),
    source_build: CLIENT_BUILD,
    tab,
    scroll_y: window.scrollY,
    capture_text: capture?.value ?? '',
    ask_draft: askDraft,
    review_forms: reviewForms,
  });
}

function applyRestoredDraft(): void {
  const draft = restoredDraft;
  if (!draft) return;
  const capture = document.getElementById('capture-input') as HTMLInputElement | null;
  if (capture) capture.value = draft.capture_text;
  askDraft = draft.ask_draft;
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
  clearDraftSnapshot();
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

async function doCheckVersion(reason: string): Promise<void> {
  setVersionStatus('checking');
  const response = await fetch('/api/version', { cache: 'no-store' });
  if (!response.ok) throw new Error('version HTTP ' + response.status + ' (' + reason + ')');
  const remote = validateVersionPayload(await response.json());
  const instanceChanged = lastServerInstance !== null && lastServerInstance !== remote.server_instance;
  lastServerInstance = remote.server_instance;
  remoteVersion = remote;
  if (remote.frontend_build === CLIENT_BUILD) {
    setVersionStatus('synced');
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
  });
  const todayView = document.getElementById('view-today') as HTMLElement;
  const reviewView = document.getElementById('view-review') as HTMLElement;
  const askView = document.getElementById('view-ask') as HTMLElement;
  const projectsView = document.getElementById('view-projects') as HTMLElement;
  const guideView = document.getElementById('view-guide') as HTMLElement;
  todayView.style.display = tab === 'today' ? '' : 'none';
  reviewView.style.display = tab === 'review' ? '' : 'none';
  askView.style.display = tab === 'ask' ? '' : 'none';
  projectsView.style.display = tab === 'projects' ? '' : 'none';
  guideView.style.display = tab === 'guide' ? '' : 'none';
  if (tab === 'today') {
    renderToday(todayView);
  } else if (tab === 'review') {
    renderReview(reviewView);
  } else if (tab === 'projects') {
    renderProjects(projectsView);
  } else if (tab === 'guide') {
    renderGuide(guideView);
  } else {
    renderAsk(askView);
  }
  applyRestoredDraft();
}

function renderShell(): void {
  app.innerHTML =
    '<header class="topbar">' +
    '<div class="brand"><span class="logo">SW</span><div><h1>SummitWorkbench</h1>' +
    '<p class="tagline">外置执行管理层 · 第二大脑</p></div></div>' +
    '<div class="header-right">' +
    '<span class="version-status checking" id="version-status">正在检查版本</span>' +
    '<span class="day-pill" id="day-pill">—</span>' +
    '<button class="ghost" id="btn-refresh" title="刷新">↻</button>' +
    '<button class="ghost" id="btn-quit" title="退出工作台（停止本地服务）">退出</button>' +
    '</div></header>' +
    '<div class="version-error-banner" id="version-error-banner" hidden>' +
    '<span>工作台更新未完成。你的草稿已保留。</span>' +
    '<button class="ghost" data-action="retry-update">重试更新</button>' +
    '<button class="ghost" data-action="copy-diagnostics">复制诊断信息</button>' +
    '</div>' +
    '<nav class="tabs" role="tablist">' +
    '<button class="tab" data-tab="today" role="tab">今日</button>' +
    '<button class="tab" data-tab="review" role="tab">审批 <span class="tab-badge" id="tab-badge-review"></span></button>' +
    '<button class="tab" data-tab="ask" role="tab">第二大脑</button>' +
    '<button class="tab" data-tab="projects" role="tab">项目</button>' +
    '<button class="tab" data-tab="guide" role="tab">指南</button>' +
    '</nav>' +
    '<main>' +
    '<section id="view-today" class="view"></section>' +
    '<section id="view-review" class="view"></section>' +
    '<section id="view-ask" class="view"></section>' +
    '<section id="view-projects" class="view"></section>' +
    '<section id="view-guide" class="view"></section>' +
    '</main>' +
    '<div class="modal-backdrop" id="modal-backdrop" hidden><div class="modal" id="modal"></div></div>';

  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    b.addEventListener('click', () => {
      const next = b.dataset.tab;
      tab = next === 'review' || next === 'ask' || next === 'projects' || next === 'guide' ? next : 'today';
      render();
    });
  });
  (document.getElementById('btn-refresh') as HTMLButtonElement).addEventListener('click', () => {
    void refreshAll().then(() => toast('已刷新', 'ok'));
  });
  (document.getElementById('btn-quit') as HTMLButtonElement).addEventListener('click', () => {
    if (!window.confirm('确定退出工作台并停止本地服务？')) return;
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
    if (ev.target === backdrop) closeModal();
  });
}

function renderToday(view: HTMLElement): void {
  if (!state) {
    view.innerHTML = '<div class="loading">正在连接工作台…</div>';
    return;
  }
  const s = state.status;
  const h = healthTone();
  const captureValue = (view.querySelector<HTMLInputElement>('#capture-input'))?.value ?? '';

  // 待确认卡片
  const pending = s.pending_review;
  const oldest = s.backlog.oldest_age_days;
  const reviewCard = pending > 0
    ? '<div class="card warn"><div class="card-head">' +
      '<span class="dot warn"></span><strong>待确认审批</strong>' +
      '<span class="count-badge">' + pending + ' 条待确认</span></div>' +
      '<p class="card-sub">' + (oldest != null ? '最老已等待 ' + oldest + ' 天 · ' : '') + '处理完才会写回执行系统</p>' +
      '<button class="primary" data-action="go-review">去处理 →</button></div>'
    : '<div class="card ok"><div class="card-head"><span class="dot ok"></span><strong>审批已清空</strong></div>' +
      '<p class="card-sub">无待确认候选，执行系统状态干净。</p></div>';

  // 导入区
  const importZone = importing
    ? '<div class="dropzone busy"><div class="spinner"></div><p>正在归档并结构化…（模型处理中，稍候）</p></div>'
    : '<div class="dropzone" id="dropzone">' +
      '<div class="dz-icon">⤓</div><p><strong>拖入会议逐字稿</strong>（.md / .txt，带说话人+时间戳）</p>' +
      '<p class="hint">或 <button class="link" id="btn-pick">点击选择文件</button> · 文件名建议 YYYY-MM-DD-会议标题.txt</p>' +
      '<input type="file" id="file-input" accept=".md,.txt" hidden></div>' +
      '<div class="import-result" id="import-result"></div>';

  // 简报
  const briefHtml = state.brief_generated && state.brief_md
    ? '<div class="brief">' + mdToHtml(state.brief_md) + '</div>'
    : '<div class="empty"><p>今日简报还没生成。</p>' +
      '<button class="primary" data-action="run-brief">⚡ 现在生成（约 30 秒）</button></div>';

  view.innerHTML =
    '<section class="hero">' +
    '<div class="hero-main"><p class="kicker">今天</p>' +
    '<h2>' + esc(state.day) + '</h2></div>' +
    '<div class="hero-side"><span class="health ' + h.tone + '"></span><span>' + esc(h.label) + '</span></div>' +
    '</section>' +
    '<section class="block capture-block">' +
    '<form id="capture-form" autocomplete="off">' +
    '<input id="capture-input" type="text" placeholder="记点什么…（想法 / 承诺，可用 #项目 标注）" value="' + esc(captureValue) + '">' +
    '<button class="primary" type="submit">记入</button>' +
    '</form>' +
    '<p class="hint">回车即记入全局 inbox；说清「要做什么 + 截止 + #项目」的，AI 会帮你分类。</p>' +
    '</section>' +
    '<section class="block">' + reviewCard + '</section>' +
    '<section class="block">' +
    '<h3 class="section-title">导入会议纪要</h3>' + importZone +
    '</section>' +
    projectsHtml() +
    '<section class="block">' +
    '<div class="section-head"><h3 class="section-title">今日简报</h3>' +
    '<button class="ghost" data-action="run-brief" title="重新生成">↻</button></div>' + briefHtml +
    '</section>';

  const captureForm = document.getElementById('capture-form') as HTMLFormElement;
  captureForm.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const input = document.getElementById('capture-input') as HTMLInputElement;
    const text = input.value.trim();
    if (!text) return;
    void mutation(() => api<{ ok: boolean; message: string }>('/api/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })).then((r) => {
      if (r.ok) {
        input.value = '';
        toast(r.message, 'ok');
      } else {
        toast(r.message, 'err');
      }
    }).catch((err: unknown) => toast(String(err), 'err'));
  });

  bindDropzone();
}

function bindDropzone(): void {
  const zone = document.getElementById('dropzone') as HTMLElement;
  const fileInput = document.getElementById('file-input') as HTMLInputElement;
  if (!zone || !fileInput) return;
  const pick = document.getElementById('btn-pick') as HTMLButtonElement;
  pick.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) void doImport(file);
    fileInput.value = '';
  });
  zone.addEventListener('dragover', (ev) => {
    ev.preventDefault();
    zone.classList.add('dragover');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (ev) => {
    ev.preventDefault();
    zone.classList.remove('dragover');
    const file = ev.dataTransfer?.files?.[0];
    if (file) void doImport(file);
  });
}

async function doImport(file: File): Promise<void> {
  if (importing) return;
  if (!file.name.toLowerCase().endsWith('.md') && !file.name.toLowerCase().endsWith('.txt')) {
    toast('仅支持 .md / .txt 逐字稿文件', 'err');
    return;
  }
  importing = true;
  renderToday(document.getElementById('view-today') as HTMLElement);
  const form = new FormData();
  form.append('file', file);
  const resultBox = document.getElementById('import-result') as HTMLElement;
  try {
    const r = await mutation(() => api<{
      ok: boolean;
      message: string;
      details?: string[];
      estimate?: { est_cost: number; currency: string; crosses_soft_budget: boolean };
    }>('/api/meetings/import', { method: 'POST', body: form }));
    if (r.ok && resultBox) {
      const est = r.estimate;
      const costLine = est
        ? '<p class="hint">预估费用约 ' + fmtCost(est.est_cost, est.currency) +
          (est.crosses_soft_budget ? '（⚠ 已越过本月软预算，仅为提醒）' : '') + '</p>'
        : '';
      const details = (r.details ?? []).map((d) => '<p>' + esc(d) + '</p>').join('');
      resultBox.innerHTML = '<div class="msg ok">✓ ' + esc(r.message) + '</div>' + costLine + details;
      toast('导入完成：' + r.message, 'ok');
    } else {
      if (resultBox) resultBox.innerHTML = '<div class="msg err">✗ ' + esc(r.message) + '</div>';
      toast(r.message, 'err');
    }
  } catch (err) {
    const msg = String(err);
    if (resultBox) resultBox.innerHTML = '<div class="msg err">✗ ' + esc(msg) + '</div>';
    toast(msg, 'err');
  } finally {
    importing = false;
    renderToday(document.getElementById('view-today') as HTMLElement);
    void refreshState();
  }
}

// ---------- 第二大脑：会话存储（localStorage，上限 10） ----------

function loadAskStore(): void {
  try {
    const raw = window.localStorage.getItem(ASK_STORAGE_KEY);
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
      ASK_STORAGE_KEY,
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
  if (existing) askDraft = existing.value;
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
  const bubbles = thread.messages.map((m) =>
    m.role === 'user'
      ? '<div class="msg user"><div class="bubble">' + esc(m.text).replace(/\n/g, '<br>') + '</div></div>'
      : '<div class="msg ai"><div class="bubble">' + m.text + '</div></div>'
  ).join('');
  const showTyping = askBusy && thread.id === askBusyThreadId;
  const typing = showTyping ? '<div class="msg ai"><div class="bubble typing">思考中…</div></div>' : '';
  main.innerHTML =
    '<div class="ask-chat" id="ask-chat">' + bubbles + typing + '</div>' +
    '<div class="ask-inputbar">' +
    '<form class="ask" id="ask-form" autocomplete="off">' +
    '<textarea id="ask-input" rows="2" placeholder="问第二大脑…（Enter 提问，Shift+Enter 换行）"></textarea>' +
    '<div class="form-row"><span class="hint ask-keyhint">Enter 提问 · Shift+Enter 换行</span>' +
    '<button class="primary" type="submit"' + (askBusy ? ' disabled' : '') + '>提问</button></div>' +
    '</form></div>';
  bindAskInput();
  const inputEl = document.getElementById('ask-input') as HTMLTextAreaElement | null;
  if (inputEl) inputEl.value = askDraft;
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
  thread.messages.push({ role: 'user', text: q, ts: new Date().toISOString(), sources: [] });
  input.value = '';
  askDraft = '';
  askBusy = true;
  askBusyThreadId = thread.id;
  saveAskStore();
  renderAskSide();
  renderAskChat();
  try {
    const r = await mutation(() => api<AskResponse>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history }),
    }));
    const html = r.ok && r.answer_html
      ? r.answer_html
      : '<p class="err-text">' + esc(r.message ?? '提问失败') + '</p>';
    thread.messages.push({
      role: 'ai',
      text: html,
      ts: new Date().toISOString(),
      sources: r.source_ids ?? [],
    });
  } catch (err) {
    thread.messages.push({
      role: 'ai',
      text: '<p class="err-text">' + esc(String(err)) + '</p>',
      ts: new Date().toISOString(),
      sources: [],
    });
  } finally {
    askBusy = false;
    askBusyThreadId = null;
    saveAskStore();
    renderAskSide();
    renderAskChat();
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
    view.innerHTML = '<div class="loading">加载审批页…</div>';
    return;
  }
  const pending = state?.status.pending_review ?? 0;
  const errorsHtml = review.errors.length
    ? '<div class="msg err">审批页解析错误：<br>' + review.errors.map(esc).join('<br>') + '</div>'
    : '';
  const groupsHtml = review.groups.length
    ? review.groups.map((g, gi) => {
        const cards = g.entries.map(entryCard).join('');
        const groupPending = g.entries.filter((e) => e.decision === 'pending').length;
        return '<div class="meeting-head">' +
          '<span class="meeting-date">' + esc(g.meeting_date) + '</span>' +
          '<span class="meeting-title">' + esc(g.meeting_title) + '</span>' +
          '<span class="group-actions">' +
          '<button class="ghost" data-action="group-decide" data-decision="approved" data-group="' + gi + '"' +
          (groupPending === 0 ? ' disabled' : '') + '>✓ 全批(' + groupPending + ')</button>' +
          '<button class="ghost" data-action="group-decide" data-decision="rejected" data-group="' + gi + '"' +
          (groupPending === 0 ? ' disabled' : '') + '>✗ 全拒</button>' +
          '</span></div>' + cards;
      }).join('')
    : '<div class="empty"><p>暂无待确认候选。</p>' +
      '<p class="hint">导入会议逐字稿后，提取结果会出现在这里。</p></div>';
  const approvedPending = review.groups.reduce(
    (n, g) => n + g.entries.filter((e) => e.decision === 'approved' && !e.apply_error).length,
    0,
  );
  const applyNudge = approvedPending > 0
    ? '<p class="apply-nudge">' + approvedPending + ' 条已批准、尚未写回 —— 点「应用（写回）」后才会真正写入项目/创建飞书任务</p>'
    : '';
  view.innerHTML =
    '<div class="review-toolbar">' +
    '<div><h3 class="section-title" style="margin:0">会议提取待确认</h3>' +
    '<p class="hint">' + pending + ' 条待确认 · 「✓ 批准」只做标记，点「应用（写回）」才会真正写入项目/创建飞书任务 · 截止早于今天的可用「一键拒绝过期项」清理</p>' + applyNudge + '</div>' +
    '<div class="form-row">' +
    '<button class="ghost" data-action="reject-expired" title="把截止日期早于今天的待确认条目批量置为拒绝">一键拒绝过期项</button>' +
    '<button class="ghost" data-action="plan">预演应用</button>' +
    '<button class="primary" data-action="apply">应用（写回）</button>' +
    '</div></div>' +
    errorsHtml +
    '<div id="review-groups">' + groupsHtml + '</div>' +
    '<div id="plan-result"></div>';
}

function projectChips(p: ProjectState): string[] {
  const chips: string[] = [];
  if (p.dirty) chips.push('未提交改动');
  if (p.behind > 0) chips.push('落后 ' + p.behind + ' 提交');
  if (p.ahead > 0) chips.push('领先 ' + p.ahead + ' 提交');
  if (p.inbox_pending > 0) chips.push(p.inbox_pending + ' 条 inbox');
  if (p.git_error) chips.push('git 异常');
  return chips;
}

function projectCard(p: ProjectState): string {
  const chips = projectChips(p);
  const chipsHtml = chips.length
    ? '<div class="chips">' + chips.map((c) => '<span class="chip">' + esc(c) + '</span>').join('') + '</div>'
    : '<span class="chip ok-chip">正常</span>';
  const step = p.next_step
    ? '<div class="project-step"><span class="step-label">下一步</span><span class="step-text">' + esc(p.next_step) + '</span></div>'
    : '<div class="project-step muted-step"><span class="step-label">下一步</span><span class="step-text">主笔记还没写下一步</span></div>';
  return (
    '<div class="card project' + (p.dirty || p.behind > 0 || p.inbox_pending > 0 ? ' attention' : '') + '">' +
    '<div class="card-head"><strong class="project-name">' + esc(p.name) + '</strong>' + chipsHtml + '</div>' +
    step +
    '<div class="card-foot">' +
    '<button class="ghost card-archive" data-action="project-archive" data-name="' + esc(p.name) + '" data-confirm="1">归档</button>' +
    '</div>' +
    '</div>'
  );
}

// ---------- 项目推进（ADR 0023：工作台精选） ----------

/** 是否在工作台上：已建档且 status = active（首页推进卡只显示这些）。 */
function isOnHome(p: ProjectState): boolean {
  return p.registered && p.status === 'active';
}

/** 是否新文件夹：还没建立 project-main 档案。 */
function isNewProject(p: ProjectState): boolean {
  return !p.registered;
}

function projectStatusBadge(p: ProjectState): string {
  if (!p.registered) return '<span class="badge is-new">新</span>';
  if (p.status === 'active') return '<span class="badge is-home">在工作台</span>';
  if (p.status === 'archived') return '<span class="badge is-archived">已归档</span>';
  return '<span class="badge is-archived">' + esc(p.status ?? '未知') + '</span>';
}

function projectsHtml(): string {
  if (!state) return '';
  const onHome = state.projects.filter(isOnHome);
  const fresh = state.projects.filter(isNewProject);
  if (onHome.length === 0 && fresh.length === 0) return '';
  const banner = fresh.length
    ? '<div class="new-projects"><div class="new-projects-head">' +
      '<strong>新文件夹</strong>' +
      '<span class="hint">尚未建立项目档案 · 加入工作台后才会出现在上方推进卡</span></div>' +
      fresh.map((p) =>
        '<div class="new-project-row"><span class="project-name">' + esc(p.name) + '</span>' +
        '<span class="row-actions">' +
        '<button class="ok" data-action="project-activate" data-name="' + esc(p.name) + '">加入工作台</button>' +
        '<button class="ghost" data-action="project-archive" data-name="' + esc(p.name) + '">归档</button>' +
        '</span></div>'
      ).join('') +
      '</div>'
    : '';
  const emptyNote = onHome.length === 0
    ? '<div class="empty"><p>工作台上还没有项目——加入上方新文件夹，或在「项目」页管理。</p></div>'
    : '';
  return (
    '<section class="block">' +
    '<div class="section-head"><h3 class="section-title">项目推进</h3>' +
    '<button class="ghost" data-action="goto-projects">管理全部 →</button></div>' +
    banner +
    onHome.map(projectCard).join('') +
    emptyNote +
    '</section>'
  );
}

function projectRow(p: ProjectState): string {
  const chips = projectChips(p);
  const chipsHtml = chips.length
    ? '<div class="chips">' + chips.map((c) => '<span class="chip">' + esc(c) + '</span>').join('') + '</div>'
    : '';
  const step = p.next_step
    ? '<div class="project-step"><span class="step-label">下一步</span><span class="step-text">' + esc(p.next_step) + '</span></div>'
    : '';
  const action = isOnHome(p)
    ? '<button class="ghost" data-action="project-archive" data-name="' + esc(p.name) + '">归档</button>'
    : '<button class="ghost" data-action="project-activate" data-name="' + esc(p.name) + '">加入工作台</button>';
  return (
    '<div class="card project-row">' +
    '<div class="project-row-main">' +
    '<div class="project-row-title"><strong class="project-name">' + esc(p.name) + '</strong>' + projectStatusBadge(p) + '</div>' +
    chipsHtml +
    step +
    '</div>' +
    '<div class="project-row-actions">' + action + '</div>' +
    '</div>'
  );
}

function projectsListHtml(query: string): string {
  if (!state) return '<div class="loading">加载中…</div>';
  const q = query.trim().toLowerCase();
  const matched = state.projects.filter((p) => !q || p.name.toLowerCase().includes(q));
  if (matched.length === 0) {
    return '<div class="empty"><p>' + (q ? '没有匹配「' + esc(q) + '」的项目' : '暂无项目文件夹') + '</p></div>';
  }
  const rank = (p: ProjectState): number => (isOnHome(p) ? 0 : isNewProject(p) ? 1 : 2);
  const sorted = [...matched].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  return sorted.map(projectRow).join('');
}

function renderProjects(view: HTMLElement): void {
  if (!state) {
    view.innerHTML = '<div class="loading">加载中…</div>';
    return;
  }
  const query = (view.querySelector<HTMLInputElement>('#project-search'))?.value ?? '';
  const total = state.projects.length;
  const onHome = state.projects.filter(isOnHome).length;
  const fresh = state.projects.filter(isNewProject).length;
  const archived = state.projects.filter((p) => p.status === 'archived').length;
  view.innerHTML =
    '<div class="section-head"><h3 class="section-title">全部项目</h3>' +
    '<span class="hint">共 ' + total + ' · 在工作台 ' + onHome + ' · 新 ' + fresh + ' · 已归档 ' + archived + '</span></div>' +
    '<div class="project-toolbar">' +
    '<input id="project-search" type="search" placeholder="搜索项目名…" value="' + esc(query) + '">' +
    '</div>' +
    '<div id="projects-list"></div>';
  const listEl = document.getElementById('projects-list') as HTMLElement;
  listEl.innerHTML = projectsListHtml(query);
  const search = view.querySelector<HTMLInputElement>('#project-search');
  search?.addEventListener('input', () => {
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(search.value);
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

function entryCard(e: ReviewEntry): string {
  const decision = DECISION_LABELS[e.decision] ?? e.decision;
  const kind = KIND_LABELS[e.kind] ?? e.kind;
  const today = state?.day ?? '';
  const expired = e.decision === 'pending' && !!e.due_date && !!today && e.due_date < today;
  const meta = [
    e.target_project ? '目标：' + esc(e.target_project) : '目标：unresolved',
    e.route ? '落点：' + (ROUTE_LABELS[e.route] ?? e.route) : '落点：未定',
    e.due_date ? '截止：' + esc(e.due_date) + (expired ? '（已过期）' : '') : '',
    e.evidence ? '依据：' + esc(e.evidence) : '',
    e.historical ? '历史补导' : '',
  ].filter(Boolean).join(' · ');
  const warn = e.actionable ? '' : '<div class="not-actionable">⚠ 依据或目标项目缺失，暂不可批准写回</div>';
  const err = e.apply_error ? '<div class="not-actionable">应用出错：' + esc(e.apply_error) + '</div>' : '';
  const note = e.note_link ? '<span class="wikilink">' + esc(e.note_link) + '</span>' : '';
  const routeLabel = e.route ? (ROUTE_LABELS[e.route] ?? e.route) : '';
  const approveLabel = routeLabel ? '✓ 批准 → ' + esc(routeLabel) : '✓ 批准（先在「修改」里选落点）';
  const approveDisabled = e.route ? '' : ' disabled title="落点未定，请点「修改」设置后再批准"';
  return (
    '<div class="card entry ' + e.decision + '" data-id="' + esc(e.candidate_id) + '">' +
    '<div class="entry-top"><span class="kind">' + esc(kind) + '</span>' +
    '<span class="badge ' + e.decision + '">' + esc(decision) + '</span></div>' +
    '<p class="desc">' + esc(e.description) + '</p>' +
    warn + err +
    '<div class="meta">' + meta + '</div>' +
    '<div class="meta">来源：' + note + '</div>' +
    '<div class="row">' +
    '<button class="ok" data-action="decide" data-decision="approved"' + approveDisabled + '>' + approveLabel + '</button>' +
    '<button class="bad" data-action="decide" data-decision="rejected">✗ 拒绝</button>' +
    (e.decision === 'pending' ? '' : '<button class="ghost" data-action="decide" data-decision="pending">↺ 改回待确认</button>') +
    '<button class="ghost" data-action="toggle-edit">修改</button>' +
    '</div>' +
    '<div class="edit-box" hidden>' +
    '<form class="edit-form">' +
    '<input type="hidden" name="candidate_id" value="' + esc(e.candidate_id) + '">' +
    '<label>正文</label><textarea name="description" rows="2">' + esc(e.description) + '</textarea>' +
    '<div class="grid2">' +
    '<div><label>目标项目</label><input name="target_project" value="' + esc(e.target_project ?? '') + '"></div>' +
    '<div><label>落点</label><select name="route">' + routeOptions(e.route) + '</select></div>' +
    '<div><label>截止日期</label><input name="due_date" placeholder="YYYY-MM-DD" value="' + esc(e.due_date ?? '') + '"></div>' +
    '</div>' +
    '<div class="row">' +
    (e.decision === 'pending'
      ? '<button class="primary" type="submit" data-action="save-approve" title="保存修改并标记批准（仍需点「应用（写回）」才真正写回）">保存并批准</button>'
      : '') +
    '<button class="ghost" type="submit">仅保存</button>' +
    '</div>' +
    '</form></div>' +
    '</div>'
  );
}

function routeOptions(current: string | null): string {
  const keys = ['', 'feishu-task', 'project-main', 'project-inbox', 'global-inbox'];
  return keys.map((k) => {
    const label = k === '' ? '（未定）' : ROUTE_LABELS[k] ?? k;
    return '<option value="' + k + '"' + (k === current ? ' selected' : '') + '>' + label + '</option>';
  }).join('');
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
  if (action === 'goto-projects') {
    tab = 'projects';
    render();
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
  if (action === 'run-brief') {
    void runBrief();
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
    const ids = group.entries
      .filter((e) => e.decision === 'pending')
      .map((e) => e.candidate_id);
    void batchDecide(ids, btn.dataset.decision ?? 'pending');
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

async function batchDecide(candidateIds: string[], decision: string): Promise<void> {
  if (candidateIds.length === 0) {
    toast('没有可操作的条目', 'info');
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
      toast('✓ 已批量' + verb + ' ' + (r.updated ?? '') + ' 条' + tip, 'ok');
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

async function planApply(exec: boolean): Promise<void> {
  const planResult = document.getElementById('plan-result');
  try {
    const r = await mutation(() => api<{ ok: boolean; message?: string; plan_text?: string; executed?: boolean }>(
      exec ? '/api/review/apply' : '/api/review/plan',
      { method: 'POST' },
    ));
    if (!r.ok) {
      toast(r.message ?? '操作失败', 'err');
      return;
    }
    const text = r.plan_text ?? '';
    const title = exec ? '已应用' : '预演计划（未写入）';
    openModal(
      '<h3>' + title + '</h3><pre>' + esc(text) + '</pre>' +
      (exec ? '' : '<div class="row"><button class="primary" data-action="apply">确认应用（写回项目/建任务/归档）</button></div>')
    );
    if (exec) {
      toast('已应用', 'ok');
      void refreshReview();
      void refreshState();
    }
  } catch (err) {
    toast(String(err), 'err');
    if (planResult) planResult.innerHTML = '<div class="msg err">' + esc(String(err)) + '</div>';
  }
}

function openModal(html: string): void {
  const backdrop = document.getElementById('modal-backdrop') as HTMLElement;
  const modal = document.getElementById('modal') as HTMLElement;
  modal.innerHTML = html;
  backdrop.hidden = false;
  modal.querySelector('[data-action="apply"]')?.addEventListener('click', () => {
    closeModal();
    void planApply(true);
  });
  const close = document.createElement('button');
  close.className = 'ghost close-modal';
  close.textContent = '关闭';
  close.style.marginTop = '12px';
  modal.appendChild(close);
  close.addEventListener('click', closeModal);
}

function closeModal(): void {
  (document.getElementById('modal-backdrop') as HTMLElement).hidden = true;
}

// ---------- 数据 ----------

async function refreshState(): Promise<void> {
  try {
    state = await api<StatePayload>('/api/state');
  } catch (err) {
    toast(String(err), 'err');
    return;
  }
  const dayPill = document.getElementById('day-pill');
  if (dayPill) dayPill.textContent = state.day;
  const badge = document.getElementById('tab-badge-review');
  if (badge) badge.textContent = state.status.pending_review > 0 ? String(state.status.pending_review) : '';
  if (tab === 'today') renderToday(document.getElementById('view-today') as HTMLElement);
  else if (tab === 'projects') {
    renderProjects(document.getElementById('view-projects') as HTMLElement);
  }
}

async function refreshReview(): Promise<void> {
  try {
    review = await api<ReviewPayload>('/api/review');
  } catch (err) {
    toast(String(err), 'err');
    return;
  }
  if (tab === 'review') renderReview(document.getElementById('view-review') as HTMLElement);
}

async function refreshAll(): Promise<void> {
  await Promise.all([refreshState(), refreshReview()]);
}

// ---------- 启动 ----------

loadAskStore();
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
  restoredDraft = loadDraftSnapshot();
  await checkVersion('startup');
  await refreshAll();
  if (restoredDraft) render();
}

void startApp();
window.setInterval(() => { void checkVersion('interval'); }, 60000);
