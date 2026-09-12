import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.sync-render-test-tmp');

// Pure label helpers of the sync conflict modal. These used to be pinned only by
// proximity regexes in test-browser-contract.mjs; assert the real behaviour instead.
const entry = `
import {
  conflictDigestSummary,
  conflictEventSummary,
  conflictKindLabel,
  conflictRevision,
  conflictSelectionLabel,
} from './features/sync';

const detail = (over: Record<string, unknown> = {}) => ({
  path: 'p', kind: 'manual-markdown', action: 'choose', automatic: false,
  changed_on: [], local_sha256: null, remote_sha256: null, ...over,
});
const event = (device: string, at: string, op: string) => ({
  device_id: device, occurred_at: at, causation_operation_id: op,
});

export const cases = {
  kinds: [
    conflictKindLabel('append-only-event'),
    conflictKindLabel('generated-view'),
    conflictKindLabel('unknown-generated-view'),
    conflictKindLabel('manual-markdown'),
    conflictKindLabel('opaque-binary'),
    conflictKindLabel('brand-new-kind'),
  ],
  selections: [
    conflictSelectionLabel('keep-local'),
    conflictSelectionLabel('keep-remote'),
    conflictSelectionLabel('preserve-both'),
    conflictSelectionLabel(''),
  ],
  revisions: [
    conflictRevision('123456789012'),
    conflictRevision('1234567890123'),
    conflictRevision('abc'),
  ],
  eventMissing: conflictEventSummary(null),
  eventUnparsed: conflictEventSummary({ parse_status: 'bad' }),
  eventEmptyFields: conflictEventSummary({}),
  eventFull: conflictEventSummary(event('dev-a', '2026-09-01', 'op-1')),
  digestPlain: conflictDigestSummary(detail()),
  digestBothSides: conflictDigestSummary(detail({
    kind: 'append-only-event',
    local_event: event('dev-a', 't1', 'op-1'),
    remote_event: event('dev-b', 't2', 'op-2'),
  })),
  digestOneSide: conflictDigestSummary(detail({
    kind: 'append-only-event',
    local_event: null,
    remote_event: event('dev-b', 't2', 'op-2'),
  })),
  digestHashes: conflictDigestSummary(detail({
    local_sha256: 'abcdef1234567890',
    remote_sha256: 'zzz',
  })),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'sync-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'sync-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { cases } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // conflictKindLabel: all five known kinds plus the identity fallback.
  assert.deepEqual(cases.kinds, [
    '活动事件（自动收集）',
    '派生视图（重建）',
    '未知派生视图（保留双方）',
    'Markdown（人工选择）',
    '未知/二进制（保留双方）',
    'brand-new-kind',
  ]);

  // conflictSelectionLabel: three choices plus the "please choose" fallback.
  assert.deepEqual(cases.selections, [
    '保留本机',
    '采用远端',
    '保留双方副本',
    '请选择处理方式',
  ]);

  // conflictRevision: truncates strictly beyond 12 characters.
  assert.deepEqual(cases.revisions, ['123456789012', '123456789012…', 'abc']);

  // conflictEventSummary: empty unless the event parsed.
  assert.equal(cases.eventMissing, '');
  assert.equal(cases.eventUnparsed, '');
  assert.equal(cases.eventEmptyFields, '设备 — · 时间 — · 操作 —');
  assert.equal(cases.eventFull, '设备 dev-a · 时间 2026-09-01 · 操作 op-1');

  // conflictDigestSummary: event digests join both sides, hash digests truncate.
  assert.equal(cases.digestPlain, '');
  assert.equal(
    cases.digestBothSides,
    '设备 dev-a · 时间 t1 · 操作 op-1 / 设备 dev-b · 时间 t2 · 操作 op-2',
  );
  assert.equal(cases.digestOneSide, '设备 dev-b · 时间 t2 · 操作 op-2');
  assert.equal(cases.digestHashes, '摘要 本机 abcdef123456… · 远端 zzz');

  console.log('Sync pure label tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// The conflict-recovery request chain, driven end to end. This is exactly the
// path the A6 two-machine rehearsal walks by hand (详情 → 逐文件选择 → 临时预检 →
// 确认恢复), and until now only proximity regexes in test-browser-contract.mjs
// pinned it. `api()` goes through fetch, so asserting on fetch also proves the
// URLs, methods and bodies the real page sends.
const conflictEntry = `
import {
  applySyncConflictRecovery,
  conflictRecoveryRequest,
  conflictSelectionRequest,
  missingConflictSelections,
  mountSyncBanner,
  previewSyncConflictRecovery,
  showSyncConflictDetails,
} from './features/sync';

function fakeElement(): any {
  const listeners: Record<string, (ev: any) => void> = {};
  return {
    hidden: false, dataset: {}, style: {}, value: '', disabled: false, innerHTML: '',
    textContent: '', children: [] as any[], listeners,
    setAttribute() {}, removeAttribute() {}, focus() {},
    appendChild(child: any) { this.children.push(child); },
    addEventListener(type: string, fn: (ev: any) => void) { listeners[type] = fn; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

const toasts = fakeElement();
const modal = fakeElement();
const backdrop = fakeElement();
const selects = new Map<string, any>();

globalThis.HTMLElement = class {};
globalThis.CSS = { escape: (value: string) => value };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.window = { confirm: () => true, setTimeout: () => 0 };
globalThis.document = {
  activeElement: null,
  createElement: () => fakeElement(),
  getElementById: (id: string) =>
    id === 'modal' ? modal : id === 'modal-backdrop' ? backdrop : id === 'toasts' ? toasts : null,
  querySelector: () => null,
  querySelectorAll: () => [],
};

// The modal is rendered as a string; expose the selects it produced so the test
// can act like the user picking a per-file choice.
modal.querySelectorAll = (selector: string) => {
  if (selector !== '[data-conflict-path]') return [];
  const paths: string[] = [];
  const re = /data-conflict-path="([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(modal.innerHTML))) paths.push(match[1]);
  return paths.map((path) => {
    let element = selects.get(path);
    if (!element) {
      element = fakeElement();
      element.dataset.conflictPath = path;
      selects.set(path, element);
    }
    return element;
  });
};

const calls: Array<{ url: string; method: string; body: any }> = [];
const detailsPath = 'notes/a.md';
const binaryPath = 'notes/b.bin';
const autoPath = 'threads/index.md';

const jsonResponse = (data: unknown) => ({ ok: true, status: 200, json: async () => data });
globalThis.fetch = async (url: any, init: any) => {
  const target = String(url);
  const body = init?.body ? JSON.parse(String(init.body)) : null;
  calls.push({ url: target, method: init?.method ?? 'GET', body });
  if (target === '/api/sync/conflict/details') {
    return jsonResponse({
      ok: true, available: true,
      details: {
        base_revision: 'base1234567890',
        local: { revision: 'local1234567890' },
        remote: { revision: 'remote123456789' },
        automatic_path_count: 1, manual_path_count: 2,
        paths: [
          { path: autoPath, kind: 'append-only-event', action: 'collect', automatic: true, changed_on: ['local', 'remote'], local_sha256: null, remote_sha256: null },
          { path: detailsPath, kind: 'manual-markdown', action: 'choose', automatic: false, changed_on: ['local'], local_sha256: 'a'.repeat(20), remote_sha256: null },
          { path: binaryPath, kind: 'opaque-binary', action: 'choose', automatic: false, changed_on: ['remote'], local_sha256: null, remote_sha256: 'b'.repeat(20) },
        ],
      },
    });
  }
  if (target === '/api/sync/conflict/selection/validate') return jsonResponse({ ok: true, selection: {} });
  if (target === '/api/sync/conflict/recover') {
    if (body?.confirmed) {
      return jsonResponse({
        ok: true,
        recovery: { status: 'committed', audit: { status: 'committed' } },
        push: { ok: true },
      });
    }
    return jsonResponse({
      ok: true,
      preparation: { ok: true, event_count: 2, aggregate_count: 1, rebuilt_view_count: 0, candidate_path_count: 2 },
    });
  }
  throw new Error('unexpected request: ' + target);
};

mountSyncBanner({
  refreshState: async () => true,
  workspaceId: () => 'ws-1',
  persistEntityDraft: () => {},
});

await showSyncConflictDetails();
export const afterDetails = {
  html: modal.innerHTML,
  missing: missingConflictSelections(),
  selectionBody: conflictSelectionRequest().selections,
  automaticRendered: new RegExp('data-conflict-path="' + autoPath + '"').test(modal.innerHTML),
  binaryOptions: (modal.innerHTML.match(/data-conflict-path="notes\\/b\\.bin"[\\s\\S]*?<\\/select>/) ?? [''])[0],
  recoverCalls: calls.filter((call) => call.url === '/api/sync/conflict/recover').length,
};

// The user picks a per-file choice through the rendered control.
selects.get(detailsPath).value = 'keep-local';
selects.get(detailsPath).listeners.change();
selects.get(binaryPath).value = 'preserve-both';
selects.get(binaryPath).listeners.change();

export const afterSelection = {
  html: modal.innerHTML,
  missing: missingConflictSelections(),
  selectionBody: conflictSelectionRequest().selections,
  recoveryBody: conflictRecoveryRequest(false),
};

await previewSyncConflictRecovery();
export const afterPreview = {
  html: modal.innerHTML,
  validateCall: calls.find((call) => call.url === '/api/sync/conflict/selection/validate'),
  previewCall: calls.find((call) => call.url === '/api/sync/conflict/recover' && call.body?.confirmed === false),
};

await applySyncConflictRecovery();
export const afterApply = {
  html: modal.innerHTML,
  backdropHidden: backdrop.hidden,
  applyCall: calls.find((call) => call.url === '/api/sync/conflict/recover' && call.body?.confirmed === true),
  toasts: toasts.children.map((child: any) => child.textContent),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: {
      contents: conflictEntry,
      resolveDir: srcDir,
      sourcefile: 'sync-conflict-test.ts',
      loader: 'ts',
    },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'sync-conflict-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const flow = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // Reading the divergence is read-only and leaves every manual path unselected.
  assert.deepEqual(flow.afterDetails.missing, ['notes/a.md', 'notes/b.bin']);
  assert.deepEqual(flow.afterDetails.selectionBody, {});
  assert.equal(flow.afterDetails.automaticRendered, false, 'automatic paths get no selector');
  assert.equal(flow.afterDetails.recoverCalls, 0, 'opening the details writes nothing');
  assert.match(flow.afterDetails.html, /自动收集/, 'the automatic path says it is collected');
  assert.match(flow.afterDetails.html, /Markdown（人工选择）/, 'the manual path names its kind');
  // opaque-binary may only preserve both copies.
  assert.match(flow.afterDetails.binaryOptions, /value="preserve-both"/);
  assert.ok(!flow.afterDetails.binaryOptions.includes('keep-local'), 'binary offers no keep-local');
  assert.ok(!flow.afterDetails.binaryOptions.includes('keep-remote'), 'binary offers no keep-remote');
  // 临时预检 stays disabled until every manual path is chosen, and 确认恢复 is absent.
  assert.match(flow.afterDetails.html, /data-action="sync-conflict-preview"[^>]*disabled/);
  assert.ok(!flow.afterDetails.html.includes('sync-conflict-apply'), 'no apply before a preflight');

  // Choosing the last manual path enables the preflight.
  assert.deepEqual(flow.afterSelection.missing, []);
  assert.deepEqual(flow.afterSelection.selectionBody, {
    'notes/a.md': 'keep-local',
    'notes/b.bin': 'preserve-both',
  });
  assert.deepEqual(flow.afterSelection.recoveryBody, {
    base_revision: 'base1234567890',
    local_revision: 'local1234567890',
    remote_revision: 'remote123456789',
    selections: { 'notes/a.md': 'keep-local', 'notes/b.bin': 'preserve-both' },
    confirmed: false,
  });
  assert.match(flow.afterSelection.html, /data-action="sync-conflict-preview"[^>]*>临时预检/);

  // The preflight validates the selections WITHOUT the recovery confirmation field,
  // then asks for a write-free preparation.
  assert.ok(flow.afterPreview.validateCall, 'selections are validated before recovery');
  assert.equal(flow.afterPreview.validateCall.method, 'POST');
  assert.ok(!('confirmed' in flow.afterPreview.validateCall.body), 'validation is never a confirmation');
  assert.deepEqual(flow.afterPreview.validateCall.body.selections, {
    'notes/a.md': 'keep-local',
    'notes/b.bin': 'preserve-both',
  });
  assert.equal(flow.afterPreview.previewCall.body.confirmed, false, 'the preview is explicit and write-free');
  assert.match(flow.afterPreview.html, /预检完成。请确认后才会写回并创建提交。/);
  assert.match(flow.afterPreview.html, /data-action="sync-conflict-apply"/, 'apply appears only after a passing preflight');

  // Only the confirmed call commits, and success reports the ordinary sync result.
  assert.equal(flow.afterApply.applyCall.body.confirmed, true);
  assert.deepEqual(flow.afterApply.applyCall.body.selections, {
    'notes/a.md': 'keep-local',
    'notes/b.bin': 'preserve-both',
  });
  assert.equal(flow.afterApply.backdropHidden, true, 'a committed recovery closes the modal');
  assert.ok(
    flow.afterApply.toasts.some((text) => text.includes('恢复提交已创建并完成普通同步')),
    'the success message names the commit and the sync',
  );

  console.log('Sync conflict recovery request tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
