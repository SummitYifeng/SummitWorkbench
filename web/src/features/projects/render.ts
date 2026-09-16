import { esc, inlineMd, mdToHtml } from '../../md';
import type { ProjectListFilter, ProjectState, ProjectView } from './types';

/** 'YYYY-MM-DD' 差值（天）；任一非法返回 -1。 */
function dayDiff(later: string | null | undefined, earlier: string | null | undefined): number {
  if (!later || !earlier) return -1;
  const a = Date.parse(later + 'T00:00:00Z');
  const b = Date.parse(earlier + 'T00:00:00Z');
  if (Number.isNaN(a) || Number.isNaN(b)) return -1;
  return Math.round((a - b) / 86400000);
}

/** 项目展示名：优先 frontmatter title（显示名），否则用规范 ID。 */
export function projectDisplayName(p: ProjectState): string {
  return (p.title && p.title.trim()) || p.name;
}

function projectChips(p: ProjectState, today: string): string[] {
  const chips: string[] = [];
  if (p.is_thread) {
    chips.push('知识线程');
    // P1 语义拆分：展示「最近活跃」用 activity_at（日志/产物等机器活动痕迹）；
    // 「>14 天未更新」停滞提示仍读 updated（实质更新），避免被高频机器活动刷失明。
    const recent = p.activity_at || p.updated;
    if (recent) chips.push('最近活跃 ' + recent);
    if (p.updated) {
      const stale = dayDiff(today, p.updated);
      if (p.status === 'active' && stale > 14) chips.push('⚠ ' + stale + ' 天未更新');
    }
    return chips;
  }
  if (p.dirty) chips.push('未提交改动');
  if (p.behind > 0) chips.push('落后 ' + p.behind + ' 提交');
  if (p.ahead > 0) chips.push('领先 ' + p.ahead + ' 提交');
  if (p.inbox_pending > 0) chips.push(p.inbox_pending + ' 条 inbox');
  if (p.git_error) chips.push('git 异常');
  return chips;
}

function projectChipsHtml(chips: string[]): string {
  return chips.length
    ? '<div class="chips">' + chips.map((c) => '<span class="chip">' + esc(c) + '</span>').join('') + '</div>'
    : '';
}

function projectNextStepHtml(nextStep: string | null): string {
  return nextStep
    ? '<div class="project-step"><span class="step-label">下一步</span><span class="step-text">' + inlineMd(nextStep) + '</span></div>'
    : '';
}

/** 推进卡与项目行共用的两个快捷动作（同一批动作只维护一份文案与 DOM）。 */
function projectQuickActions(name: string, extraClass = ''): string {
  const cls = 'ghost' + (extraClass ? ' ' + extraClass : '');
  return '<button class="' + cls + '" data-action="open-log" data-project="' + esc(name) + '" title="追加推进日志">✎ 日志</button>' +
    '<button class="' + cls + '" data-action="open-artifact" data-project="' + esc(name) + '" title="把 AI 产物存入本线程/项目档案">存产物</button>';
}

function projectCard(p: ProjectState, today: string): string {
  const chips = projectChips(p, today);
  const chipsHtml = chips.length
    ? projectChipsHtml(chips)
    : '<span class="project-clear-state">未发现同步提醒</span>';
  const step = projectNextStepHtml(p.next_step) ||
    '<div class="project-step muted-step"><span class="step-label">下一步</span><span class="step-text">主笔记还没写下一步</span></div>';
  const quick = p.registered ? projectQuickActions(p.name, 'card-quick') : '';
  return (
    '<div class="card project' + (p.dirty || p.behind > 0 || p.inbox_pending > 0 ? ' attention' : '') + '">' +
    '<div class="card-head"><button class="project-name project-link" data-action="open-view" data-name="' + esc(p.name) + '" title="打开线视图">' + esc(projectDisplayName(p)) + '</button>' + chipsHtml + '</div>' +
    step +
    '<div class="card-foot">' + quick +
    '<button class="ghost card-archive" data-action="project-archive" data-name="' + esc(p.name) + '" data-confirm="1">归档</button>' +
    '</div>' +
    '</div>'
  );
}

function isOnHome(p: ProjectState): boolean {
  return p.registered && p.status === 'active';
}

function isNewProject(p: ProjectState): boolean {
  return !p.registered;
}

function projectStatusBadge(p: ProjectState): string {
  if (!p.registered) return '<span class="badge is-new">新</span>';
  if (p.status === 'active') return '<span class="badge is-home">在工作台</span>';
  if (p.status === 'archived') return '<span class="badge is-archived">已归档</span>';
  return '<span class="badge is-archived">' + esc(p.status ?? '未知') + '</span>';
}

export function projectsHtml(projects: ProjectState[], today: string): string {
  const onHome = projects.filter(isOnHome);
  const fresh = projects.filter(isNewProject);
  // 2026-09-14：只有已归档项目时也要保留这一节（含「管理全部 →」入口），
  // 否则首页会整块消失、看不到任何入口；原先的 emptyNote 在该分支永远不可达。
  if (projects.length === 0) return '';
  // 未建档的文件夹没有档案 title，只能显示文件夹名；加一个「（未命名文件夹）」前缀说明它是什么，
  // 免得一屏里中文名（卡片）与英文文件夹名（横幅）混在一起看不出关系。
  const freshRows = fresh.map((p) => {
    const named = !!(p.title && p.title.trim());
    return '<div class="new-project-row"><span class="project-name">' +
      (named ? esc(projectDisplayName(p)) : '（未命名文件夹）') + '</span>' +
      (named ? '' : '<span class="hint">' + esc(p.name) + '</span>') +
      '<span class="row-actions">' +
      '<button class="ok" data-action="project-activate" data-name="' + esc(p.name) + '">加入工作台</button>' +
      '<button class="ghost" data-action="project-archive" data-name="' + esc(p.name) + '">归档</button>' +
      '</span></div>';
  }).join('');
  const banner = fresh.length
    ? '<div class="new-projects"><div class="new-projects-head">' +
      '<strong>新文件夹</strong>' +
      '<span class="hint">尚未建立项目档案 · 加入工作台后才会出现在上方推进卡</span></div>' +
      freshRows +
      '</div>'
    : '';
  const emptyNote = onHome.length === 0
    ? '<div class="empty"><p>' +
      (fresh.length
        ? '工作台上还没有项目——加入上方新文件夹，或在「项目」页管理。'
        : '当前没有在工作中显示的项目（可能都已归档）。点「管理全部 →」查看或恢复。') +
      '</p></div>'
    : '';
  return (
    '<section class="block">' +
    '<div class="section-head"><h3 class="section-title">项目推进</h3>' +
    '<button class="ghost" data-action="goto-projects">管理全部 →</button></div>' +
    banner +
    onHome.map((p) => projectCard(p, today)).join('') +
    emptyNote +
    '</section>'
  );
}

function projectRow(p: ProjectState, today: string): string {
  const chipsHtml = projectChipsHtml(projectChips(p, today));
  const step = projectNextStepHtml(p.next_step);
  const action = isOnHome(p)
    ? '<button class="ghost" data-action="project-archive" data-name="' + esc(p.name) + '">归档</button>'
    : '<button class="ghost" data-action="project-activate" data-name="' + esc(p.name) + '">加入工作台</button>';
  const quick = p.registered ? projectQuickActions(p.name) : '';
  return (
    '<div class="card project-row">' +
    '<div class="project-row-main">' +
    '<div class="project-row-title"><button class="project-name project-link" data-action="open-view" data-name="' + esc(p.name) + '" title="打开线视图">' + esc(projectDisplayName(p)) + '</button>' + projectStatusBadge(p) + '</div>' +
    chipsHtml +
    step +
    '</div>' +
    '<div class="project-row-actions">' + quick + action + '</div>' +
    '</div>'
  );
}

/** 项目页内详情：保留档案区块与时间线，不再依赖通用弹层容器。 */
export function projectDetailHtml(v: ProjectView, backLabel = '返回项目列表'): string {
  const order = ['当前状态', '下一步', '阻塞', '跟进事项', '决策记录'];
  const blockSections = order.map((label) => {
    const lines = v.blocks[label] ?? [];
    if (lines.length === 0) return '';
    // 区块正文是**逐行原始 Markdown**（粗体/代码/wikilink/有序列表/表格/软换行），
    // 交给共用的子集渲染器，而不是 esc 后一行塞一个 <li>——否则档案页会显示成源码。
    const body = mdToHtml(lines.join('\n'));
    const extra = label === '跟进事项' && v.followup_pending > 0
      ? ' <span class="badge warn">' + v.followup_pending + ' 条待闭环</span>' : '';
    // 表格在双列网格里会被挤扁：含表格的区块横跨整行。
    const wide = body.includes('<table') ? ' pv-block-wide' : '';
    return '<div class="pv-block' + wide + '"><h4>' + esc(label) + extra + '</h4>' + body + '</div>';
  }).join('');
  const timeline = v.timeline.length
    ? '<ul class="pv-timeline">' + v.timeline.map((t) =>
        '<li class="tl-kind-' + esc(t.kind) + '">' +
        '<span class="tl-date">' + esc(t.date) + '</span>' +
        '<span class="tl-label">' + esc(t.label) + '</span>' +
        '<span class="tl-title">' + inlineMd(t.title) + '</span>' +
        (t.snippet ? '<div class="tl-snippet">' + inlineMd(t.snippet) + '</div>' : '') +
        '</li>'
      ).join('') + '</ul>'
    : '<p class="hint">还没有推进日志/产物/关联会议——用下方「✎ 日志」「存产物」开始积累。</p>';
  const inboxNote = v.inbox_pending > 0
    ? '<p class="hint">📥 线程 inbox 有 ' + v.inbox_pending + ' 条待处理</p>' : '';
  const statusBadge = v.status === 'archived' ? '已归档' : '在工作台';
  const disp = (v.title && v.title.trim()) || v.name;
  return (
    '<section class="pv project-detail" aria-labelledby="pv-title">' +
    '<div class="pv-return"><button class="ghost" data-action="project-detail-back">← ' + esc(backLabel) + '</button></div>' +
    '<div class="pv-head">' +
    '<div><h3 class="project-name" id="pv-title">' + esc(disp) + '</h3>' +
    (disp !== v.name ? '<div class="hint">档案 ID：' + esc(v.name) + '</div>' : '') +
    '<div class="hint">状态：' + esc(statusBadge) + (v.updated ? ' · 更新于 ' + esc(v.updated) : '') + '</div>' +
    inboxNote + '</div>' +
    '<div class="row">' +
    '<button class="ok" data-action="pv-log" title="追加推进日志">✎ 日志</button>' +
    '<button class="ghost" id="pv-rename" title="修改显示名（不改档案 ID / 文件夹 / git）">✎ 显示名</button>' +
    '<button class="ghost" data-action="pv-artifact" title="把 AI 产物存入本档案">存产物</button>' +
    '<button class="ghost" data-action="pv-refresh" title="重新加载">↻ 刷新</button>' +
    '</div></div>' +
    '<div class="pv-blocks">' + blockSections + '</div>' +
    '<div class="pv-timeline-wrap"><h4>时间线</h4>' + timeline + '</div>' +
    '</section>'
  );
}

export function projectsListHtml(
  query: string,
  projects: ProjectState[],
  today: string,
  loaded: boolean,
  filter: ProjectListFilter = 'all',
): string {
  if (!loaded) return '<div class="loading">加载中…</div>';
  const q = query.trim().toLowerCase();
  const matchesFilter = (p: ProjectState): boolean =>
    filter === 'all' ||
    (filter === 'active' && isOnHome(p)) ||
    (filter === 'new' && isNewProject(p)) ||
    (filter === 'archived' && p.status === 'archived');
  const matched = projects.filter((p) => matchesFilter(p) &&
    (!q || p.name.toLowerCase().includes(q) || projectDisplayName(p).toLowerCase().includes(q)));
  if (matched.length === 0) {
    // 空状态必须说清「为什么空」：搜索无命中、筛选到某一类、还是真的没有项目。
    const reason = q
      ? '没有匹配「' + esc(q) + '」的项目'
      : filter === 'archived'
        ? '还没有已归档的项目'
        : filter === 'new'
          ? '没有未建档的新文件夹'
          : filter === 'active'
            ? '工作台上还没有项目'
            : '暂无项目文件夹';
    const retry = q || filter !== 'all'
      ? '<p class="hint">可以清空搜索框，或把筛选切回「全部项目」。</p>'
      : '';
    return '<div class="empty"><p>' + reason + '</p>' + retry + '</div>';
  }
  const rank = (p: ProjectState): number => (isOnHome(p) ? 0 : isNewProject(p) ? 1 : 2);
  const sorted = [...matched].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  return sorted.map((p) => projectRow(p, today)).join('');
}
