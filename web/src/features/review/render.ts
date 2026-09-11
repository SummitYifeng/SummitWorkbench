import { projectDisplayName } from '../projects/render';
import { esc } from '../../md';
import type { ProjectState } from '../projects/types';
import type {
  ExternalAction,
  ReviewEntry,
  ReviewFilter,
  ReviewPayload,
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

function routeOptions(current: string | null): string {
  const keys = ['', 'feishu-task', 'feishu-meeting', 'project-main', 'project-followup', 'project-inbox', 'global-inbox'];
  return keys.map((k) => {
    const label = k === '' ? '（未定）' : ROUTE_LABELS[k] ?? k;
    return '<option value="' + k + '"' + (k === current ? ' selected' : '') + '>' + label + '</option>';
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

function entryCard(e: ReviewEntry, today: string, selectedIds: ReadonlySet<string>): string {
  const decision = DECISION_LABELS[e.decision] ?? e.decision;
  const kind = KIND_LABELS[e.kind] ?? e.kind;
  const expired = e.decision === 'pending' && !!e.due_date && !!today && e.due_date < today;
  const meta = [
    e.target_project ? '目标：' + esc(e.target_project) : '目标：unresolved',
    e.route ? '落点：' + (ROUTE_LABELS[e.route] ?? e.route) : '落点：未定',
    e.due_date ? '截止：' + esc(e.due_date) + (expired ? '（已过期）' : '') : '',
    e.start_at
      ? '会议时间：' + esc(e.start_at.replace('T', ' ')) + (e.end_at ? ' ~ ' + esc(e.end_at.replace('T', ' ')) : '')
      : '',
    e.evidence ? '依据：' + esc(e.evidence) : '',
    e.historical ? '历史补导' : '',
  ].filter(Boolean).join(' · ');
  const warn = e.actionable ? '' : '<div class="not-actionable">⚠ 依据或目标项目缺失，暂不可批准写回</div>';
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
    '<p class="desc">' + esc(e.description) + '</p>' +
    warn + err +
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
    '<div><label>目标项目</label><input name="target_project" list="wb-project-options" placeholder="项目 ID 或别名（如 finance-ops）；留空=全局 inbox" value="' + esc(e.target_project ?? '') + '"></div>' +
    '<div><label>落点</label><select name="route">' + routeOptions(e.route) + '</select></div>' +
    '<div><label>截止日期</label><input name="due_date" placeholder="YYYY-MM-DD" value="' + esc(e.due_date ?? '') + '"></div>' +
    '<div><label>开始时间（新建会议）</label><input name="start_at" type="datetime-local" value="' + esc(e.start_at ?? '') + '"></div>' +
    '<div><label>结束时间（新建会议）</label><input name="end_at" type="datetime-local" value="' + esc(e.end_at ?? '') + '"></div>' +
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

function renderExternalActions(actions: ExternalAction[]): string {
  if (!actions.length) return '';
  const labels: Record<string, string> = {
    prepared: '已准备', sending: '发送中', succeeded: '已创建', failed: '创建失败',
    unknown: '结果未知', 'reconciled-succeeded': '已核对创建', 'reconciled-not-found': '已核对未找到',
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
    const detail = a.error ? ' · ' + esc(a.error) : (a.remote_id ? ' · ' + esc(a.remote_id) : '');
    return '<div class="external-action-row"><span><strong>' + esc(label) + '</strong> · ' + esc(a.candidate_id) + detail + '</span><span class="row">' + controls + '</span></div>';
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
        const cards = g.entries.map((entry) => entryCard(entry, today, options.selectedIds)).join('');
        const groupPending = g.entries.filter((e) => e.decision === 'pending').length;
        const groupApprovable = g.entries.filter((e) => e.decision === 'pending' && e.actionable && !!e.route).length;
        const groupBlocked = groupPending - groupApprovable;
        const approvalTitle = groupBlocked > 0
          ? ' title="仅纳入具备依据和落点的候选；' + groupBlocked + ' 条未纳入批准"'
          : '';
        return '<div class="meeting-head">' +
          '<span class="meeting-date">' + esc(g.meeting_date) + '</span>' +
          '<span class="meeting-title">' + esc(g.meeting_title) + '</span>' +
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
  // 「一键拒绝过期项」不受当前筛选/选择影响；必须先显示真实范围，且无可拒绝项时不可点。
  const expiredCount = allEntries.filter((entry) =>
    entry.decision === 'pending' && !!entry.due_date && !!today && entry.due_date < today,
  ).length;
  return (
    '<div class="review-toolbar">' +
    '<div><h3 class="section-title" style="margin:0">会议提取待确认</h3>' +
    '<p class="hint">' + pending + ' 条待确认 · 「✓ 批准」只做标记，点「应用（写回）」才会真正写入项目/创建飞书任务 · 截止早于今天的可用「一键拒绝过期项」清理</p>' + applyNudge + '</div>' +
    '<div class="form-row">' +
    '<button class="ghost" data-action="reject-expired"' + (expiredCount === 0 ? ' disabled' : '') +
    ' title="不受当前筛选影响：把截止日期早于今天的待确认条目全部置为拒绝（当前 ' + expiredCount + ' 条）">一键拒绝过期项' +
    (expiredCount > 0 ? '（' + expiredCount + '）' : '') + '</button>' +
    '<button class="primary" data-action="plan">检查并写回</button>' +
    '</div></div>' +
    errorsHtml +
    selectionToolbar +
    externalHtml +
    '<div id="review-groups">' + groupsHtml + '</div>' +
    projectOptions +
    '<div id="plan-result"></div>'
  );
}

export { reviewHtml as default };
