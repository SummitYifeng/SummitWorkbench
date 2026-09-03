import assert from 'node:assert/strict';

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
