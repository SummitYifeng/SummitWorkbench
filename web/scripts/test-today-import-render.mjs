import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.today-import-render-test-tmp');
const entry = `
import {
  completeTask,
  createTodayActions,
  mountTodayActions,
  openRowEditModal,
  plusMinutesInput,
  runBrief,
  todayHtml,
  todayUi,
  tsToDatetimeLocal,
} from './features/today';

const state = {
  day: '2026-09-10', status: { pending_review: 0, backlog: { oldest_age_days: null } },
  brief_md: null, brief_generated: false, projects: [],
};
const base = { state, importing: false, importOpen: true, health: { tone: 'ok', label: '正常' } };
export const receipt = todayHtml({ ...base, importResults: [
  { fileName: 'ok.md', bytes: 1024, status: 'success', message: '导入完成：处理 1、跳过 0、失败 0' },
  { fileName: 'partial.txt', bytes: 2048, status: 'partial', message: '导入部分完成：处理 1、跳过 0、失败 1', details: ['失败项保留待重试'] },
  { fileName: 'budget.md', bytes: 4096, status: 'success', message: '接近预算', estimate: { crosses_soft_budget: true } },
  { fileName: 'duplicate.md', bytes: 512, status: 'success', message: '幂等，未重复调用模型' },
  { fileName: 'failed.txt', bytes: 256, status: 'error', message: '导入未启动' },
] }, '');
export const multi = todayHtml({ ...base, importing: true, importResults: [
  { fileName: 'queue-a.md', bytes: 100, status: 'processing', message: '正在处理…' },
  { fileName: 'queue-b.md', bytes: 200, status: 'success', message: '导入完成' },
] }, '');
export const reopened = todayHtml({ ...base, importOpen: false, importResults: [
  { fileName: 'reopened.md', bytes: 100, status: 'success', message: '上次导入完成' },
] }, '');
export const times = {
  valid: tsToDatetimeLocal('1757000000'),
  zero: tsToDatetimeLocal('0'),
  negative: tsToDatetimeLocal('-1'),
  nullish: tsToDatetimeLocal(null),
  undefinedValue: tsToDatetimeLocal(undefined),
  junk: tsToDatetimeLocal('abc'),
  plus60: plusMinutesInput('1757000000', 60),
  plusInvalid: plusMinutesInput(undefined, 60),
};

// ---------------------------------------------------------------- write actions
// Step 8d moved these out of legacy-main; drive them through a stub DOM so the guards
// (oversize, double-submit, button re-enable) are asserted as behaviour, not as source text.

class FakeClassList {
  added: string[] = [];
  removed: string[] = [];
  add(name: string) { this.added.push(name); }
  remove(name: string) { this.removed.push(name); }
  contains() { return false; }
}

function fakeElement(): any {
  const listeners: Record<string, (ev: any) => void> = {};
  return {
    hidden: false, dataset: {}, style: {}, value: '', disabled: false, innerHTML: '',
    textContent: '', children: [] as any[], listeners,
    classList: new FakeClassList(),
    setAttribute() {}, removeAttribute() {}, focus() {},
    appendChild(child: any) { this.children.push(child); },
    addEventListener(type: string, fn: (ev: any) => void) { listeners[type] = fn; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

const elements: Record<string, any> = {
  toasts: fakeElement(),
  'modal-backdrop': fakeElement(),
  modal: fakeElement(),
  'row-edit-form': fakeElement(),
  'row-edit-summary': { value: '合成标题' },
  'row-edit-due': { value: '2026-09-30' },
  'row-edit-start': { value: '2026-09-10T09:00' },
  'row-edit-end': { value: '2026-09-10T10:00' },
};
const submitButton = fakeElement();
globalThis.HTMLElement = class {};
globalThis.window = { setTimeout: () => 0 };
globalThis.document = {
  activeElement: null,
  createElement: () => fakeElement(),
  getElementById: (id: string) => elements[id] ?? null,
  querySelector: (selector: string) =>
    (selector === '#row-edit-form button[type="submit"]' ? submitButton : null),
};

const toasts: Array<{ message: string; kind?: string }> = [];
const calls: Array<{ url: string; options: any }> = [];
let renders = 0;
let refreshes = 0;
let gate: { promise: Promise<any>; resolve: (value: any) => void } | null = null;

const deferred = () => {
  let resolve!: (value: any) => void;
  const promise = new Promise<any>((r) => { resolve = r; });
  return { promise, resolve };
};

const api = (url: string, options?: any) => {
  calls.push({ url, options });
  const payload =
    url === '/api/capture' ? { ok: true, message: '已捕捉：合成捕捉文本' } :
    url === '/api/run/brief' ? { ok: true, message: '简报已生成' } :
    url === '/api/tasks/complete' ? { ok: false, message: '写回失败' } :
    url === '/api/meetings/import' ? { ok: true, status: 'queued', job_id: 'job-1', message: '已归档，后台继续处理' } :
    url === '/api/meetings/imports/job-1' ? { ok: true, job_id: 'job-1', file_name: 'transcript.md', bytes: 10, status: 'succeeded', stage: 'completed', result: { message: '导入完成' } } :
    { ok: true, message: '任务已更新' };
  if (gate) { const pending = gate; gate = null; return pending.promise; }
  return Promise.resolve(payload);
};

mountTodayActions({
  api,
  mutation: (work) => work(),
  toast: (message, kind) => { toasts.push({ message, kind }); },
  refreshState: async () => { refreshes += 1; return true; },
  renderToday: () => { renders += 1; },
});

const view = {} as HTMLElement;
const actions = createTodayActions(view);
const callsTo = (url: string) => calls.filter((call) => call.url === url);

// capture: the 100k limit is enforced locally, so an oversized body never reaches the API.
const oversized = await actions.capture('长'.repeat(100001));
const captured = await actions.capture('合成捕捉文本');
const captureCalls = callsTo('/api/capture');
const oversizeToasts = elements.toasts.children.map((child: any) => child.textContent);

// importFiles: an unsupported file becomes a receipt without any request; a supported one
// posts multipart FormData and only then refreshes the day.
todayUi.importResults = [];
await actions.importFiles([{ name: 'deck.pdf', size: 10 } as unknown as File]);
const unsupportedReceipt = { ...todayUi.importResults[0] };
const requestsAfterUnsupported = callsTo('/api/meetings/import').length;
await actions.importFiles([{ name: 'transcript.md', size: 10 } as unknown as File]);
const importReceipts = todayUi.importResults.map((item) => ({ ...item }));

// runBrief / completeTask / refresh.
await runBrief();
const briefCalls = callsTo('/api/run/brief').length;
const doneButton: any = fakeElement();
doneButton.dataset = { task: 'task-1' };
doneButton.closest = () => ({});
await completeTask(doneButton);
const completeCalls = callsTo('/api/tasks/complete').length;
actions.refresh();

// Row edit: escaped seed, one PATCH per double click, button re-enabled afterwards.
openRowEditModal('task', { id: 'task-1', title: '<img src=x onerror=alert(1)>', due: '2026-09-30' });
const modalHtml = elements.modal.innerHTML;
const form = elements['row-edit-form'];
const updatesBefore = callsTo('/api/tasks/update').length;
const pending = deferred();
gate = pending;
form.listeners.submit({ preventDefault() {} });
form.listeners.submit({ preventDefault() {} });
pending.resolve({ ok: true, message: '任务已更新' });
await new Promise((r) => setTimeout(r, 0));
const updateCalls = calls.filter((call) => call.url === '/api/tasks/update');
const updateBody = JSON.parse(updateCalls[updateCalls.length - 1].options.body);

export const actionsProbe = {
  oversized,
  captured,
  captureCalls,
  oversizeToasts,
  unsupportedReceipt,
  requestsAfterUnsupported,
  importReceipts,
  importBodyIsFormData: callsTo('/api/meetings/import')[0]?.options?.body instanceof FormData,
  briefCalls,
  completeCalls,
  refreshes,
  renders,
  doneDisabled: doneButton.disabled,
  doneRemoved: doneButton.classList.removed,
  modalHtml,
  updateDelta: updateCalls.length - updatesBefore,
  updateBody,
  submitDisabledAfter: submitButton.disabled,
  backdropHidden: elements['modal-backdrop'].hidden,
  feishuToastKinds: toasts.map((entry) => entry.kind),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'today-import-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'today-import-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());
  assert.match(mod.receipt, /ok\.md/);
  assert.match(mod.receipt, /import-receipt partial/);
  assert.match(mod.receipt, /本次估算接近软预算/);
  assert.match(mod.receipt, /幂等，未重复调用模型/);
  assert.match(mod.receipt, /failed\.txt/);
  assert.match(mod.receipt, /multiple/);
  assert.match(mod.multi, /queue-a\.md/);
  assert.match(mod.multi, /queue-b\.md/);
  assert.match(mod.multi, /正在归档并结构化/);
  assert.match(mod.reopened, /import-drawer[^>]+hidden/);
  assert.match(mod.reopened, /reopened\.md/);

  // Pure time helpers used by the inline row editor (now features/today/time.ts).
  // Asserted timezone-independently: only the value delta and the invalid cases.
  assert.match(mod.times.valid, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  assert.equal(
    new Date(mod.times.plus60).getTime() - new Date(mod.times.valid).getTime(),
    60 * 60 * 1000,
  );
  for (const key of ['zero', 'negative', 'nullish', 'undefinedValue', 'junk', 'plusInvalid']) {
    assert.equal(mod.times[key], '', key);
  }

  const probe = mod.actionsProbe;

  // capture
  assert.equal(probe.oversized.ok, false, 'an oversized capture is refused locally');
  assert.equal(probe.captureCalls.length, 1, 'the oversized capture must not reach the API');
  assert.match(probe.oversizeToasts.join('\n'), /超过 10 万字上限/, 'the refusal explains the limit');
  assert.equal(probe.captured.ok, true);
  assert.equal(probe.captureCalls[0].options.method, 'POST');
  assert.equal(probe.captureCalls[0].options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(probe.captureCalls[0].options.body), { text: '合成捕捉文本' });
  assert.ok(probe.renders >= 2, 'capture re-renders before and after the request');

  // import
  assert.equal(probe.unsupportedReceipt.status, 'error');
  assert.match(probe.unsupportedReceipt.message, /仅支持 \.md \/ \.txt/);
  assert.equal(probe.requestsAfterUnsupported, 0, 'an unsupported file issues no import request');
  assert.equal(probe.importReceipts.length, 2, 'the earlier receipt is kept alongside the new one');
  assert.equal(probe.importReceipts[1].status, 'success');
  assert.equal(probe.importBodyIsFormData, true, 'meeting import posts multipart form data');

  // runBrief / completeTask / refresh
  assert.equal(probe.briefCalls, 1);
  assert.equal(probe.completeCalls, 1);
  assert.equal(probe.doneDisabled, false, 'a failed completion re-enables the row button');
  assert.deepEqual(probe.doneRemoved, ['busy'], 'the busy affordance is removed on failure');
  assert.ok(probe.refreshes >= 3, 'brief/complete/refresh all ask for a state refresh');

  // row edit
  assert.match(probe.modalHtml, /&lt;img src=x onerror=alert\(1\)&gt;/, 'seed values are escaped');
  assert.ok(!probe.modalHtml.includes('<img src=x'), 'raw markup never reaches the modal');
  assert.equal(probe.updateDelta, 1, 'a double submit issues exactly one write-back');
  assert.deepEqual(probe.updateBody, {
    task_id: 'task-1', summary: '合成标题', due_date: '2026-09-30',
  });
  assert.equal(probe.submitDisabledAfter, false, 'the submit button is re-enabled afterwards');
  assert.equal(probe.backdropHidden, true, 'a successful save closes the modal');
  assert.ok(probe.feishuToastKinds.includes('err'), 'the failed completion reports an error toast');

  console.log('Today import receipt render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
