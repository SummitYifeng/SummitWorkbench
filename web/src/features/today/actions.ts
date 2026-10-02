import { esc } from '../../md';
import { clearServerDraft } from '../../lifecycle/server-drafts';
import { closeModal, openModal, rejectOversizeText } from '../shell';
import { api, mutation, refreshState, renderToday, toast } from './deps';
import { todayUi } from './state';
import type { ImportReceipt, TodayActions } from './types';

/** 「今日」页写回动作（原 legacy-main 逐条搬迁，Step 8d）。 */

export function createTodayActions(view: HTMLElement): TodayActions {
  const applyJob = (job: { job_id: string; file_name: string; bytes?: number; status: string; stage: string; error?: string | null; result?: { message?: string; candidates?: number } | null }): void => {
    const index = todayUi.importResults.findIndex((item) => item.jobId === job.job_id);
      const status: ImportReceipt['status'] = job.status === 'succeeded'
      ? 'success' : job.status === 'partial' ? 'partial' : job.status === 'failed' ? 'error' : 'processing';
    const message = job.error || job.result?.message || ({
      uploaded: '已上传，等待归档', archived: '已归档，等待结构化', structuring: '正在结构化…',
      candidates: '正在生成候选…', completed: '已完成',
    } as Record<string, string>)[job.stage] || '排队中…';
    const receipt: ImportReceipt = { jobId: job.job_id, fileName: job.file_name, bytes: job.bytes ?? 0, status, message };
    if (index >= 0) todayUi.importResults[index] = receipt;
    else todayUi.importResults.push(receipt);
  };
  const loadRecentImports = async (): Promise<void> => {
    try {
      const response = await api<{ ok: boolean; jobs?: any[] }>('/api/meetings/imports');
      if (!response.ok || !response.jobs) return;
      for (const job of response.jobs) applyJob(job);
      renderToday(view);
    } catch { /* 状态读取失败不应阻塞今日页 */ }
  };
  void loadRecentImports();
  const pollJob = async (jobId: string): Promise<void> => {
    const started = Date.now();
    while (true) {
      try {
        const job = await api<any>('/api/meetings/imports/' + encodeURIComponent(jobId));
        if (!job.ok) throw new Error(job.message || '任务读取失败');
        applyJob(job);
        renderToday(view);
        if (['succeeded', 'partial', 'failed'].includes(job.status)) return;
      } catch (err) {
        const index = todayUi.importResults.findIndex((item) => item.jobId === jobId);
        if (index >= 0) todayUi.importResults[index] = { ...todayUi.importResults[index], status: 'error', message: String(err) };
        return;
      }
      const delay = Date.now() - started < 30_000 ? 2_000 : 5_000;
      await new Promise<void>((resolve) => window.setTimeout(resolve, delay));
    }
  };
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
        if (result.ok) {
          try { await clearServerDraft(api, 'quick-note', 'quick'); }
          catch { /* retain the draft if cleanup cannot be confirmed */ }
        }
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
            status?: string;
            job_id?: string;
            message: string;
            details?: string[];
            estimate?: { est_cost?: number; currency?: string; crosses_soft_budget?: boolean };
          }>('/api/meetings/import', {
            method: 'POST', body: form,
          }));
          const status: ImportReceipt['status'] = result.status === 'partial'
            ? 'partial' : result.status === 'failed' || !result.ok ? 'error' : 'processing';
          todayUi.importResults[receiptIndex] = {
            jobId: result.job_id,
            fileName: file.name,
            bytes: file.size,
            status,
            message: result.job_id ? '已归档，后台继续处理' : result.message,
            details: result.details,
            estimate: result.estimate,
          };
          toast(result.message, status === 'processing' ? 'info' : status === 'partial' ? 'info' : 'err');
          if (result.job_id) await pollJob(result.job_id);
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

export async function retryImport(jobId: string): Promise<void> {
  if (!jobId) return;
  try {
    const result = await mutation(() => api<{ ok: boolean; message?: string }>('/api/meetings/imports/' + encodeURIComponent(jobId) + '/retry', { method: 'POST' }));
    if (result.ok) {
      const receipt = todayUi.importResults.find((item) => item.jobId === jobId);
      if (receipt) {
        receipt.status = 'processing';
        receipt.message = '正在继续处理失败项…';
      }
      void refreshState();
    }
    toast(result.message || '已重新排队', result.ok ? 'info' : 'err');
  } catch (err) { toast(err, 'err'); }
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
    '<form id="row-edit-form" data-draft-type="' + (kind === 'task' ? 'task-edit' : 'meeting-edit') +
    '" data-draft-id="' + esc(seed.id ?? '') + '">' + body +
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
    if (r.ok) {
      const draftType = kind === 'task' ? 'task-edit' : 'meeting-edit';
      try { await clearServerDraft(api, draftType, id); }
      catch { /* retain the draft if cleanup cannot be confirmed */ }
      closeModal();
    }
    toast(r.message, r.ok ? 'ok' : 'err');
    if (r.ok) void refreshState();
  } catch (err) {
    toast(err, 'err');
  } finally {
    rowEditSubmitting = false;
    if (submitButton) submitButton.disabled = false;
  }
}

// ---------- 「写工作日志」/「写工作思考」入口（契约 §4.10） ----------

/** 关联项目下拉的候选项（name = 规范 ID，title = 中文显示名）。 */
export interface ProjectChoice {
  name: string;
  title: string;
}

function fieldValue(id: string): string {
  return (document.getElementById(id) as HTMLTextAreaElement | HTMLInputElement | null)?.value ?? '';
}

function projectCheckboxes(projects: ProjectChoice[]): string {
  if (!projects.length) return '<p class="hint">暂无已建档项目，可以先不关联。</p>';
  return '<div class="project-checklist">' + projects.map((project) =>
    '<label><input type="checkbox" name="journal-project" value="' + esc(project.name) + '"> ' +
    esc(project.title || project.name) + '</label>',
  ).join('') + '</div>';
}

function selectedProjectChecks(formId: string): string[] {
  const form = document.getElementById(formId);
  return Array.from(form?.querySelectorAll<HTMLInputElement>('input[name="journal-project"]:checked') ?? [])
    .map((input) => input.value);
}

function bindJournalCounters(formId: string): void {
  const form = document.getElementById(formId) as HTMLFormElement | null;
  if (!form) return;
  const update = (): void => {
    form.querySelectorAll<HTMLTextAreaElement>('textarea[data-count]').forEach((input) => {
      const count = form.querySelector<HTMLElement>('[data-count-for="' + input.id + '"]');
      const length = Array.from(input.value).length;
      if (count) count.textContent = length + ' / 1500';
      input.setCustomValidity(length > 1500 ? '这一段不能超过 1500 字符' : '');
    });
  };
  form.addEventListener('input', update);
  update();
}

/** 操作面板提供「查看记录」；瞬时提示用中文说明落点，不暴露目录字段。 */
function journalReceipt(url: string): string {
  return url.endsWith('/log')
    ? '工作日志已保存，可在最近操作结果中查看记录。'
    : '工作思考已保存，可在最近操作结果中查看记录。';
}

let journalSubmitting = false;

/** 提交一条日志/思考；后端的中文提示**原样**显示，成功才关弹层并给落点回执。 */
async function submitJournal(url: string, formId: string, body: Record<string, unknown>): Promise<void> {
  if (journalSubmitting) return;
  const oversized = Array.from(document.getElementById(formId)?.querySelectorAll<HTMLTextAreaElement>('textarea[data-count]') ?? [])
    .find((field) => Array.from(field.value).length > 1500);
  if (oversized) {
    oversized.setCustomValidity('这一段不能超过 1500 字符');
    oversized.reportValidity();
    oversized.focus();
    return;
  }
  journalSubmitting = true;
  const submit = document.querySelector<HTMLButtonElement>('#' + formId + ' button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const result = await mutation(() => api<{ ok: boolean; message: string; path?: string }>(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
    if (result.ok) {
      const draftType = url.endsWith('/log') ? 'journal-log' : 'journal-thought';
      try { await clearServerDraft(api, draftType, 'daily'); }
      catch { /* retain the draft if cleanup cannot be confirmed */ }
      closeModal();
      toast(journalReceipt(url), 'ok');
    } else {
      // 弹层留着好改：把「至少填一段…」「缺少必填段落：## 思考展开」「超过 1500 字符…」原样显示。
      toast(result.message, 'err');
    }
  } catch (err) {
    toast(err, 'err');
  } finally {
    journalSubmitting = false;
    if (submit) submit.disabled = false;
  }
}

/** 打开「写工作日志」弹层：四段（标签用使用者的话术），至少填一段；可多选关联项目。 */
export function openJournalLogModal(projects: ProjectChoice[] = []): void {
  const textField = (id: string, label: string, rows: number): string =>
    '<label for="' + id + '">' + label + '</label><textarea id="' + id + '" data-count aria-describedby="count-' + id + '" rows="' + rows + '"></textarea>' +
    '<span class="hint journal-count" id="count-' + id + '" data-count-for="' + id + '">0 / 1500</span>';
  openModal(
    '<h3>写工作日志</h3>' +
    '<p class="hint">按段填写今天的进展；每段最多 1500 字符，至少填写一段。</p>' +
    '<form id="journal-log-form" data-draft-type="journal-log" data-draft-id="daily">' +
    textField('journal-did', '今天做了什么', 3) +
    textField('journal-remaining', '还剩什么没做', 2) +
    textField('journal-reflection', '今天的一点感悟（可留空）', 2) +
    textField('journal-blockers', '卡点与需要谁（可留空）', 2) +
    '<fieldset><legend>关联项目（可多选，可不选）</legend>' + projectCheckboxes(projects) + '</fieldset>' +
    '<div class="row"><button class="primary" type="submit">保存</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>',
  );
  bindJournalCounters('journal-log-form');
  const form = document.getElementById('journal-log-form') as HTMLFormElement | null;
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    void submitJournal('/api/journal/log', 'journal-log-form', {
      did: fieldValue('journal-did'),
      remaining: fieldValue('journal-remaining'),
      reflection: fieldValue('journal-reflection'),
      blockers: fieldValue('journal-blockers'),
      projects: selectedProjectChecks('journal-log-form'),
    });
  });
}

/** 打开「写工作思考」弹层：三段都必填；可多选关联项目、可选一句话摘要。 */
export function openJournalThoughtModal(projects: ProjectChoice[] = []): void {
  const textField = (id: string, label: string, rows: number): string =>
    '<label for="' + id + '">' + label + '</label><textarea id="' + id + '" data-count required aria-describedby="count-' + id + '" rows="' + rows + '"></textarea>' +
    '<span class="hint journal-count" id="count-' + id + '" data-count-for="' + id + '">0 / 1500</span>';
  openModal(
    '<h3>写工作思考</h3>' +
    '<p class="hint">问题缘起、思考展开和当前结论都要填写；每段最多 1500 字符。</p>' +
    '<form id="journal-thought-form" data-draft-type="journal-thought" data-draft-id="daily">' +
    textField('journal-problem', '问题缘起', 3) +
    textField('journal-thinking', '思考展开', 4) +
    textField('journal-conclusion', '当前结论', 3) +
    '<label for="journal-summary">一句话摘要（可留空）</label><input id="journal-summary">' +
    '<fieldset><legend>关联项目（可多选，可不选）</legend>' + projectCheckboxes(projects) + '</fieldset>' +
    '<div class="row"><button class="primary" type="submit">保存</button>' +
    '<button class="ghost" type="button" data-action="close-modal">取消</button></div>' +
    '</form>',
  );
  bindJournalCounters('journal-thought-form');
  const form = document.getElementById('journal-thought-form') as HTMLFormElement | null;
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    void submitJournal('/api/journal/thought', 'journal-thought-form', {
      problem: fieldValue('journal-problem'),
      thinking: fieldValue('journal-thinking'),
      conclusion: fieldValue('journal-conclusion'),
      summary: fieldValue('journal-summary'),
      projects: selectedProjectChecks('journal-thought-form'),
    });
  });
}
