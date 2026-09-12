import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.undo-render-test-tmp');

// The undo dialog's HTML builders are pure string functions; the modal used to be untested.
const entry = `
import { UNDO_FLYNOTE, undoEmptyHtml, undoErrorHtml, undoListHtml } from './features/undo';

const commit = {
  sha: 'abc123def456',
  short_sha: 'abc123d',
  message: 'wb: 审批应用写回',
  time: '2026-09-12T07:20:30+08:00',
  files: ['review.md', 'projects/P1.md'],
};

export const cases = {
  flynote: UNDO_FLYNOTE,
  error: undoErrorHtml('读取失败'),
  errorEscaped: undoErrorHtml('<b>boom</b>'),
  empty: undoEmptyHtml('暂无系统自动提交'),
  emptyNoteEscaped: undoEmptyHtml('a<b>'),
  listEmpty: undoListHtml([]),
  list: undoListHtml([commit]),
  listEscaped: undoListHtml([{ ...commit, message: 'x<b>', files: ['a<b>'] }]),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'undo-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'undo-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { cases } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.ok(cases.flynote.length > 0, 'the flynote is defined');

  // Read failures surface as an error block.
  assert.match(cases.error, /class="msg err"/);
  assert.match(cases.error, /读取失败/);
  assert.match(cases.errorEscaped, /&lt;b&gt;boom&lt;\/b&gt;/);
  assert.ok(!cases.errorEscaped.includes('<b>'), 'error text is escaped');

  // Empty history: the note plus the flynote explaining what undo does and does not cover.
  assert.match(cases.empty, /暂无系统自动提交/);
  assert.match(cases.empty, /每次系统写回成功都会自动留痕/);
  assert.ok(cases.empty.includes(cases.flynote), 'flynote is present when history is empty');
  assert.match(cases.emptyNoteEscaped, /a&lt;b&gt;/);

  // Non-empty history: one row per commit with both actions wired to the sha.
  assert.ok(cases.listEmpty.includes(cases.flynote), 'flynote is present in the list header too');
  assert.ok(!cases.listEmpty.includes('undo-commit'), 'no rows when there are no commits');
  assert.ok(cases.list.includes(cases.flynote));
  assert.equal((cases.list.match(/undo-commit/g) ?? []).length, 1);
  assert.match(cases.list, /wb: 审批应用写回/);
  assert.match(cases.list, /abc123d/);
  assert.match(cases.list, /2026-09-12 07:20/);
  assert.match(cases.list, /触碰文件：review\.md、projects\/P1\.md/);
  assert.match(cases.list, /data-undo="diff" data-sha="abc123def456"/);
  assert.match(cases.list, /data-undo="revert" data-sha="abc123def456"/);
  assert.match(cases.listEscaped, /x&lt;b&gt;/);
  assert.match(cases.listEscaped, /a&lt;b&gt;/);

  console.log('Undo pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
