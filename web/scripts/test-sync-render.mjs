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
