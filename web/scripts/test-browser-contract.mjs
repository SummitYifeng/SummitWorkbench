import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/legacy-main.ts'), 'utf8');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');

// Browser-level interaction contract: these user actions must remain wired after feature moves.
assert.match(source, /\/api\/onboarding\//, 'onboarding API actions remain wired');
assert.match(source, /data-action="sync-retry"/, 'sync retry remains wired');
assert.match(source, /\/api\/review\/apply/, 'review apply remains wired');
assert.match(source, /data-action="profile-switch"/, 'profile switch remains wired');
assert.match(read('src/api/client.ts'), /dispose\(\): void/, 'requests have a disposal boundary');
assert.match(read('src/core/workspace-store.ts'), /subscribe\(/, 'workspace changes are observable');
console.log('Browser interaction contract tests passed');
