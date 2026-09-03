// 晨间简报 v2 组件渲染：结构化快照（/api/state.brief）→ HTML。
// 纯字符串渲染、无 DOM 依赖，便于单元验证与生成静态预览。
// 安全：所有用户/模型文本一律经 esc 转义后输出。

import { esc } from './md';

export interface BriefHealth {
  level: string;
  label: string;
  reasons: string[];
}
export interface BriefMeeting {
  title: string;
  start_time: string;
}
export interface BriefTask {
  summary: string;
  due_date: string | null;
  task_id: string | null;
}
export interface BriefAction {
  signal_id: string;
  title: string;
  category_key: string;
  category: string;
  evidence: string;
  source_ref: string;
  project: string | null;
  due_date: string | null;
  detail: string;
  /** 入选「需要行动」的排名（1..5）；非入选项无此字段 */
  rank?: number;
}
export interface BriefCompletion {
  text: string;
  source_ref: string;
}
export interface BriefData {
  date: string;
  health: BriefHealth;
  meetings: BriefMeeting[];
  tasks: BriefTask[];
  actions: BriefAction[];
  proposals: BriefAction[];
  completions: BriefCompletion[];
  pending_review: number;
  ranking_model: string | null;
}

const BRIEF_CAT_CLASS: Record<string, string> = {
  'main-push': 'cat-push',
  commitment: 'cat-commit',
  'anti-stall': 'cat-stall',
  proposal: 'cat-proposal',
};

function briefDayEpoch(iso: string | null | undefined): number {
  if (!iso) return NaN;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return NaN;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86400000;
}

function briefDueBadge(due: string | null, todayIso: string): string {
  if (!due) return '<span class="bf-due-slot"></span>';
  const diff = Math.round(briefDayEpoch(due) - briefDayEpoch(todayIso));
  if (!Number.isFinite(diff)) {
    return '<span class="bf-due later">' + esc(due) + '</span>';
  }
  if (diff < 0) {
    const label = diff <= -2 ? '已过期 ' + String(-diff) + ' 天' : '已过期';
    return '<span class="bf-due over">' + label + '</span>';
  }
  if (diff === 0) return '<span class="bf-due today">今天到期</span>';
  if (diff <= 2) return '<span class="bf-due soon">剩 ' + String(diff) + ' 天</span>';
  if (diff <= 7) return '<span class="bf-due week">剩 ' + String(diff) + ' 天</span>';
  return '<span class="bf-due later">' + esc(due.slice(5)) + '</span>';
}

function briefAnnChip(a: BriefAction): string {
  const cls = BRIEF_CAT_CLASS[a.category_key] ?? 'cat-proposal';
  const label = a.rank ? a.category + ' · #' + String(a.rank) : a.category;
  return '<span class="bf-ann ' + cls + '">' + esc(label) + '</span>';
}

function briefSectionHead(title: string, count: number, note: string): string {
  return '<div class="bf-sec-head"><span class="bf-sec-title">' + esc(title) + '</span>' +
    (count > 0 ? '<span class="bf-count">' + count + '</span>' : '') +
    (note ? '<span class="bf-note">' + esc(note) + '</span>' : '') + '</div>';
}

function briefMeetingBlock(list: BriefMeeting[]): string {
  const head = briefSectionHead('会议', list.length, '');
  if (!list.length) {
    return '<div class="bf-section">' + head + '<div class="bf-empty">今日无会议</div></div>';
  }
  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  const rows = list.map((m) => {
    const t = /^(\d{1,2}):(\d{2})$/.exec(m.start_time);
    const past = t ? Number(t[1]) * 60 + Number(t[2]) < nowMinutes : false;
    return '<div class="bf-row bf-mt' + (past ? ' past' : '') + '">' +
      '<span class="bf-time">' + esc(m.start_time) + '</span>' +
      '<span class="bf-mt-title">' + esc(m.title) + '</span></div>';
  });
  return '<div class="bf-section">' + head + rows.join('') + '</div>';
}

/** 任务行尾部：AI 注解 chip（若有）+「标记完成」控件（仅真飞书任务，有 task_id）。 */
function briefTaskTrailing(t: BriefTask, ann: BriefAction | undefined): string {
  const chip = ann ? briefAnnChip(ann) : '';
  const done = t.task_id
    ? '<button class="bf-done" data-action="task-complete" data-task="' +
      esc(t.task_id) +
      '" title="在飞书中标记该任务为已完成" aria-label="标记完成">✓</button>'
    : '';
  return chip || done ? '<span class="bf-trailing">' + chip + done + '</span>' : '';
}

function briefTaskBlock(b: BriefData, todayIso: string): string {
  // 任务 → 行动候选的精确实联：source_ref / signal_id 里的 feishu-task guid。
  const byGuid = new Map<string, BriefAction>();
  for (const a of b.actions) {
    const m = /feishu-task:([0-9a-zA-Z_-]+)/.exec(a.source_ref)
      || /^task-([0-9a-zA-Z_-]+)$/.exec(a.signal_id);
    if (m) byGuid.set(m[1].toLowerCase(), a);
  }
  const sorted = [...b.tasks].sort((x, y) => {
    const dx = briefDayEpoch(x.due_date);
    const dy = briefDayEpoch(y.due_date);
    if (!Number.isFinite(dx)) return Number.isFinite(dy) ? 1 : 0;
    if (!Number.isFinite(dy)) return -1;
    return dx - dy;
  });
  let annotated = 0;
  const rows = sorted.map((t) => {
    const key = t.task_id ? String(t.task_id).toLowerCase() : '';
    const ann = key ? byGuid.get(key) : undefined;
    if (ann) annotated += 1;
    return '<div class="bf-row bf-task">' +
      briefDueBadge(t.due_date, todayIso) +
      '<span class="bf-task-title">' + esc(t.summary) + '</span>' +
      briefTaskTrailing(t, ann) + '</div>';
  }).join('');
  const head = briefSectionHead(
    '待办任务', sorted.length,
    annotated > 0 ? annotated + ' 项今日优先（AI 排序）' : ''
  );
  return '<div class="bf-section">' + head + rows + '</div>';
}

function briefOrphanActions(b: BriefData): BriefAction[] {
  const guids = new Set<string>();
  for (const t of b.tasks) if (t.task_id) guids.add(String(t.task_id).toLowerCase());
  return b.actions.filter((a) => {
    const m = /feishu-task:([0-9a-zA-Z_-]+)/.exec(a.source_ref)
      || /^task-([0-9a-zA-Z_-]+)$/.exec(a.signal_id);
    return !(m && guids.has(m[1].toLowerCase()));
  });
}

function briefOrphanBlock(list: BriefAction[], todayIso: string): string {
  const rows = list.map((a) => {
    const pieces: string[] = [];
    if (a.project) pieces.push(a.project);
    if (a.detail) pieces.push(a.detail);
    const refName = a.source_ref.startsWith('feishu-task:')
      ? ''
      : (a.source_ref.split('/').pop() || '');
    if (refName && refName !== a.project) pieces.push(refName);
    const meta = pieces.length
      ? '<div class="bf-act-meta">' + pieces.map(esc).join(' · ') + '</div>'
      : '';
    return '<div class="bf-act">' +
      '<div class="bf-act-top">' + briefAnnChip(a) +
      '<span class="bf-act-title">' + esc(a.title) + '</span>' +
      briefDueBadge(a.due_date, todayIso) + '</div>' + meta + '</div>';
  }).join('');
  return '<div class="bf-section">' +
    briefSectionHead('需要行动', list.length, '任务清单之外') + rows + '</div>';
}

function briefFoldBlock(label: string, count: number, rowsHtml: string): string {
  return '<details class="bf-fold"><summary><span class="bf-chev">›</span><span>' + esc(label) + '</span>' +
    '<span class="bf-count">' + count + '</span></summary>' + rowsHtml + '</details>';
}

function briefProposalBlock(list: BriefAction[]): string {
  const rows = list.map((p) => {
    const pieces: string[] = [];
    if (p.project) pieces.push(p.project);
    const refName = p.source_ref.startsWith('feishu-task:')
      ? ''
      : (p.source_ref.split('/').pop() || '');
    if (refName && refName !== p.project) pieces.push(refName);
    return '<div class="bf-minor-row"><span class="bf-minor-main">' + esc(p.title) + '</span>' +
      (pieces.length
        ? '<span class="bf-minor-text">' + pieces.map(esc).join(' · ') + '</span>'
        : '') + '</div>';
  }).join('');
  return briefFoldBlock('AI 提议（非事实）', list.length, rows);
}

function briefCompletionBlock(list: BriefCompletion[]): string {
  const rows = list.map((c) =>
    '<div class="bf-minor-row"><span class="bf-minor-main ok-text">✓ ' + esc(c.text) + '</span></div>'
  ).join('');
  return briefFoldBlock('最近完成', list.length, rows);
}

export function briefCardHtml(b: BriefData, todayIso: string): string {
  const parts: string[] = [];
  if (b.health.level !== 'ok') {
    const tone = b.health.level === 'alert' ? 'bad' : 'warn';
    parts.push('<div class="bf-alert ' + tone + '"><span class="dot ' + tone + '"></span>' +
      '<span>健康度 ' + esc(b.health.label) + '</span>' +
      (b.health.reasons.length
        ? '<span class="bf-alert-reasons">' + b.health.reasons.map(esc).join(' · ') + '</span>'
        : '') + '</div>');
  }
  if (b.pending_review > 0) {
    parts.push('<div class="bf-hint"><span>⏳ 另有 ' + b.pending_review +
      ' 条会议提取结果待确认（未确认内容不计入事实）</span>' +
      '<button class="link" data-action="go-review">去审批</button></div>');
  }
  parts.push(briefMeetingBlock(b.meetings));
  parts.push(briefTaskBlock(b, todayIso));
  const orphans = briefOrphanActions(b);
  if (orphans.length) parts.push(briefOrphanBlock(orphans, todayIso));
  if (b.proposals.length) parts.push(briefProposalBlock(b.proposals));
  if (b.completions.length) parts.push(briefCompletionBlock(b.completions));
  return parts.join('');
}
