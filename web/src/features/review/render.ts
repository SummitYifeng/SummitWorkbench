import { projectDisplayName } from '../projects/render';
import { esc, inlineMd } from '../../md';
import type { ProjectState } from '../projects/types';
import type {
  ExternalAction,
  ReviewEntry,
  ReviewFilter,
  ReviewPayload,
  PendingContent,
  ReviewRenderOptions,
} from './types';

const KIND_LABELS: Record<string, string> = {
  decision: '决策',
  'action-item': '行动项',
  'project-status-change': '状态变化',
  'task-create': '建任务',
};
const ROUTE_LABELS: Record<string, string> = {
  'feishu-task': '飞书任务',
  'feishu-meeting': '新建会议',
  'project-main': '项目主笔记',
  'project-followup': '跟进事项',
  'project-inbox': '项目 inbox',
  'global-inbox': '全局 inbox',
  'knowledge-note': '知识沉淀',
};
const DECISION_LABELS: Record<string, string> = {
  pending: '待确认',
  approved: '已批准',
  rejected: '已拒绝',
};
const FILTER_LABELS: Record<ReviewFilter, string> = {
  all: '全部',
  pending: '待确认',
  approved: '已批准',
  rejected: '已拒绝',
};

function routeOptions(): string {
  const keys = [
    '',
    'knowledge-note',
    'project-main',
    'feishu-task',
  ];
  return keys.map((k) => {
    const label = k === '' ? '（未定）' : ROUTE_LABELS[k] ?? k;
    return '<option value="' + k + '">' + label + '</option>';
  }).join('');
}

function sourceLink(raw: string, label: string): string {
  const value = raw.trim();
  const match = value.match(/^\[\[([^\]]+)\]\]$/);
  const path = (match?.[1] ?? value).split('|', 1)[0].trim();
  if (!path || path.startsWith('/') || path.includes('://')) {
    return '<span class="wikilink">' + esc(value) + '</span>';
  }
  return '<button type="button" class="link source-link" data-action="source-open" data-source-id="' + esc(path) +
    '" title="打开' + esc(label) + '">' + esc(label) + ' · ' + esc(value) + '</button>';
}

/** 目标项目的显示名：`unresolved`（内部标记）显示为「未定」，有映射就用中文名，否则退回 ID。 */
function targetLabel(target: string | null, projectNames: Record<string, string>): string {
  if (!target || target === 'unresolved') return '未定';
  return projectNames[target] ?? target;
}

function entryCard(
  e: ReviewEntry,
  today: string,
  selectedIds: ReadonlySet<string>,
  projectNames: Record<string, string>,
): string {
  const decision = DECISION_LABELS[e.decision] ?? e.decision;
  const kind = KIND_LABELS[e.kind] ?? e.kind;
  const expired = e.decision === 'pending' && !!e.due_date && !!today && e.due_date < today;
  const meta = [
    '目标：' + esc(targetLabel(e.target_project, projectNames)),
    e.route ? '落点：' + (ROUTE_LABELS[e.route] ?? e.route) : '落点：未定',
    e.due_date ? '截止：' + esc(e.due_date) + (expired ? '（已过期）' : '') : '',
    e.start_at
      ? (e.route === 'feishu-task' ? '任务开始：' : '会议时间：') + esc(e.start_at.replace('T', ' ')) +
        (e.route === 'feishu-meeting' && e.end_at ? ' ~ ' + esc(e.end_at.replace('T', ' ')) : '')
      : '',
    e.evidence ? '依据：' + inlineMd(e.evidence) : '',
    e.historical ? '历史补导' : '',
  ].filter(Boolean).join(' · ');
  const warn = e.actionable ? '' : '<div class="not-actionable">⚠ 依据或目标项目缺失，暂不可批准写回</div>';
  const timingWarning = e.route === 'feishu-task' && (!e.start_at || !e.due_date)
    ? '<div class="not-actionable timing-warning">⚠ 将创建无时效的飞书任务：请填写任务开始时间和截止日期；仍可批准。</div>'
    : '';
  const err = e.apply_error ? '<div class="not-actionable">应用出错：' + esc(e.apply_error) + '</div>' : '';
  const sources = [
    e.note_link ? sourceLink(e.note_link, '会议笔记') : '',
    e.transcript_link ? sourceLink(e.transcript_link, '逐字稿') : '',
  ].filter(Boolean).join(' · ') || '未提供来源';
  const routeLabel = e.route ? (ROUTE_LABELS[e.route] ?? e.route) : '';
  const approveLabel = routeLabel ? '✓ 批准 → ' + esc(routeLabel) : '✓ 批准（先在「修改」里选落点）';
  const approveDisabled = e.route && e.actionable
    ? ''
    : e.route
      ? ' disabled title="依据或目标项目缺失，请点「修改」补齐后再批准"'
      : ' disabled title="落点未定，请点「修改」设置后再批准"';
  return (
    '<div class="card entry ' + e.decision + '" data-id="' + esc(e.candidate_id) + '">' +
    '<div class="entry-top"><span class="entry-select">' +
    (e.decision === 'pending'
      ? '<input type="checkbox" data-review-select="' + esc(e.candidate_id) + '"' +
        (selectedIds.has(e.candidate_id) ? ' checked' : '') +
        ' aria-label="选择：' + esc(e.description) + '">' : '') +
    '<span class="kind">' + esc(kind) + '</span>' +
    '<span class="badge ' + e.decision + '">' + esc(decision) + '</span></div>' +
    '<p class="desc">' + inlineMd(e.description) + '</p>' +
    warn + timingWarning + err +
    '<div class="meta">' + meta + '</div>' +
    '<div class="meta">来源：' + sources + '</div>' +
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
      '<div><label>目标项目</label><input name="target_project" list="wb-project-options" placeholder="填项目 ID 或别名（如 finance-ops）；留空 = 全局 inbox" value="' + esc(e.target_project === 'unresolved' ? '' : e.target_project ?? '') + '"></div>' +
    '<div><label>去处</label><select name="route">' + routeOptions() + '</select></div>' +
      '<div><label>沉淀目标</label><input name="sink_target" placeholder="仅「知识沉淀」用：填「页面路径#区块」" title="例如 hii/clusters/ip-trademark#关键结论（vault 相对路径 + 区块标题）" value="' + esc(e.sink_target ?? '') + '"></div>' +
    '<div><label>截止日期</label><input name="due_date" type="date" value="' + esc(e.due_date ?? '') + '"></div>' +
    '<div><label data-review-field-label="start">' + (e.route === 'feishu-task' ? '任务开始时间' : e.route === 'feishu-meeting' ? '会议开始时间' : '开始时间（新建会议）') +
      '</label><input name="start_at" type="' + (e.route === 'feishu-task' ? 'date' : 'datetime-local') +
      '" data-review-field="start" value="' + esc(e.route === 'feishu-task' ? (e.start_at?.split('T', 1)[0] ?? '') : (e.start_at ?? '')) + '"></div>' +
    '<div><label data-review-field-label="end">' + (e.route === 'feishu-meeting' ? '会议结束时间' : '结束时间（新建会议）') +
      '</label><input name="end_at" type="datetime-local" data-review-field="end" value="' + esc(e.end_at ?? '') + '"></div>' +
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

/** 外部写回行的可读标识：「会议提取项 · 会议 2026-09-14」；内部 ID 只留在 hover。 */
function externalCandidateLabel(a: ExternalAction): string {
  const kind = KIND_LABELS[a.kind] ?? '会议提取项';
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(a.candidate_id);
  return match ? kind + ' · 会议 ' + match[1] : kind;
}

function renderExternalActions(actions: ExternalAction[]): string {
  if (!actions.length) return '';
  const labels: Record<string, string> = {
    prepared: '已准备', sending: '发送中', succeeded: '已创建', failed: '创建失败',
    unknown: '结果未知', 'reconciled-succeeded': '已核对创建', 'reconciled-not-found': '已核对未找到',
  };
  const errorLabels: Record<string, string> = {
    external_action_interrupted: '上次执行中断，结果待核对',
    external_action_accounting_failed: '远端可能已创建，本地记账失败，结果待核对',
    operation_outcome_unknown: '操作结果未知，请先核对，禁止自动重试',
  };
  const rows = actions.map((a) => {
    const label = labels[a.state] ?? a.state;
    let controls = '';
    if (a.state === 'unknown') {
      controls = '<button class="ghost" data-action="external-recheck" data-operation="' + esc(a.operation_id) + '">重新核对</button>' +
        '<button class="ghost" data-action="external-confirm-created" data-operation="' + esc(a.operation_id) + '">确认已创建</button>' +
        '<button class="ghost" data-action="external-confirm-not-found" data-operation="' + esc(a.operation_id) + '">确认未创建</button>';
    } else if (a.state === 'reconciled-not-found') {
      controls = '<button class="ghost" data-action="external-retry" data-operation="' + esc(a.operation_id) + '">确认后重试</button>';
    }
    // 出错时保留错误原文（可执行信息）；成功/未决时不把飞书 remote_id 铺在行里——进 hover。
    const detail = a.error ? ' · ' + esc(errorLabels[a.error] ?? a.error) : '';
    const hint = a.remote_id ? '远端记录：' + a.remote_id + '｜内部标识：' + a.candidate_id : '内部标识：' + a.candidate_id;
    return '<div class="external-action-row" title="' + esc(hint) + '"><span><strong>' + esc(label) + '</strong> · ' +
      esc(externalCandidateLabel(a)) + detail + '</span><span class="row">' + controls + '</span></div>';
  }).join('');
  return '<section class="external-actions"><h4>外部写回状态</h4>' + rows + '<p class="hint">结果未知时不会自动再次创建；请先核对，只有确认未创建后才能再次重试。</p></section>';
}

export function reviewHtml(
  review: ReviewPayload,
  pending: number,
  today: string,
  projects: ProjectState[],
  externalActions: ExternalAction[],
  externalActionsError: string | null = null,
  options: ReviewRenderOptions = { filter: 'all', selectedIds: new Set<string>() },
): string {
  const allEntries = review.groups.flatMap((group) => group.entries);
  // 项目 ID → 中文显示名：审批卡里只显示中文名（ID 留给「修改」表单里填）。
  const projectNames: Record<string, string> = {};
  for (const p of projects) projectNames[p.name] = projectDisplayName(p);
  const filteredGroups = review.groups
    .map((group, sourceIndex) => ({
      ...group,
      sourceIndex,
      entries: group.entries.filter((entry) => options.filter === 'all' || entry.decision === options.filter),
    }))
    .filter((group) => group.entries.length > 0);
  const filteredEntries = filteredGroups.flatMap((group) => group.entries);
  const selectableIds = filteredEntries
    .filter((entry) => entry.decision === 'pending')
    .map((entry) => entry.candidate_id);
  const selectedCount = selectableIds.filter((id) => options.selectedIds.has(id)).length;
  const allSelected = selectableIds.length > 0 && selectedCount === selectableIds.length;
  const filterOptions = (Object.keys(FILTER_LABELS) as ReviewFilter[]).map((value) =>
    '<option value="' + value + '"' + (options.filter === value ? ' selected' : '') + '>' +
    FILTER_LABELS[value] + '</option>'
  ).join('');
  const countText = (decision: string): string => String(allEntries.filter((entry) => entry.decision === decision).length);
  const selectionText = selectedCount > 0 ? '已选 ' + selectedCount + ' 条待确认候选' : '尚未选择待确认候选';
  const selectionToolbar =
    '<div class="review-selection" aria-live="polite">' +
    '<div class="review-selection-line"><label for="review-status-filter">状态筛选</label>' +
    '<select id="review-status-filter" data-review-filter="' + esc(options.filter) + '">' + filterOptions + '</select>' +
    '<span class="review-counts">待确认 ' + countText('pending') + ' · 已批准 ' + countText('approved') + ' · 已拒绝 ' + countText('rejected') + '</span></div>' +
    '<div class="review-selection-line"><span>' + esc(selectionText) + ' · 当前筛选：' + esc(FILTER_LABELS[options.filter]) + '</span>' +
    '<button class="ghost" type="button" data-action="review-select-all"' + (selectableIds.length === 0 ? ' disabled' : '') + '>' +
    (allSelected ? '取消全选' : '全选当前') + '</button>' +
    '<button class="ok" type="button" data-action="review-batch" data-decision="approved"' + (selectedCount === 0 ? ' disabled' : '') + '>批量批准</button>' +
    '<button class="bad" type="button" data-action="review-batch" data-decision="rejected"' + (selectedCount === 0 ? ' disabled' : '') + '>批量拒绝</button></div></div>';
  const errorsHtml = review.errors.length
    ? '<div class="msg err">审批页解析错误：<br>' + review.errors.map(esc).join('<br>') + '</div>'
    : '';
  const groupsHtml = filteredGroups.length
    ? filteredGroups.map((g) => {
        const cards = g.entries.map((entry) => entryCard(entry, today, options.selectedIds, projectNames)).join('');
        const groupPending = g.entries.filter((e) => e.decision === 'pending').length;
        const groupApprovable = g.entries.filter((e) => e.decision === 'pending' && e.actionable && !!e.route).length;
        const groupBlocked = groupPending - groupApprovable;
        const approvalTitle = groupBlocked > 0
          ? ' title="仅纳入具备依据和落点的候选；' + groupBlocked + ' 条未纳入批准"'
          : '';
        return '<div class="meeting-head">' +
          '<span class="meeting-date">' + esc(g.meeting_date) + '</span>' +
          '<span class="meeting-title">' + inlineMd(g.meeting_title) + '</span>' +
          '<span class="group-actions">' +
          '<button class="ghost" data-action="group-decide" data-decision="approved" data-group="' + g.sourceIndex + '"' +
          (groupApprovable === 0 ? ' disabled' : '') + approvalTitle + '>✓ 全批(' + groupApprovable + ')</button>' +
          '<button class="ghost" data-action="group-decide" data-decision="rejected" data-group="' + g.sourceIndex + '"' +
          (groupPending === 0 ? ' disabled' : '') + '>✗ 全拒(' + groupPending + ')</button>' +
          '</span></div>' + cards;
      }).join('')
    : '<div class="empty"><p>当前筛选没有候选。</p>' +
      '<p class="hint">可以切换状态筛选，或导入会议逐字稿生成新的待确认项。</p></div>';
  const approvedPending = review.groups.reduce(
    (n, g) => n + g.entries.filter((e) => e.decision === 'approved' && !e.apply_error).length,
    0,
  );
  const applyNudge = approvedPending > 0
    ? '<p class="apply-nudge">' + approvedPending + ' 条已批准、尚未写回 —— 点「应用（写回）」后才会真正写入项目/创建飞书任务</p>'
    : '';
  const projectOptions = projects.length
    ? '<datalist id="wb-project-options">' +
      projects.map((p) => '<option value="' + esc(p.name) + '">' + esc(projectDisplayName(p)) + '</option>').join('') +
      '</datalist>'
    : '';
  const externalHtml = (externalActionsError
    ? '<section class="external-actions error-state"><h4>外部写回状态暂时无法读取</h4><p class="hint">' + esc(externalActionsError) +
      '。审批决定仍保留；请稍后重试读取，不要据此重复应用。</p></section>'
    : '') + renderExternalActions(externalActions);
  const contentItems = review.content_items ?? [];
  const contentReviewHtml = '<section class="content-review" aria-labelledby="content-review-title">' +
    '<div class="content-review-head"><h3 class="section-title" id="content-review-title">正式内容待确认</h3>' +
    '<p class="hint">' + contentItems.length + ' 篇当前版本待确认。批准后会为这一版写入批准证明并转为正式内容；文件变化后需重新确认。此操作不会创建飞书任务。</p></div>' +
    (contentItems.length === 0
      ? '<div class="empty"><p>没有待确认的正式内容。</p></div>'
      : contentItems.map(contentCard).join('')) +
    '</section>';
  // 「一键拒绝过期项」不受当前筛选/选择影响；必须先显示真实范围，且无可拒绝项时不可点。
  const expiredCount = allEntries.filter((entry) =>
    entry.decision === 'pending' && !!entry.due_date && !!today && entry.due_date < today,
  ).length;
  return (
    '<div class="review-toolbar">' +
    '<div><h3 class="section-title" style="margin:0">会议提取待确认</h3>' +
    '<p class="hint">' + pending + ' 条待确认 · 「✓ 批准」只做标记，点「应用（写回）」才会真正写入项目/创建飞书任务 · 截止早于今天的可用「一键拒绝过期项」清理</p>' +
    '<p class="hint review-howto"><strong>怎么读这一页：</strong>' +
    '灰标签是 AI 判断的类型——<strong>决策</strong>是会上说定的结论（只需落点，不需要截止日期）；' +
    '<strong>行动项</strong>是某人要做的事（通常要给目标项目 + 截止日期）。' +
    '显示「未定」表示 AI 没给出目标项目，按设计先落全局 inbox；要归到具体项目请点「修改」填目标项目。' +
    '批准按钮被禁用是因为缺依据或落点，点「修改」补齐即可。点「来源」可回看原文核对 AI 有没有编。</p>' + applyNudge + '</div>' +
    '<div class="form-row">' +
    '<button class="ghost" data-action="reject-expired"' + (expiredCount === 0 ? ' disabled' : '') +
    ' title="不受当前筛选影响：把截止日期早于今天的待确认条目全部置为拒绝（当前 ' + expiredCount + ' 条）">一键拒绝过期项（' + expiredCount + '）</button>' +
    '<button class="primary" data-action="plan">检查并写回</button>' +
    '</div></div>' +
    errorsHtml +
    contentReviewHtml +
    selectionToolbar +
    externalHtml +
    '<div id="review-groups">' + groupsHtml + '</div>' +
    projectOptions +
    '<div id="plan-result"></div>'
  );
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  'project-main': '项目主页', note: '知识页', decision: '业务决定',
  'meeting-note': '会议纪要', 'long-form-thought': '工作思考',
  'work-log': '工作日志', 'thread-doc': '工作材料', 'weekly-review': '周复盘',
};

function contentCard(item: PendingContent): string {
  const draftHint = /待核对|待结算|草稿/.test(item.title + item.summary)
    ? '<p class="content-review-draft">提示：这份内容标记了待核对事项，请先确认它已具备正式批准条件。</p>'
    : '';
  return '<article class="card content-review-card" data-content-path="' + esc(item.path) + '">' +
    '<div class="entry-top"><span class="kind">' + esc(CONTENT_TYPE_LABELS[item.content_type] ?? item.content_type) + '</span>' +
    '<span class="badge pending">待确认</span></div>' +
    '<h4>' + esc(item.title) + '</h4>' +
    '<p class="meta">' + esc(item.path) + '</p>' +
    (item.summary ? '<p>' + esc(item.summary) + '</p>' : '') + draftHint +
    '<details class="content-review-details"><summary>查看完整正文</summary><pre>' + esc(item.body) + '</pre></details>' +
    (item.content_type === 'meeting-note'
      ? '<form class="pending-meeting-date-form" data-path="' + esc(item.path) + '" data-digest="' + esc(item.content_sha256) + '" data-title="' + esc(item.title) + '">' +
        '<label>会议日期 <input type="date" name="date" value="' + esc(item.date) + '" required></label>' +
        '<button class="ghost" type="submit">保存日期（纪要继续待审）</button></form>'
      : '') +
    '<div class="row"><button class="ok" type="button" data-action="content-approve" data-path="' + esc(item.path) +
    '" data-digest="' + esc(item.content_sha256) + '" data-title="' + esc(item.title) + '">批准当前版本</button></div>' +
    '</article>';
}

export { reviewHtml as default };
