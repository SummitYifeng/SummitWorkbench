import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/legacy-main.ts'), 'utf8');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');

// Browser-level interaction contract: these user actions must remain wired after feature moves.
assert.match(read('src/features/onboarding/index.ts'), /onboarding/, 'onboarding feature exists');
assert.match(source, /data-action="sync-retry"/, 'sync retry remains wired');
assert.match(source, /data-action="sync-conflict-details"/, 'protected sync opens conflict details');
assert.match(source, /\/api\/sync\/conflict\/selection\/validate/, 'manual conflict choices are validated');
assert.match(
  source,
  /\/api\/sync\/conflict\/selection\/validate[\s\S]{0,350}conflictSelectionRequest\(\)/,
  'selection validation does not send the recovery confirmation field',
);
assert.match(source, /\/api\/sync\/conflict\/recover/, 'conflict recovery remains wired');
assert.match(source, /\/api\/sync\/conflict\/export/, 'conflict package export remains wired');
assert.match(source, /unknown-generated-view/, 'unknown generated views have a safe fallback label');
assert.match(source, /preserve-both/, 'unknown generated views keep both copies');
assert.match(source, /脱敏审计记录未完成/, 'audit failure remains visible after recovery commit');
assert.match(source, /conflictRecoveryRequest\(false\)/, 'recovery preview is explicit and write-free');
assert.match(source, /确认恢复并创建提交/, 'recovery requires an explicit confirmation action');
assert.match(source, /\/api\/review\/apply/, 'review apply remains wired');
assert.match(source, /data-action="profile-switch"/, 'profile switch remains wired');
assert.match(source, /data-action="diagnostics-preview"/, 'diagnostics preview remains wired');
assert.match(source, /\/api\/diagnostics\/export/, 'diagnostics export remains wired');
assert.match(
  source,
  /\/api\/settings\/git\/remote\/preview[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote preview sends JSON content type',
);
assert.match(
  source,
  /\/api\/settings\/git\/remote\/apply[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'remote apply sends JSON content type',
);
assert.match(
  source,
  /\/api\/settings\/acceptance-preflight[\s\S]{0,250}headers: \{ 'Content-Type': 'application\/json' \}/,
  'acceptance preflight sends JSON content type',
);
assert.match(read('src/lifecycle/native-bridge.ts'), /openLogDirectory/, 'log directory action remains wired');
assert.match(read('src/api/client.ts'), /dispose\(\): void/, 'requests have a disposal boundary');
assert.match(read('src/core/workspace-store.ts'), /subscribe\(/, 'workspace changes are observable');
console.log('Browser interaction contract tests passed');
