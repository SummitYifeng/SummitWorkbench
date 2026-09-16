import { esc } from '../../md';
import { closeModal, openModal, rejectOversizeText } from '../shell';
import { api, mutation, refreshState, renderToday, toast } from './deps';
import { todayUi } from './state';
import type { ImportReceipt, TodayActions } from './types';

/** 「今日」页写回动作（原 legacy-main 逐条搬迁，Step 8d）。 */

export function createTodayActions(view: HTMLElement): TodayActions {
  return {
    capture: async (text) => {
      if (todayUi.capturing) return { ok: false };
      if (rejectOversizeText(text)) return { ok: false };
      todayUi.capturing = true;
      renderToday(view);
      try {
        const result = await mutation(() => api<{ ok: boolean; message: string }>('/api/capture', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        }));
        toast(result.message, result.ok ? 'ok' : 'err');
        return { ok: result.ok };
      } catch (err) {
        toast(err, 'err');
        return { ok: false };
      } finally {
        todayUi.capturing = false;
        renderToday(view);
      }
    },
    importFiles: async (files) => {
      if (todayUi.importing || files.length === 0) return;
      const supported = files.filter((file) => file.name.toLowerCase().endsWith('.md') || file.name.toLowerCase().endsWith('.txt'));
      const unsupported = files.filter((file) => !supported.includes(file));
      if (unsupported.length) {
        todayUi.importResults = todayUi.importResults.concat(unsupported.map((file) => ({
          fileName: file.name,
          bytes: file.size,
          status: 'error' as const,
          message: '仅支持 .md / .txt 逐字稿文件',
        })));
      }
      if (supported.length === 0) {
        renderToday(view);
        return;
      }
      if (supported.length > 1) toast('已加入 ' + supported.length + ' 个文件，将按顺序处理', 'info');
      todayUi.importing = true;
      const start = todayUi.importResults.length;
      todayUi.importResults = todayUi.importResults.concat(supported.map((file) => ({
        fileName: file.name,
        bytes: file.size,
        status: 'processing' as const,
        message: '排队中…',
      })));
      renderToday(view);
      for (const [offset, file] of supported.entries()) {
        const receiptIndex = start + offset;
        todayUi.importResults[receiptIndex] = { ...todayUi.importResults[receiptIndex], message: '正在处理…' };
        renderToday(view);
        const form = new FormData();
        form.append('file', file);
        try {
          const result = await mutation(() => api<{
            ok: boolean;
            status?: 'success' | 'partial' | 'failed';
            message: string;
            details?: string[];
            estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
          }>('/api/meetings/import', {
            method: 'POST', body: form,
          }));
          const status: ImportReceipt['status'] = result.status === 'partial'
            ? 'partial' : result.status === 'failed' || !result.ok ? 'error' : 'success';
          todayUi.importResults[receiptIndex] = {
            fileName: file.name,
            bytes: file.size,
            status,
            message: result.message,
            details: result.details,
            estimate: result.estimate,
          };
          toast(result.message, status === 'success' ? 'ok' : status === 'partial' ? 'info' : 'err');
        } catch (err) {
          todayUi.importResults[receiptIndex] = { fileName: file.name, bytes: file.size, status: 'error', message: String(err) };
          toast(err, 'err');
        }
        renderToday(view);
      }
      todayUi.importing = false;
      renderToday(view);
      void refreshState();
    },
    toggleImport: (open) => { todayUi.importOpen = open; },
    refresh: () => { void refreshState(); },
  };
}

export async function runBrief(): Promise<void> {
  toast('正在生成今日简报…', 'info');
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>(
      '/api/run/brief', { method: 'POST' }, { timeoutMs: 300_000 },
    ));
    toast(r.message, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast(err, 'err');
  }
  void refreshState();
}

/** 「今日」待办任务行的一键完成：写回飞书成功后刷新（快照镜像 → 行消失、进「最近完成」）。 */
export async function completeTask(btn: HTMLElement): Promise<void> {
  const guid = btn.dataset.task ?? '';
  const row = btn.closest<HTMLElement>('.bf-task');
  if (!guid || !row) return;
  const doneBtn = btn as HTMLButtonElement;
  doneBtn.disabled = true;
  doneBtn.classList.add('busy');
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>('/api/tasks/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: guid }),
    }));
    toast(r.message, r.ok ? 'ok' : 'err');
    if (!r.ok) {
      doneBtn.disabled = false;
      doneBtn.classList.remove('busy');
      return;
    }
    void refreshState();
  } catch (err) {
    toast(err, 'err');
    doneBtn.disabled = false;
    doneBtn.classList.remove('busy');
  }
}

/** 打开任务/会议的行内编辑弹窗（改动直接写回飞书本体）。 */
export function openRowEditModal(kind: 'task' | 'meeting', seed: Record<string, string>): void {
  const hint = kind === 'task'
    ? '<p class="hint">改动直接写回飞书任务本体；清空截止 = 移除截止日期。</p>'
    : '<p class="hint">改动直接写回飞书日历事件（个人日程，不邀请他人）。</p>';
  const body = kind === 'task'
    ? '<label>标题</label><input id="row-edit-summary" required value="' + esc(seed.title ?? '') + '">' +
      '<div class="form-row"><label>截止日期</label><input id="row-edit-due" type="date" value="' +
      esc(seed.due ?? '') + '"></div>'
    : '<label>标题</label><input id="row-edit-summary" required value="' + esc(seed.title ?? '') + '">' +
      '<div class="grid2">' +
      '<div><label>开始时间</label><input id="row-edit-start" type="datetime-local" required value="' +
      esc(seed.start ?? '') + '"></div>' +
      '<div><label>结束时间</label><input id="row-edit-end" type="datetime-local" required value="' +
      esc(seed.end ?? '') + '"></div>' +
      '</div>';
  openModal(
    '<h3>' + (kind === 'task' ? '编辑任务' : '编辑会议') + '</h3>' + hint +
    '<form id="row-edit-form">' + body +
    '<div class="row"><button class="primary" type="submit">保存</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>'
  );
  const form = document.getElementById('row-edit-form') as HTMLFormElement | null;
  form?.addEventListener('submit', (ev) => {
    ev.preventDefault();
    void submitRowEdit(kind, seed.id ?? '');
  });
}

/** 行内编辑提交：任务/会议 → PATCH 写回飞书 + 快照镜像 → 刷新「今日」。 */
let rowEditSubmitting = false;

async function submitRowEdit(kind: 'task' | 'meeting', id: string): Promise<void> {
  if (rowEditSubmitting) return;
  if (!id) {
    toast('缺少目标 id', 'err');
    return;
  }
  const summaryInput = document.getElementById('row-edit-summary') as HTMLInputElement | null;
  const summary = (summaryInput?.value ?? '').trim();
  if (!summary) {
    toast('标题不能为空', 'err');
    return;
  }
  const url = kind === 'task' ? '/api/tasks/update' : '/api/meetings/update';
  const body: Record<string, string> = kind === 'task'
    ? {
        task_id: id,
        summary,
        due_date: (document.getElementById('row-edit-due') as HTMLInputElement | null)?.value ?? '',
      }
    : {
        event_id: id,
        summary,
        start_at: (document.getElementById('row-edit-start') as HTMLInputElement | null)?.value ?? '',
        end_at: (document.getElementById('row-edit-end') as HTMLInputElement | null)?.value ?? '',
      };
  // 双击「保存」不能对飞书本体发出两次 PATCH。
  rowEditSubmitting = true;
  const submitButton = document.querySelector<HTMLButtonElement>('#row-edit-form button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  try {
    const r = await mutation(() => api<{ ok: boolean; message: string }>(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
    closeModal();
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) void refreshState();
  } catch (err) {
    toast(err, 'err');
  } finally {
    rowEditSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}
