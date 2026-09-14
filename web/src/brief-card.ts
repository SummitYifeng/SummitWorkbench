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
  /** 飞书日历事件原始标识/时间戳（附加演进；缺 event_id 的旧快照不可行内编辑） */
  event_id?: string | null;
  start_ts?: string | null;
  end_ts?: string | null;
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
    const edit = m.event_id
      ? '<button class="bf-edit" data-action="meeting-edit" data-event="' + esc(m.event_id) +
        '" data-title="' + esc(m.title) + '" data-start="' + esc(m.start_ts ?? '') +
        '" data-end="' + esc(m.end_ts ?? '') +
        '" title="编辑该日历会议（标题/时间，写回飞书）" aria-label="编辑会议">✎</button>'
      : '';
    const trailing = edit ? '<span class="bf-trailing">' + edit + '</span>' : '';
    return '<div class="bf-row bf-mt' + (past ? ' past' : '') + '">' +
      '<span class="bf-time">' + esc(m.start_time) + '</span>' +
      '<span class="bf-mt-title">' + esc(m.title) + '</span>' +
      trailing + '</div>';
  });
  return '<div class="bf-section">' + head + rows.join('') + '</div>';
}

/** 任务行尾部：AI 注解 chip（若有）+「标记完成」/「编辑」控件（仅真飞书任务，有 task_id）。 */
function briefTaskTrailing(t: BriefTask, ann: BriefAction | undefined): string {
  const chip = ann ? briefAnnChip(ann) : '';
  const done = t.task_id
    ? '<button class="bf-done" data-action="task-complete" data-task="' +
      esc(t.task_id) +
      '" title="在飞书中标记该任务为已完成" aria-label="标记完成">✓</button>'
    : '';
  const edit = t.task_id
    ? '<button class="bf-edit" data-action="task-edit" data-task="' + esc(t.task_id) +
      '" data-title="' + esc(t.summary) + '" data-due="' + esc(t.due_date ?? '') +
      '" title="编辑该任务（标题/截止，写回飞书）" aria-label="编辑任务">✎</button>'
    : '';
  return chip || done || edit
    ? '<span class="bf-trailing">' + chip + done + edit + '</span>'
    : '';
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

/**
 * 出处文件的显示名：先去掉 `#区块` 锚点与目录，再去掉日期前缀，只留可读标题。
 *
 * 2026-09-14：界面上不再直接显示 `huoman-logistics · 2026-09-14-木子沟通.md` 这种
 * 「英文 ID + 文件名」；完整路径仍可在「第二大脑」的来源按钮里看到。
 * ⚠️ 锚点必须先剥掉：`projects/hii-affairs.md#下一步` 若只按 `.md$` 去尾，
 * 会留下 `it-development.md#下一步` 这种把项目 ID 带出来的残渣（真实数据验证发现）。
 */
export function briefSourceLabel(ref: string): string {
  if (!ref || ref.startsWith('feishu-task:')) return '';
  const withoutAnchor = ref.split('#')[0];
  const base = (withoutAnchor.split('/').pop() || '').replace(/\.(md|txt)$/i, '');
  return base.replace(/^\d{4}-?\d{2}-?\d{2}[-_]?/, '');
}

/**
 * 这条行动要显示的出处标签。
 *
 * - 飞书任务引用没有可读文件名 ⇒ 空；
 * - **项目自身页面**的引用（`projects/<该项目>.md#…`）不重复显示——那只是把项目 ID
 *   再写一遍，同一行的项目中文名已经表达了它；
 * - 其余给出去目录、去日期前缀的可读名。
 */
function briefRefLabel(a: BriefAction, projectNames: Record<string, string>): string {
  const ref = a.source_ref || '';
  if (a.project && ref.startsWith('projects/' + a.project + '.md')) return '';
  const label = briefSourceLabel(ref);
  const projectName = a.project ? projectNames[a.project] ?? a.project : '';
  return label && label !== projectName ? label : '';
}

function briefOrphanBlock(
  list: BriefAction[],
  todayIso: string,
  projectNames: Record<string, string>,
): string {
  const rows = list.map((a) => {
    const pieces: string[] = [];
    if (a.project) pieces.push(projectNames[a.project] ?? a.project);
    if (a.detail) pieces.push(a.detail);
    const refName = briefRefLabel(a, projectNames);
    if (refName) pieces.push(refName);
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

function briefProposalBlock(list: BriefAction[], projectNames: Record<string, string>): string {
  const rows = list.map((p) => {
    const pieces: string[] = [];
    if (p.project) pieces.push(projectNames[p.project] ?? p.project);
    const refName = briefRefLabel(p, projectNames);
    if (refName) pieces.push(refName);
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

/**
 * 渲染整份简报。
 *
 * `projectNames` 是「项目 ID → 中文显示名」映射（由今日页从 `state.projects` 提供）：
 * 界面上一律先给中文名，没有映射时才退回 ID。
 */
export function briefCardHtml(
  b: BriefData,
  todayIso: string,
  projectNames: Record<string, string> = {},
): string {
  const parts: string[] = [];
  if (b.health.level !== 'ok') {
    const tone = b.health.level === 'alert' ? 'bad' : 'warn';
    parts.push('<div class="bf-alert ' + tone + '"><span class="dot ' + tone + '"></span>' +
      '<span>健康度 ' + esc(b.health.label) + '</span>' +
      (b.health.reasons.length
        ? '<span class="bf-alert-reasons">' + b.health.reasons.map(esc).join(' · ') + '</span>'
        : '') + '</div>');
  }
  // 「待确认 N 条」在今日页只保留一处（下方那张带「去处理 →」的审批卡）；
  // 简报里再重复一遍数字只会让同一屏出现两个同样的计数（2026-09-14 去重）。
  // 上下两块（2026-09-14）：会议在上、紧凑；待办任务在下、占满整宽。
  // 原先左右各占一半，会议少时空半屏、待办一多就被半宽卡住。
  const schedule = briefMeetingBlock(b.meetings);
  const taskColumn: string[] = [briefTaskBlock(b, todayIso)];
  const orphans = briefOrphanActions(b);
  if (orphans.length) taskColumn.push(briefOrphanBlock(orphans, todayIso, projectNames));
  parts.push('<div class="bf-stack"><div class="bf-col bf-col-schedule">' + schedule + '</div>' +
    '<div class="bf-col bf-col-tasks">' + taskColumn.join('') + '</div></div>');
  if (b.proposals.length) parts.push(briefProposalBlock(b.proposals, projectNames));
  if (b.completions.length) parts.push(briefCompletionBlock(b.completions));
  return parts.join('');
}
