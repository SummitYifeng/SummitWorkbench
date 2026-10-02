import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { computeSourceHash, makeBuildIdentity, verifiedGitRevision } from './build.mjs';

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
  `v2026.09.03-${firstHash.slice(0, 8)}`,
);
// 回归守卫：身份不得依赖 git 提交，否则「重建 → 产物变 → 提交 → HEAD 变 → 产物又变」
// 的自指循环会让仓库静态产物与装机包永远对不上（2026-09-18 踩到）。
assert.equal(
  makeBuildIdentity({
    sourceHash: firstHash,
    builtAt: '2026-09-03T00:00:00.000Z',
    gitRevision: 'completely-different',
  }).frontendBuild,
  `v2026.09.03-${firstHash.slice(0, 8)}`,
  'frontend build identity must not depend on the git revision',
);
assert.equal(
  makeBuildIdentity({
    sourceHash: firstHash,
    builtAt: '2026-09-03T00:00:00.000Z',
    gitRevision: 'abc1234',
  }).gitRevision,
  'abc1234',
  'git revision stays available as provenance metadata',
);
assert.equal(verifiedGitRevision('abc1234', ''), 'abc1234');
assert.equal(verifiedGitRevision('abc1234', ' M src/file.py'), '');
assert.equal(verifiedGitRevision('abc1234', null), '');
assert.equal(verifiedGitRevision('nogit', ''), '');
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
