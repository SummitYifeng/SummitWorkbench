import { esc } from '../../md';
import type { ProjectState } from './types';

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
    ? '<div class="project-step"><span class="step-label">下一步</span><span class="step-text">' + esc(nextStep) + '</span></div>'
    : '';
}

function projectCard(p: ProjectState, today: string): string {
  const chips = projectChips(p, today);
  const chipsHtml = chips.length
    ? projectChipsHtml(chips)
    : '<span class="chip ok-chip">正常</span>';
  const step = projectNextStepHtml(p.next_step) ||
    '<div class="project-step muted-step"><span class="step-label">下一步</span><span class="step-text">主笔记还没写下一步</span></div>';
  const quick = p.registered
    ? '<button class="ghost card-quick" data-action="open-log" data-project="' + esc(p.name) + '" title="追加推进日志">✎ 日志</button>' +
      '<button class="ghost card-quick" data-action="open-artifact" data-project="' + esc(p.name) + '" title="把 AI 产物存入本线程/项目档案">存产物</button>'
    : '';
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
  const quick = p.registered
    ? '<button class="ghost" data-action="open-log" data-project="' + esc(p.name) + '" title="追加推进日志">✎ 日志</button>' +
      '<button class="ghost" data-action="open-artifact" data-project="' + esc(p.name) + '" title="把 AI 产物存入本线程/项目档案">存产物</button>'
    : '';
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

export function projectsListHtml(
  query: string,
  projects: ProjectState[],
  today: string,
  loaded: boolean,
): string {
  if (!loaded) return '<div class="loading">加载中…</div>';
  const q = query.trim().toLowerCase();
  const matched = projects.filter((p) => !q || p.name.toLowerCase().includes(q));
  if (matched.length === 0) {
    return '<div class="empty"><p>' + (q ? '没有匹配「' + esc(q) + '」的项目' : '暂无项目文件夹') + '</p></div>';
  }
  const rank = (p: ProjectState): number => (isOnHome(p) ? 0 : isNewProject(p) ? 1 : 2);
  const sorted = [...matched].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  return sorted.map((p) => projectRow(p, today)).join('');
}
