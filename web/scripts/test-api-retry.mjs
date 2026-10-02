import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.api-retry-test-tmp');
const entry = `
import { retryRead } from './api/request';
export async function retryProbe() {
  let calls = 0;
  const delays: number[] = [];
  const value = await retryRead(async () => {
    calls += 1;
    if (calls < 3) throw new TypeError('Failed to fetch');
    return 'ready';
  }, 0, async (delay) => { delays.push(delay); });
  return { calls, delays, value };
}
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'api-retry-test.ts', loader: 'ts' },
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
  assert.deepEqual(await mod.retryProbe(), { calls: 3, delays: [1000, 3000], value: 'ready' });
  console.log('GET retry schedule tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
