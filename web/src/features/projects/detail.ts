import { api, isStaleWorkspaceResponse } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { esc } from '../../md';
import { focusVisibleProjectLink, toast, type ShellTab } from '../shell';
import { openArtifactModal } from '../threads';
import { openLogModal } from '../threads';
import { getProjectDeps } from './deps';
import { projectDetailHtml, projectDisplayName, projectsListHtml } from './render';
import type { ProjectListFilter, ProjectState, ProjectView } from './types';

/** 项目页装配与详情导航（原 legacy-main 逐条搬迁）。 */

/** 组合根扇出的看板快照（只取本模块需要的字段，避免 import legacy-main，§4.1 硬规则 2）。 */
interface ProjectsSnapshot {
  day: string;
  projects: ProjectState[];
}

export let projectDetail: ProjectView | null = null;
export let projectDetailLoading = false;
export let projectDetailError: string | null = null;
export let projectDetailName = '';
export let projectListQuery = '';
export let projectListFilter: ProjectListFilter = 'all';
export interface ProjectReturnContext {
  tab: ShellTab;
  query: string;
  filter: ProjectListFilter;
  scrollY: number;
}
export let projectReturnContext: ProjectReturnContext | null = null;
export let projectFocusAfterRenderName: string | null = null;
export let latestProjectViewRequest = 0;

export function renderProjects(view: HTMLElement, state: ProjectsSnapshot | null): void {
  if (!state) {
    view.innerHTML = '<div class="loading">加载中…</div>';
    return;
  }
  if (projectDetailLoading) {
    // 加载态显示中文显示名，而不是项目 ID（ID 在详情页里另有「档案 ID」一行）。
    const known = state.projects.find((p) => p.name === projectDetailName);
    const loadingName = known ? projectDisplayName(known) : projectDetailName;
    view.innerHTML = '<div class="section-head"><button class="ghost" data-action="project-detail-back">← 返回项目</button></div>' +
      '<div class="loading">正在读取「' + esc(loadingName) + '」详情…</div>';
    return;
  }
  if (projectDetail) {
    view.innerHTML = projectDetailHtml(
      projectDetail,
      projectReturnContext?.tab === 'today' ? '返回今日' : '返回项目列表',
    );
    bindProjectDetail(view, projectDetail);
    return;
  }
  if (projectDetailError) {
    view.innerHTML = '<div class="empty load-error"><p>项目详情读取失败：' + esc(projectDetailError) + '</p>' +
      '<button class="ghost" data-action="project-detail-back">返回项目</button></div>';
    return;
  }
  const projects = state.projects;
  const today = state.day;
  const query = projectListQuery;
  const total = projects.length;
  const onHome = projects.filter((p) => p.registered && p.status === 'active').length;
  const fresh = projects.filter((p) => !p.registered).length;
  const archived = projects.filter((p) => p.status === 'archived').length;
  view.innerHTML =
    '<div class="section-head"><div><h3 class="section-title">全部项目</h3>' +
    '<span class="hint">共 ' + total + ' · 在工作台 ' + onHome + ' · 新 ' + fresh + ' · 已归档 ' + archived + '</span></div>' +
    '<div class="row project-global-actions"><button class="ok" data-action="open-log" data-project="">✎ 追加日志</button>' +
    '<button class="ghost" data-action="open-artifact" data-project="">存产物</button></div></div>' +
    '<div class="project-toolbar">' +
    '<input id="project-search" type="search" placeholder="搜索项目名…" value="' + esc(query) + '">' +
    '<label class="project-filter"><span class="hint">显示</span><select id="project-status-filter">' +
    '<option value="all"' + (projectListFilter === 'all' ? ' selected' : '') + '>全部项目</option>' +
    '<option value="active"' + (projectListFilter === 'active' ? ' selected' : '') + '>在工作台</option>' +
    '<option value="new"' + (projectListFilter === 'new' ? ' selected' : '') + '>新文件夹</option>' +
    '<option value="archived"' + (projectListFilter === 'archived' ? ' selected' : '') + '>已归档</option>' +
    '</select></label>' +
    '<details class="thread-create" title="业务线程不需要 Work 文件夹/git 仓库，直接在 vault 建档">' +
    '<summary class="ghost">＋ 新建知识线程</summary>' +
    '<form class="thread-create-form">' +
    '<input name="project_id" placeholder="项目 ID，如 finance-ops" required pattern="[A-Za-z0-9_-]+" title="字母/数字/下划线/连字符">' +
    '<p class="hint">项目 ID 是文件夹 / 档案名（英文小写，别用中文）；界面上一律显示档案里的中文名。</p>' +
    '<input name="aliases" placeholder="别名（逗号分隔，可选）：财务运营, Finance Ops">' +
    '<button class="ok" type="submit">建档</button>' +
    '</form></details>' +
    '</div>' +
    '<div id="projects-list"></div>';
  const listEl = document.getElementById('projects-list') as HTMLElement;
  listEl.innerHTML = projectsListHtml(query, projects, today, true, projectListFilter);
  revealQueuedProjectFocus();
  const search = view.querySelector<HTMLInputElement>('#project-search');
  search?.addEventListener('input', () => {
    projectListQuery = search.value;
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(projectListQuery, projects, today, true, projectListFilter);
  });
  view.querySelector<HTMLSelectElement>('#project-status-filter')?.addEventListener('change', (event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (value !== 'all' && value !== 'active' && value !== 'new' && value !== 'archived') return;
    projectListFilter = value;
    const el = document.getElementById('projects-list');
    if (el) el.innerHTML = projectsListHtml(projectListQuery, projects, today, true, projectListFilter);
  });
}

export function bindProjectDetail(container: HTMLElement, current: ProjectView): void {
  container.querySelector('[data-action="pv-refresh"]')?.addEventListener('click', () => { void showProjectView(current.name); });
  container.querySelector('[data-action="pv-log"]')?.addEventListener('click', () => openLogModal(current.name));
  container.querySelector('[data-action="pv-artifact"]')?.addEventListener('click', () => openArtifactModal(current.name));
  const renameBtn = container.querySelector<HTMLButtonElement>('#pv-rename');
  renameBtn?.addEventListener('click', () => {
    const titleBox = container.querySelector('#pv-title');
    if (!titleBox) return;
    const cur = (current.title && current.title.trim()) || current.name;
    const wrap = document.createElement('div');
    wrap.className = 'pv-rename';
    const input = document.createElement('input');
    input.value = cur;
    input.maxLength = 60;
    input.placeholder = '显示名（如：活满报名系统）';
    const save = document.createElement('button');
    save.className = 'ok';
    save.type = 'button';
    save.textContent = '保存';
    const cancel = document.createElement('button');
    cancel.className = 'ghost';
    cancel.type = 'button';
    cancel.textContent = '取消';
    wrap.append(input, save, cancel);
    titleBox.replaceWith(wrap);
    input.focus();
    input.select();
    const reload = (): void => { void showProjectView(current.name); };
    const commit = (): void => {
      const value = input.value.trim();
      if (!value) {
        toast('显示名不能为空', 'err');
        return;
      }
      void mutation(async () => {
        const r = await api<{ ok: boolean; message: string }>('/api/projects/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: current.name, title: value }),
        });
        toast(r.message, r.ok ? 'ok' : 'err');
        if (r.ok) {
          reload();
          void getProjectDeps()?.refreshState();
        }
      }).catch((err: unknown) => toast(err, 'err'));
    };
    save.addEventListener('click', commit);
    cancel.addEventListener('click', reload);
    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        commit();
      } else if (ev.key === 'Escape') {
        reload();
      }
    });
  });
}

export async function showProjectView(name: string): Promise<void> {
  if (!name) return;
  if (!projectReturnContext) {
    projectReturnContext = {
      tab: getProjectDeps()?.currentTab() ?? 'projects',
      query: projectListQuery,
      filter: projectListFilter,
      scrollY: window.scrollY,
    };
  }
  const requestId = ++latestProjectViewRequest;
  projectDetailName = name;
  projectDetail = null;
  projectDetailError = null;
  projectDetailLoading = true;
  getProjectDeps()?.setTab('projects');
  getProjectDeps()?.render();
  window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  try {
    const next = await api<ProjectView>('/api/projects/view?name=' + encodeURIComponent(name));
    if (requestId !== latestProjectViewRequest) return;
    if (!next.ok) {
      projectDetailError = next.message ?? '打开失败';
      return;
    }
    projectDetail = next;
  } catch (err) {
    if (requestId !== latestProjectViewRequest || isStaleWorkspaceResponse(err)) return;
    projectDetailError = String(err);
  } finally {
    if (requestId === latestProjectViewRequest) {
      projectDetailLoading = false;
      if (getProjectDeps()?.currentTab() === 'projects') {
        getProjectDeps()?.render();
        document.querySelector<HTMLElement>('[data-action="project-detail-back"]')?.focus();
      }
    }
  }
}

export function backFromProjectDetail(): void {
  // 失效在途详情读取：返回/切换后，过期响应不得把详情重新推回页面。
  latestProjectViewRequest += 1;
  const context = projectReturnContext;
  const name = projectDetailName;
  projectFocusAfterRenderName = name || null;
  projectDetail = null;
  projectDetailError = null;
  projectDetailLoading = false;
  projectDetailName = '';
  projectReturnContext = null;
  getProjectDeps()?.setTab(context?.tab ?? 'projects');
  projectListQuery = context?.query ?? projectListQuery;
  projectListFilter = context?.filter ?? projectListFilter;
  getProjectDeps()?.render();
  window.setTimeout(() => {
    window.scrollTo({ top: context?.scrollY ?? 0, behavior: 'instant' as ScrollBehavior });
    if (projectFocusAfterRenderName && focusVisibleProjectLink(projectFocusAfterRenderName)) {
      projectFocusAfterRenderName = null;
    }
  }, 0);
}

/** workspace 换代时清空项目详情状态（原 doCheckVersion 内联的 8 行重置，逐字搬迁）。 */
export function resetProjectsForWorkspace(): void {
    latestProjectViewRequest += 1;
    projectDetail = null;
    projectDetailLoading = false;
    projectDetailError = null;
    projectDetailName = '';
    projectListQuery = '';
    projectListFilter = 'all';
    projectReturnContext = null;
}

/**
 * 重建项目列表后恢复"排队的"项目链接焦点。
 *
 * 组合根的 renderToday 也会重建项目行（从详情返回今日时），因此本函数对外公开：跨域读取经
 * 导出函数，而不是让 today 直接摸 project 的状态（§4.2）。
 */
export function revealQueuedProjectFocus(): void {
  if (projectFocusAfterRenderName && focusVisibleProjectLink(projectFocusAfterRenderName)) {
    projectFocusAfterRenderName = null;
  }
}
