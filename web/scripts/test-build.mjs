import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { computeSourceHash, makeBuildIdentity } from './build.mjs';

const input = [
  { path: 'web/src/main.ts', content: Buffer.from('alpha') },
  { path: 'web/package.json', content: Buffer.from('{}') },
];
const firstHash = computeSourceHash(input);
assert.equal(computeSourceHash(input), firstHash, 'same source input must be stable');
assert.notEqual(
  computeSourceHash([
    input[0],
    { path: 'web/package.json', content: Buffer.from('{"x":1}') },
  ]),
  firstHash,
  'changing a source file must change the source hash',
);
assert.equal(
  makeBuildIdentity({
    sourceHash: firstHash,
    builtAt: '2026-09-03T00:00:00.000Z',
    gitRevision: 'abc1234',
  }).frontendBuild,
  `v2026.09.03-abc1234-${firstHash.slice(0, 8)}`,
);
console.log('Build identity tests passed');

const root = path.resolve(import.meta.dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
assert.ok(read('src/main.ts').split('\n').length <= 40, 'main.ts must remain a composition root');
assert.match(read('src/api/client.ts'), /normalizeApiError/);
assert.match(read('src/api/client.ts'), /AbortController/);
assert.match(read('src/core/workspace-store.ts'), /workspaceScopedKey/);
for (const feature of ['projects', 'review', 'settings', 'today']) {
  assert.ok(fs.existsSync(path.join(root, 'src/features', feature, 'index.ts')), `${feature} feature exists`);
}
assert.match(read('src/features/projects/index.ts'), /projectDetailHtml/);
assert.match(read('src/features/review/index.ts'), /reviewHtml/);
assert.match(read('src/features/settings/render.ts'), /profile/);
assert.match(read('src/features/today/index.ts'), /mountToday/);
console.log('Frontend feature contract tests passed');
