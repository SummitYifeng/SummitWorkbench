// 「今日」页两个新入口（写工作日志 / 写工作思考）的弹层契约：
// 表单字段与标签、提交体、后端中文提示原样上屏、成功后关闭并给落点回执。
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.today-journal-test-tmp');
const entry = `
import {
  mountTodayActions,
  openJournalLogModal,
  openJournalThoughtModal,
} from './features/today';

export const toasts: Array<{ message: string; kind?: string }> = [];
export const calls: Array<{ url: string; options: any }> = [];
export const responses: any[] = [];

mountTodayActions({
  api: ((url: string, options?: any) => {
    calls.push({ url, options });
    return Promise.resolve(responses.shift() ?? { ok: true, message: 'ok' });
  }) as any,
  mutation: ((work: any) => work()) as any,
  toast: ((message: any, kind?: any) => { toasts.push({ message: String(message), kind }); }) as any,
  refreshState: (async () => true) as any,
  renderToday: (() => {}) as any,
});

export { openJournalLogModal, openJournalThoughtModal };
`;

function fakeElement() {
  const listeners = {};
  return {
    hidden: false, dataset: {}, style: {}, value: '', disabled: false, innerHTML: '',
    textContent: '', children: [], listeners, selectedOptions: [],
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute() {}, removeAttribute() {}, focus() {},
    appendChild(child) { this.children.push(child); },
    addEventListener(type, fn) { listeners[type] = fn; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

const elements = {
  toasts: fakeElement(),
  'modal-backdrop': fakeElement(),
  modal: fakeElement(),
  'journal-log-form': fakeElement(),
  'journal-thought-form': fakeElement(),
  'journal-did': { value: '今天做了 A。' },
  'journal-remaining': { value: 'B 还没做。' },
  'journal-reflection': { value: '感悟：C。' },
  'journal-blockers': { value: '卡在 D。' },
  'journal-log-projects': { selectedOptions: [{ value: 'alpha' }] },
  'journal-problem': { value: '问题 P。' },
  'journal-thinking': { value: '展开 T。' },
  'journal-conclusion': { value: '结论 C。' },
  'journal-summary': { value: '' },
  'journal-thought-projects': { selectedOptions: [{ value: 'beta' }] },
};
globalThis.HTMLElement = class {};
globalThis.window = { confirm: () => true };
globalThis.document = {
  activeElement: null,
  createElement: () => fakeElement(),
  getElementById: (id) => elements[id] ?? null,
  querySelector: () => null,
};

const tick = () => new Promise((resolveTick) => setTimeout(resolveTick, 0));

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'today-journal-test.ts', loader: 'ts' },
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

  // ---- 写工作日志：字段/标签 + 提交体 ----
  mod.openJournalLogModal([{ name: 'alpha', title: '项目甲' }]);
  const logModalHtml = elements.modal.innerHTML;
  for (const label of ['今天做了什么', '还剩什么没做', '今天的一点感悟', '卡点与需要谁', '关联项目', '写工作日志']) {
    assert.ok(logModalHtml.includes(label), `log modal has label ${label}`);
  }
  assert.ok(logModalHtml.includes('项目甲'), 'project choices are rendered');

  elements['journal-log-form'].listeners.submit({ preventDefault() {} });
  await tick();
  const logCall = mod.calls.find((call) => call.url === '/api/journal/log');
  assert.ok(logCall, 'log submit posts to /api/journal/log');
  assert.deepEqual(JSON.parse(logCall.options.body), {
    did: '今天做了 A。',
    remaining: 'B 还没做。',
    reflection: '感悟：C。',
    blockers: '卡在 D。',
    projects: ['alpha'],
  });

  // ---- 成功：关弹层 + 落点回执 ----
  mod.responses.push({ ok: true, message: '已写入工作日志 → alpha', path: '/Users/x/Documents/Work/_vault/logs/2026-09-19-001.md' });
  elements['modal-backdrop'].hidden = false;
  elements['journal-log-form'].listeners.submit({ preventDefault() {} });
  await tick();
  assert.equal(elements['modal-backdrop'].hidden, true, 'a successful save closes the modal');
  const okToast = mod.toasts.at(-1);
  assert.equal(okToast.kind, 'ok');
  assert.match(okToast.message, /logs\/2026-09-19-001\.md/, 'the receipt names the vault path');

  // ---- 后端拒绝：提示原样上屏、弹层不关 ----
  const refusal = '至少填一段：今天做了什么 / 还剩什么没做 / 今天的一点感悟 / 卡点与需要谁';
  mod.responses.push({ ok: false, message: refusal });
  elements['modal-backdrop'].hidden = true;
  elements['journal-log-form'].listeners.submit({ preventDefault() {} });
  await tick();
  const errToast = mod.toasts.at(-1);
  assert.equal(errToast.kind, 'err');
  assert.equal(errToast.message, refusal, 'the backend message is shown verbatim');
  assert.equal(elements['modal-backdrop'].hidden, true, 'the modal stays as-is on refusal');

  // ---- 写工作思考：字段/标签 + 三段提交 + 缺段提示原样 ----
  mod.openJournalThoughtModal([{ name: 'beta', title: '项目乙' }]);
  const thoughtHtml = elements.modal.innerHTML;
  for (const label of ['问题缘起', '思考展开', '当前结论', '一句话摘要', '关联项目', '写工作思考']) {
    assert.ok(thoughtHtml.includes(label), `thought modal has label ${label}`);
  }
  mod.responses.push({ ok: false, message: '缺少必填段落：## 思考展开' });
  elements['journal-thought-form'].listeners.submit({ preventDefault() {} });
  await tick();
  const thoughtCall = mod.calls.find((call) => call.url === '/api/journal/thought');
  assert.ok(thoughtCall, 'thought submit posts to /api/journal/thought');
  assert.deepEqual(JSON.parse(thoughtCall.options.body), {
    problem: '问题 P。',
    thinking: '展开 T。',
    conclusion: '结论 C。',
    summary: '',
    projects: ['beta'],
  });
  assert.equal(mod.toasts.at(-1).message, '缺少必填段落：## 思考展开', 'the section refusal is verbatim');

  // ---- think 成功：落点回执 ----
  mod.responses.push({ ok: true, message: '已写入工作思考 → 20260919-ab12.md', path: '/Users/x/Documents/Work/_vault/thinking/20260919-ab12.md' });
  elements['modal-backdrop'].hidden = false;
  elements['journal-thought-form'].listeners.submit({ preventDefault() {} });
  await tick();
  assert.equal(elements['modal-backdrop'].hidden, true, 'a successful thought closes the modal');
  assert.match(mod.toasts.at(-1).message, /thinking\/20260919-ab12\.md/);

  console.log('Today journal entry tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
