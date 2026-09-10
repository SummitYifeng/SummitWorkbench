import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/legacy-main.ts'), 'utf8');
const reviewSource = fs.readFileSync(path.join(root, 'src/features/review/render.ts'), 'utf8');
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
assert.match(reviewSource, /\/api\/review\/source\?path=/, 'review evidence links open a local read-only source route');
assert.match(source, /e\.actionable && !!e\.route/, 'batch approval filters incomplete candidates');
assert.match(source, /REVIEW_BATCH_LIMIT/, 'batch review operations have a client-side limit');
assert.match(source, /超过单批上限 100 条/, 'batch limit explains how to recover');
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
assert.match(source, /X-WB-Workspace-Generation/, 'API requests carry workspace generation');
assert.match(source, /latestStateRequest|latestReviewRequest/, 'stale refresh responses are ignored');
assert.match(source, /saveEntityDraft|loadEntityDraft|clearEntityDraft/, 'entity drafts have an explicit storage contract');
assert.match(source, /requestModalClose/, 'modal close is routed through the unsaved-draft guard');
assert.match(source, /function activateModal/, 'specialized modals use the shared focus setup');
assert.match(source, /if \(backdrop\.hidden\)[\s\S]{0,180}modalReturnFocus/, 'nested modal content preserves the original return focus');
assert.match(source, /const modal = activateModal\(projectViewHtml\(view\)\)/, 'project view receives modal focus semantics');
assert.match(source, /window\.confirm[\s\S]{0,350}产物已保存[\s\S]{0,500}\/api\/threads\/state/, 'artifact state sync requires a final preview confirmation');
assert.match(source, /askErrors/, 'failed ask requests remain visible without entering history');
assert.match(source, /restoreFailedQuestion/, 'failed ask requests restore the question without duplicating history');
console.log('Browser interaction contract tests passed');
