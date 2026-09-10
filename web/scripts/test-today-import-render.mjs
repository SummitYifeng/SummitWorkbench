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
import { todayHtml } from './features/today';

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
  console.log('Today import receipt render tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
