import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const main = readFileSync(new URL('../src/legacy-main.ts', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../src/features/shell/shell.ts', import.meta.url), 'utf8');
const forbidden = [
  /\/api\/sync\//,
  /sync-conflict-(?:details|preview|apply|export)/,
  /autoSyncIfIdle|refreshSyncBanner|retrySync/,
  /openUndoModal|mountUndo/,
  /git-remote-(?:preview|apply|rollback|publish)/,
  /primary-(?:claim|downgrade)/,
];
for (const pattern of forbidden) {
  assert.doesNotMatch(main + shell, pattern, `retired workbench control remains reachable: ${pattern}`);
}
console.log('Retired workbench controls contract tests passed');
