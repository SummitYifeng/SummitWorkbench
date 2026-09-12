import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.version-status-test-tmp');

// The version chip is the only place the app tells the user which build is running
// (Step 9 moved it into lifecycle/version.ts). Every status maps to exactly one sentence,
// and the synced label must name both the client build and the served version.
const entry = `
import { versionStatusLabel } from './lifecycle/version';

const remote = { server_version: '2.3.4' } as any;

export const labels = {
  checking: versionStatusLabel('checking', null),
  syncedLocal: versionStatusLabel('synced', null),
  syncedRemote: versionStatusLabel('synced', remote),
  pending: versionStatusLabel('update-pending', null),
  reconnecting: versionStatusLabel('reconnecting', null),
  failed: versionStatusLabel('failed', null),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'version-status-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
    define: { __WB_BUILD__: JSON.stringify('v-test-build') },
  });
  const bundlePath = join(tmpDir, 'version-status-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { labels } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.equal(labels.checking, '正在检查版本');
  assert.equal(labels.syncedLocal, '已同步', 'without a served version the label stays generic');
  assert.match(labels.syncedRemote, /v-test-build/, 'the synced label names the client build');
  assert.match(labels.syncedRemote, /2\.3\.4/, 'the synced label names the served version');
  assert.match(labels.syncedRemote, /已同步/);
  assert.equal(labels.pending, '新版本已就绪');
  assert.equal(labels.reconnecting, '正在重新连接');
  assert.equal(labels.failed, '更新未完成');

  console.log('Version status label tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
