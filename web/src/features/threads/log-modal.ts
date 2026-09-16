import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { clearEntityDraft, loadEntityDraft } from '../../lifecycle/drafts';
import { esc } from '../../md';
import { projectDisplayName } from '../projects';
import type { ProjectState } from '../projects/types';
import { closeModal, openModal, rejectOversizeText, toast } from '../shell';
import { getThreadsDeps } from './deps';
import type { LogDraft } from './types';

/** 追加推进日志弹层（原 legacy-main 逐条搬迁）。 */

/**
 * 项目勾选清单的纯渲染（不碰 DOM，便于单测直接断言）。
 *
 * 口径（2026-09-14）：**一项一行、占满整宽**——勾选框 + 中文显示名；
 * 英文项目 ID 与「知识线程 / 文件夹项目」只进 `title`（hover 可见）。
 * 原先一格塞「中文名 + 英文 ID + (线程)」三段的窄网格会错行、中英挤在一起。
 */
export function logProjectChoices(projects: ProjectState[], selected: string[]): string {
  const rows = (items: ProjectState[]) => items
    .map((p) => {
      const label = projectDisplayName(p);
      const kind = p.is_thread ? '知识线程' : '文件夹项目';
      const hint = label === p.name ? kind : label + '（' + p.name + '）· ' + kind;
      return (
        '<label class="log-proj" title="' + esc(hint) + '">' +
        '<input type="checkbox" name="log-proj" value="' + esc(p.name) + '"' +
        (selected.includes(p.name) ? ' checked' : '') + '>' +
        '<span class="log-proj-name">' + esc(label) + '</span>' +
        '</label>'
      );
    })
    .join('');
  const active = projects.filter((p) => p.status !== 'archived');
  const archived = projects.filter((p) => p.status === 'archived');
  return rows(active) + (archived.length
    ? '<details class="log-archived"><summary>已归档 ' + archived.length + '</summary>' + rows(archived) + '</details>'
    : '');
}

/** 追加推进日志弹窗：多选关联线程/项目 + 粘贴文本 → AI 消化入各线程。 */
export function openLogModal(defaultProject: string): void {
  const registered = (getThreadsDeps()?.projects() ?? []).filter((p) => p.registered);
  const saved = loadEntityDraft<LogDraft>('log:' + defaultProject, Date.now(), getThreadsDeps()?.workspaceId());
  const selectedProjects = saved?.projects ?? (defaultProject ? [defaultProject] : []);
  const boxes = logProjectChoices(registered, selectedProjects);
  openModal(
    '<h3>追加推进日志</h3>' +
    '<p class="hint">粘贴一段推进/沟通摘录/跟进（文本即可，语音请先自行转写）。可勾选多个关联的线程或项目；' +
    'AI 会整理摘要并归入各线程。模型不可用时只存原文，绝不丢。</p>' +
    '<form id="log-form">' +
    '<input id="log-project-search" type="search" placeholder="搜索项目名或 ID…" autocomplete="off">' +
    '<p class="hint">已选择 <span id="log-project-count">' + selectedProjects.length + '</span> 个项目</p>' +
    '<div class="log-projs">' + (boxes || '<span class="hint">还没有已建档的项目，先在「项目」页建档。</span>') + '</div>' +
    '<textarea id="log-text" rows="8" required placeholder="今天和木子/冯老师沟通了什么、定了什么、下一步做什么…">' +
    esc(saved?.text ?? '') + '</textarea>' +
    '<div class="row"><button class="primary" type="submit">保存日志</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  const modal = document.getElementById('modal') as HTMLElement | null;
  if (modal) {
    modal.dataset.draftEntity = 'log:' + defaultProject;
    modal.dataset.draftDirty = saved ? '1' : '0';
  }
  const persistLogDraft = (): void => {
    const text = (document.getElementById('log-text') as HTMLTextAreaElement | null)?.value ?? '';
    const projects = Array.from(document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]:checked')).map((i) => i.value);
    getThreadsDeps()?.persistEntityDraft('log:' + defaultProject, { projects, text });
  };
  const search = document.getElementById('log-project-search') as HTMLInputElement | null;
  search?.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    const archivedGroup = document.querySelector<HTMLDetailsElement>('#log-form .log-archived');
    if (archivedGroup) archivedGroup.open = !!query;
    document.querySelectorAll<HTMLElement>('#log-form .log-proj').forEach((row) => {
      const input = row.querySelector<HTMLInputElement>('input[name="log-proj"]');
      const searchable = (row.textContent ?? '') + ' ' + (input?.value ?? '');
      row.hidden = !!query && !searchable.toLowerCase().includes(query);
    });
  });
  const updateCount = (): void => {
    const count = document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]:checked').length;
    const countEl = document.getElementById('log-project-count');
    if (countEl) countEl.textContent = String(count);
  };
  document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]').forEach((input) => input.addEventListener('change', updateCount));
  document.getElementById('log-form')?.addEventListener('input', persistLogDraft);
  document.getElementById('log-form')?.addEventListener('change', persistLogDraft);
  document.getElementById('log-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitLog();
  });
}

let logSubmitting = false;

export async function submitLog(): Promise<void> {
  if (logSubmitting) return;
  const text = ((document.getElementById('log-text') as HTMLTextAreaElement | null)?.value ?? '').trim();
  const projects = Array.from(
    document.querySelectorAll<HTMLInputElement>('#log-form input[name="log-proj"]:checked')
  ).map((i) => i.value);
  if (!text) {
    toast('日志内容为空', 'err');
    return;
  }
  if (rejectOversizeText(text)) return;
  if (projects.length === 0) {
    toast('至少勾选一个线程/项目', 'err');
    return;
  }
  logSubmitting = true;
  const submitButton = document.querySelector<HTMLButtonElement>('#log-form button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/threads/logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projects, text }),
    }));
    if (r.ok) {
      const entity = document.getElementById('modal')?.dataset.draftEntity;
      if (entity) clearEntityDraft(entity, getThreadsDeps()?.workspaceId());
      closeModal();
    }
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(err, 'err');
  } finally {
    logSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}
