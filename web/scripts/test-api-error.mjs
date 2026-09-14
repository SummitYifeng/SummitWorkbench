import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// 真实单元测试（非源码正则）：API 错误 envelope 必须让用户看懂失败原因。
const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.api-error-test-tmp');
const entry = `
import { errorText, normalizeApiError } from './api/client';

export const cases = {
  envelope: normalizeApiError(400, { code: 'invalid_source_path', message: '来源路径无效' }),
  validation: normalizeApiError(422, {
    code: 'validation_error',
    message: '请求参数不符合接口约束',
    details: [
      { loc: ['body', 'text'], msg: 'String should have at most 100000 characters' },
      { loc: ['body', 'project'], msg: 'Field required' },
    ],
  }),
  bare: normalizeApiError(503, null),
  nonObject: normalizeApiError(500, 'boom'),
  network: errorText(new TypeError('Failed to fetch')),
  aborted: errorText(Object.assign(new Error('x'), { name: 'AbortError' })),
  plain: errorText('同步完成'),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'api-error-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'api-error-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  // 2026-09-14：错误码是内部标识，保留在 ApiError.code，但不再拼进给使用者看的文案。
  assert.equal(mod.cases.envelope.message, '来源路径无效');
  assert.equal(mod.cases.envelope.status, 400);
  assert.equal(mod.cases.envelope.code, 'invalid_source_path');
  assert.match(
    mod.cases.validation.message,
    /请求参数不符合接口约束：String should have at most 100000 characters/,
    'validation detail must be surfaced so the user can act',
  );
  assert.ok(
    !mod.cases.validation.message.includes('validation_error'),
    'internal error codes must not leak into the user-facing message',
  );
  assert.equal(mod.cases.bare.message, '请求失败：HTTP 503');
  assert.equal(mod.cases.nonObject.message, '请求失败：HTTP 500');
  assert.equal(mod.cases.network, '连不上本地服务，请确认工作台还在运行');
  assert.equal(mod.cases.aborted, '请求已取消');
  assert.equal(mod.cases.plain, '同步完成');
  console.log('API error normalization tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
