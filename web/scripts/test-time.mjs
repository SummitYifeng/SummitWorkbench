import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.time-test-tmp');

const entry = `
import { formatBusinessTime, businessDatetimeLocal } from './core/time';

export const values = {
  instant: formatBusinessTime('2026-09-15T16:30:00Z'),
  offset: formatBusinessTime('2026-09-16T00:30:00+08:00'),
  missing: formatBusinessTime(null),
  dateOnly: formatBusinessTime('2026-09-16'),
  unknownZone: formatBusinessTime('2026-09-16T00:30:00'),
  invalid: formatBusinessTime('not-a-time'),
  input: businessDatetimeLocal('1789489800'),
};
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'time-test.ts', loader: 'ts' },
    bundle: true, write: false, format: 'esm', platform: 'node', target: 'node18', logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'time-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const { values } = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.equal(values.instant, '2026-09-16 00:30:00');
  assert.equal(values.offset, '2026-09-16 00:30:00');
  assert.equal(values.missing, '—');
  assert.equal(values.dateOnly, '2026-09-16');
  assert.equal(values.unknownZone, '时区未知');
  assert.equal(values.invalid, '无效时间');
  assert.equal(values.input, '2026-09-16T00:30');
  console.log('Business time tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
