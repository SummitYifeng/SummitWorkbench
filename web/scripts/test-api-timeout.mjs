import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.api-timeout-test-tmp');
const entry = `
import { createApiClient, ApiError } from './api/client';
export { ApiError };

export async function timeoutCase() {
  globalThis.fetch = (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  });
  const client = createApiClient();
  try { await client.request('/never', undefined, { timeoutMs: 20 }); }
  catch (error) { return error; }
  throw new Error('request unexpectedly settled');
}

export async function callerAbortCase() {
  globalThis.fetch = (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  });
  const caller = new AbortController();
  const client = createApiClient();
  const pending = client.request('/caller-abort', { signal: caller.signal }, { timeoutMs: 200 });
  caller.abort();
  try { await pending; }
  catch (error) { return error; }
  throw new Error('caller abort unexpectedly settled');
}
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'api-timeout-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'api-timeout-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());
  const timeout = await mod.timeoutCase();
  assert.ok(timeout instanceof mod.ApiError);
  assert.equal(timeout.code, 'request_timeout');
  const callerAbort = await mod.callerAbortCase();
  assert.equal(callerAbort.name, 'AbortError');
  console.log('API timeout and abort composition tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
