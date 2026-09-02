import './style.css';

import { esc, mdToHtml } from './md';

type Tab = 'today' | 'review';

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
}
interface StatePayload {
  day: string;
  status: StatusState;
  brief_md: string | null;
  brief_generated: boolean;
  inbox_pending: number;
  projects: ProjectState[];
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

const app = document.getElementById('app') as HTMLElement;
const toasts = document.getElementById('toasts') as HTMLElement;

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    throw new Error('请求失败：HTTP ' + resp.status);
  }
  return (await resp.json()) as T;
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

// ---------- 渲染 ----------

function render(): void {
  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    const active = b.dataset.tab === tab;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  const todayView = document.getElementById('view-today') as HTMLElement;
  const reviewView = document.getElementById('view-review') as HTMLElement;
  todayView.style.display = tab === 'today' ? '' : 'none';
  reviewView.style.display = tab === 'review' ? '' : 'none';
  if (tab === 'today') {
    renderToday(todayView);
  } else {
    renderReview(reviewView);
  }
}

function renderShell(): void {
  app.innerHTML =
    '<header class="topbar">' +
    '<div class="brand"><span class="logo">SW</span><div><h1>SummitWorkbench</h1>' +
    '<p class="tagline">外置执行管理层 · 第二大脑</p></div></div>' +
    '<div class="header-right">' +
    '<span class="day-pill" id="day-pill">—</span>' +
    '<button class="ghost" id="btn-refresh" title="刷新">↻</button>' +
    '<button class="ghost" id="btn-quit" title="退出工作台（停止本地服务）">退出</button>' +
    '</div></header>' +
    '<nav class="tabs" role="tablist">' +
    '<button class="tab" data-tab="today" role="tab">今日</button>' +
    '<button class="tab" data-tab="review" role="tab">审批 <span class="tab-badge" id="tab-badge-review"></span></button>' +
    '</nav>' +
    '<main>' +
    '<section id="view-today" class="view"></section>' +
    '<section id="view-review" class="view"></section>' +
    '</main>' +
    '<div class="modal-backdrop" id="modal-backdrop" hidden><div class="modal" id="modal"></div></div>';

  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    b.addEventListener('click', () => {
      tab = b.dataset.tab === 'review' ? 'review' : 'today';
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
  const askValue = (view.querySelector<HTMLTextAreaElement>('#ask-input'))?.value ?? '';

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

  // 问答
  const askHtml =
    '<form class="ask" id="ask-form">' +
    '<textarea id="ask-input" rows="2" placeholder="问第二大脑：例如「网课项目最近的决策是什么？」">' + esc(askValue) + '</textarea>' +
    '<div class="form-row"><button class="primary" type="submit">提问</button></div>' +
    '</form>' +
    '<div class="answer" id="answer"></div>';

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
    '</section>' +
    '<section class="block">' +
    '<h3 class="section-title">问第二大脑</h3>' + askHtml +
    '</section>';

  const captureForm = document.getElementById('capture-form') as HTMLFormElement;
  captureForm.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const input = document.getElementById('capture-input') as HTMLInputElement;
    const text = input.value.trim();
    if (!text) return;
    void api<{ ok: boolean; message: string }>('/api/capture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then((r) => {
      if (r.ok) {
        input.value = '';
        toast(r.message, 'ok');
      } else {
        toast(r.message, 'err');
      }
    }).catch((err: unknown) => toast(String(err), 'err'));
  });

  bindDropzone();
  bindAsk();
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
    const r = await api<{
      ok: boolean;
      message: string;
      details?: string[];
      estimate?: { est_cost: number; currency: string; crosses_soft_budget: boolean };
    }>('/api/meetings/import', { method: 'POST', body: form });
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

function bindAsk(): void {
  const form = document.getElementById('ask-form') as HTMLFormElement;
  if (!form) return;
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const input = document.getElementById('ask-input') as HTMLTextAreaElement;
    const answer = document.getElementById('answer') as HTMLElement;
    const q = input.value.trim();
    if (!q) return;
    answer.innerHTML = '<div class="loading">思考中…</div>';
    void api<{ ok: boolean; message: string; answer_html?: string }>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    }).then((r) => {
      if (r.ok && r.answer_html) {
        answer.innerHTML = r.answer_html;
      } else {
        answer.innerHTML = '<p class="err-text">' + esc(r.message) + '</p>';
      }
    }).catch((err: unknown) => {
      answer.innerHTML = '<p class="err-text">' + esc(String(err)) + '</p>';
    });
  });
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
  view.innerHTML =
    '<div class="review-toolbar">' +
    '<div><h3 class="section-title" style="margin:0">会议提取待确认</h3>' +
    '<p class="hint">' + pending + ' 条待确认 · 批准后才写回项目/飞书 · 截止早于今天的可用「一键拒绝过期项」清理</p></div>' +
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
    '</div>'
  );
}

function projectsHtml(): string {
  if (!state || state.projects.length === 0) return '';
  return (
    '<section class="block">' +
    '<h3 class="section-title">项目推进</h3>' +
    state.projects.map(projectCard).join('') +
    '</section>'
  );
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
  return (
    '<div class="card entry ' + e.decision + '" data-id="' + esc(e.candidate_id) + '">' +
    '<div class="entry-top"><span class="kind">' + esc(kind) + '</span>' +
    '<span class="badge ' + e.decision + '">' + esc(decision) + '</span></div>' +
    '<p class="desc">' + esc(e.description) + '</p>' +
    warn + err +
    '<div class="meta">' + meta + '</div>' +
    '<div class="meta">来源：' + note + '</div>' +
    '<div class="row">' +
    '<button class="ok" data-action="decide" data-decision="approved">✓ 批准</button>' +
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
    '<div class="row"><button class="primary" type="submit">保存修改</button></div>' +
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
  void api<{ ok: boolean; message: string }>('/api/review/edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => {
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) void refreshReview();
  }).catch((err: unknown) => toast(String(err), 'err'));
});

async function decide(candidateId: string, decision: string): Promise<void> {
  try {
    const r = await api<{ ok: boolean; message: string }>('/api/review/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, decision }),
    });
    toast(r.message, r.ok ? 'ok' : 'err');
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
    const r = await api<{ ok: boolean; message: string; updated?: number }>('/api/review/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds, decision }),
    });
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshReview();
  void refreshState();
}

async function runBrief(): Promise<void> {
  toast('正在生成今日简报…', 'info');
  try {
    const r = await api<{ ok: boolean; message: string }>('/api/run/brief', { method: 'POST' });
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(String(err), 'err');
  }
  void refreshState();
}

async function planApply(exec: boolean): Promise<void> {
  const planResult = document.getElementById('plan-result');
  try {
    const r = await api<{ ok: boolean; message?: string; plan_text?: string; executed?: boolean }>(
      exec ? '/api/review/apply' : '/api/review/plan',
      { method: 'POST' },
    );
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

renderShell();
void refreshAll();
window.setInterval(() => { void refreshState(); }, 60000);
