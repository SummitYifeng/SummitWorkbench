import { api } from '../../api/request';
import { mutation } from '../../lifecycle/connection';
import { clearEntityDraft, loadEntityDraft } from '../../lifecycle/drafts';
import { esc } from '../../md';
import { projectDisplayName } from '../projects';
import { closeModal, openModal, rejectOversizeText, toast } from '../shell';
import { getThreadsDeps } from './deps';
import type { LogDraft } from './types';

/** 追加推进日志弹层（原 legacy-main 逐条搬迁）。 */

/** 追加推进日志弹窗：多选关联线程/项目 + 粘贴文本 → AI 消化入各线程。 */
export function openLogModal(defaultProject: string): void {
  const registered = (getThreadsDeps()?.projects() ?? []).filter((p) => p.registered);
  const saved = loadEntityDraft<LogDraft>('log:' + defaultProject, Date.now(), getThreadsDeps()?.workspaceId());
  const selectedProjects = saved?.projects ?? (defaultProject ? [defaultProject] : []);
  const boxes = registered
    .map((p) =>
      '<label class="log-proj"><input type="checkbox" name="log-proj" value="' + esc(p.name) + '"' +
      (selectedProjects.includes(p.name) ? ' checked' : '') + '>' + esc(projectDisplayName(p)) +
      (projectDisplayName(p) !== p.name ? ' <span class="hint">' + esc(p.name) + '</span>' : '') +
      (p.is_thread ? ' <span class="hint">(线程)</span>' : '') + '</label>'
    )
    .join('');
  openModal(
    '<h3>追加推进日志</h3>' +
    '<p class="hint">粘贴一段推进/沟通摘录/跟进（文本即可，语音请先自行转写）。可勾选多个关联的线程或项目；' +
    'AI 会整理摘要并归入各线程。模型不可用时只存原文，绝不丢。</p>' +
    '<form id="log-form">' +
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
    toast(String(err), 'err');
  } finally {
    logSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}
