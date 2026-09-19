// 【今日】页收件箱提升弹层（契约 §10）的行为契约：
// 默认目标来自后端本地启发式（打开弹层不调模型）、切目标只显示相关字段、
// 三个目标各自提交正确的请求体、后端中文提示原样上屏、成功才关弹层并刷新列表。
//
// 成本约定在这里也钉一半（另一半在 test-browser-contract.mjs 的**位置**守卫）：
// 「让 AI 判断」必须是显式调用 —— 本文件断言只有 requestInboxSuggestion 会打
// `/api/inbox/suggest`，而打开弹层本身一次请求都不发。
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.today-inbox-test-tmp');
const entry = `
import { openInboxPromoteModal, requestInboxSuggestion, mountTodayActions } from './features/today';

export const toasts: Array<{ message: string; kind?: string }> = [];
export const calls: Array<{ url: string; options: any }> = [];
export const responses: any[] = [];
export let refreshCount = 0;

mountTodayActions({
  api: ((url: string, options?: any) => {
    calls.push({ url, options });
    return Promise.resolve(responses.shift() ?? { ok: true, message: 'ok' });
  }) as any,
  mutation: ((work: any) => work()) as any,
  toast: ((message: any, kind?: any) => { toasts.push({ message: String(message), kind }); }) as any,
  refreshState: (async () => { refreshCount += 1; return true; }) as any,
  renderToday: (() => {}) as any,
});
export const refreshes = () => refreshCount;

export { openInboxPromoteModal, requestInboxSuggestion };
`;

function fakeElement(id = '') {
  const listeners = {};
  return {
    id, hidden: false, dataset: {}, style: {}, value: '', checked: false, disabled: false,
    innerHTML: '', textContent: '', children: [], listeners, selectedOptions: [],
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute() {}, removeAttribute() {}, focus() {}, click() {},
    appendChild(child) { this.children.push(child); },
    addEventListener(type, fn) { listeners[type] = fn; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

const elements = {
  'modal-backdrop': fakeElement(),
  modal: fakeElement(),
  'inbox-promote-form': fakeElement(),
  'inbox-suggest-line': fakeElement(),
  'inbox-project': { value: 'alpha' },
  'inbox-block': { value: 'followup' },
  'inbox-due': { value: '2026-09-25' },
  'inbox-start': { value: '2026-09-25' },
  'inbox-problem': { value: '要不要把术语表前置？' },
  'inbox-thinking': { value: '返工都出在术语上。' },
  'inbox-conclusion': { value: '术语表前置能明显降低返工。' },
  'inbox-summary': { value: '' },
  'inbox-fields-project': fakeElement('inbox-fields-project'),
  'inbox-fields-feishu-task': fakeElement('inbox-fields-feishu-task'),
  'inbox-fields-thought': fakeElement('inbox-fields-thought'),
  'inbox-target-project': { ...fakeElement('inbox-target-project'), value: 'project' },
  'inbox-target-feishu-task': { ...fakeElement('inbox-target-feishu-task'), value: 'feishu-task' },
  'inbox-target-thought': { ...fakeElement('inbox-target-thought'), value: 'thought' },
};
// 单选组的当前选择：`checkedTarget()` 读 `input[name=inbox-target]:checked`
let picked = elements['inbox-target-project'];
for (const radio of [elements['inbox-target-project'], elements['inbox-target-feishu-task'], elements['inbox-target-thought']]) {
  Object.defineProperty(radio, 'checked', {
    get() { return picked === radio; },
    set(next) { if (next) picked = radio; },
  });
}

globalThis.HTMLElement = class {};
globalThis.window = { confirm: () => true };
globalThis.document = {
  activeElement: null,
  createElement: () => fakeElement(),
  getElementById: (id) => elements[id] ?? null,
  querySelector: (selector) => (selector === 'input[name="inbox-target"]:checked' ? picked : null),
  querySelectorAll: (selector) =>
    selector === 'input[name="inbox-target"]'
      ? [elements['inbox-target-project'], elements['inbox-target-feishu-task'], elements['inbox-target-thought']]
      : [],
};

const tick = () => new Promise((resolveTick) => setTimeout(resolveTick, 0));
const item = {
  id: 'web-a',
  text: '把翻译流程定稿 #it-development',
  kind: null,
  due: null,
  project: 'it-development',
  projects: ['it-development'],
  candidate_id: 'web-a',
  suggested_target: 'project',
  suggested_reason: '有 #it-development ⇒ 归到该项目页（下一步 / 跟进事项）',
};

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'today-inbox-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const outFile = join(tmpDir, 'bundle.mjs');
  writeFileSync(outFile, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(outFile).href + '?t=' + Date.now());

  // ---- 打开弹层：本地默认选中 + 不调模型、不发任何请求 ----
  mod.openInboxPromoteModal(item, [{ name: 'alpha', title: '项目甲' }]);
  const html = elements.modal.innerHTML;
  for (const label of ['提升这条', '项目页条目', '飞书待办', '一篇工作思考', '让 AI 判断这条适合变成什么', '提升并移出收件箱']) {
    assert.ok(html.includes(label), `promote modal has ${label}`);
  }
  assert.ok(html.includes('把翻译流程定稿'), 'the entry text is shown');
  assert.ok(html.includes('归到该项目页'), 'the local suggestion reason is shown');
  assert.ok(html.includes('项目甲'), 'project choices are rendered');
  assert.equal(picked, elements['inbox-target-project'], 'the local heuristic picks the default target');
  assert.equal(mod.calls.length, 0, 'opening the modal makes no request at all (no model, no cost)');

  // ---- 切目标：只显示相关字段 ----
  picked = elements['inbox-target-thought'];
  for (const radio of [elements['inbox-target-project'], elements['inbox-target-feishu-task'], elements['inbox-target-thought']]) {
    radio.listeners.change?.({});
  }
  assert.equal(elements['inbox-fields-thought'].hidden, false, 'thought fields become visible');
  assert.equal(elements['inbox-fields-project'].hidden, true, 'project fields hide');
  assert.equal(elements['inbox-fields-feishu-task'].hidden, true, 'feishu fields hide');

  // ---- 三个目标各自的提交体 ----
  picked = elements['inbox-target-project'];
  elements['inbox-promote-form'].listeners.submit({ preventDefault() {} });
  await tick();
  let call = mod.calls.at(-1);
  assert.equal(call.url, '/api/inbox/promote');
  assert.deepEqual(JSON.parse(call.options.body), {
    id: 'web-a', target: 'project', project: 'alpha', block: 'followup',
  });

  picked = elements['inbox-target-feishu-task'];
  elements['inbox-promote-form'].listeners.submit({ preventDefault() {} });
  await tick();
  call = mod.calls.at(-1);
  assert.deepEqual(JSON.parse(call.options.body), {
    id: 'web-a', target: 'feishu-task', due_date: '2026-09-25', start_date: '2026-09-25',
  });

  picked = elements['inbox-target-thought'];
  elements['inbox-promote-form'].listeners.submit({ preventDefault() {} });
  await tick();
  call = mod.calls.at(-1);
  assert.deepEqual(JSON.parse(call.options.body), {
    id: 'web-a', target: 'thought',
    problem: '要不要把术语表前置？',
    thinking: '返工都出在术语上。',
    conclusion: '术语表前置能明显降低返工。',
    summary: '',
  });

  // ---- 后端拒绝：提示原样上屏、弹层不关、不刷新 ----
  const refusal = '飞书待办需要截止日期（这条没带截止，请填一个）';
  mod.responses.push({ ok: false, message: refusal });
  const refreshesBefore = mod.refreshes();
  elements['modal-backdrop'].hidden = false;
  elements['inbox-promote-form'].listeners.submit({ preventDefault() {} });
  await tick();
  assert.equal(mod.toasts.at(-1).kind, 'err');
  assert.equal(mod.toasts.at(-1).message, refusal, 'the backend message is shown verbatim');
  assert.equal(elements['modal-backdrop'].hidden, false, 'the modal stays open so it can be fixed');
  assert.equal(mod.refreshes(), refreshesBefore, 'a refusal does not refresh the list');

  // ---- 成功：关弹层 + 回执带落点 + 刷新列表（条目消失） ----
  mod.responses.push({
    ok: true,
    message: '已提升为 alpha 的「下一步」并移出收件箱',
    path: '/Users/x/Documents/Work/_vault/projects/alpha.md',
  });
  elements['modal-backdrop'].hidden = false;
  elements['inbox-promote-form'].listeners.submit({ preventDefault() {} });
  await tick();
  assert.equal(elements['modal-backdrop'].hidden, true, 'a successful promote closes the modal');
  assert.equal(mod.toasts.at(-1).kind, 'ok');
  assert.match(mod.toasts.at(-1).message, /projects\/alpha\.md/, 'the receipt names the landing page');
  assert.equal(mod.refreshes(), refreshesBefore + 1, 'a successful promote refreshes the inbox list');

  // ---- 「让 AI 判断」：显式调用、只给建议、不自动提交 ----
  const callsBefore = mod.calls.length;
  const promotesBefore = mod.calls.filter((entryCall) => entryCall.url === '/api/inbox/promote').length;
  mod.responses.push({
    ok: true,
    model_used: true,
    target: 'feishu-task',
    reason: 'AI 建议：有截止日期 2026-09-25 ⇒ 按待办处理（建议仅供参考，最终由你确认）',
  });
  await mod.requestInboxSuggestion('web-a');
  assert.equal(mod.calls.length, callsBefore + 1, 'the AI button makes exactly one call');
  const suggestCall = mod.calls.at(-1);
  assert.equal(suggestCall.url, '/api/inbox/suggest');
  assert.deepEqual(JSON.parse(suggestCall.options.body), { id: 'web-a' });
  assert.equal(picked, elements['inbox-target-feishu-task'], 'the AI suggestion selects its target');
  assert.match(elements['inbox-suggest-line'].textContent, /AI 建议/, 'the suggestion is labelled as AI');
  assert.match(elements['inbox-suggest-line'].textContent, /仅供参考/, 'and says the human still decides');
  assert.equal(
    mod.calls.filter((entryCall) => entryCall.url === '/api/inbox/promote').length,
    promotesBefore,
    'a suggestion never submits on its own',
  );

  // ---- AI 不可用：保留本地默认，并说明这不是 AI 结论 ----
  mod.responses.push({ ok: true, model_used: false, target: 'project', reason: '有 #it-development ⇒ 归到该项目页（AI 不可用，显示的是本地判断：LLMError）' });
  await mod.requestInboxSuggestion('web-a');
  assert.equal(picked, elements['inbox-target-project'], 'the local default is kept when the model is unavailable');
  assert.match(elements['inbox-suggest-line'].textContent, /本地判断/);
  assert.equal(mod.toasts.at(-1).kind, 'info');

  console.log('Today inbox promote tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
