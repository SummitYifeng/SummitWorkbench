import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.threads-render-test-tmp');

// The artifact "save then confirm the state write-back" chain is a key invariant (plan Step 7).
// The confirmation text is now a pure function, so the preview/truncation rule can be asserted
// directly instead of via the contract test's proximity regex.
const entry = `
import { artifactStateConfirmText } from './features/threads';

const exactly1200 = 'a'.repeat(1200);
const over1200 = 'b'.repeat(1300);

export const cases = {
  short: artifactStateConfirmText('阶段总结：已完成拆分'),
  exactly: artifactStateConfirmText(exactly1200),
  over: artifactStateConfirmText(over1200),
  empty: artifactStateConfirmText(''),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'threads-render-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'threads-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { cases } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // The confirmation must name the write target explicitly and keep the user in control.
  assert.match(cases.short, /产物已保存/);
  assert.match(cases.short, /主档案「当前状态」/);
  assert.match(cases.short, /确认继续？/);
  assert.ok(cases.short.includes('阶段总结：已完成拆分'), 'the summary is previewed verbatim');

  // Preview budget: exactly 1200 characters passes through untouched.
  assert.ok(cases.exactly.includes('a'.repeat(1200)), 'a 1200-char preview is not truncated');
  assert.ok(!cases.exactly.includes('预览已截断'), 'no truncation notice at the limit');

  // One character over truncates to 1200 and says so.
  assert.ok(cases.over.includes('b'.repeat(1200)));
  assert.ok(!cases.over.includes('b'.repeat(1201)), 'the preview never exceeds 1200 characters');
  assert.match(cases.over, /…（预览已截断）/);

  // Empty summary still produces a well-formed confirmation.
  assert.match(cases.empty, /产物已保存/);
  assert.match(cases.empty, /确认继续？/);

  console.log('Threads pure render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
