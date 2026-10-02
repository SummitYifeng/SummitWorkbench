import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const render = readFileSync(new URL('../src/features/settings/render.ts', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../src/features/shell/shell.ts', import.meta.url), 'utf8');

assert.match(render, /settings-grid settings-grid-single/, 'the three core settings cards remain vertical');
for (const card of ['工作区', 'AI 模型', '飞书']) {
  assert.ok(render.includes(card), `settings retain the ${card} card`);
}
assert.match(render, /OneDrive 客户端负责/, 'settings explain external folder synchronization');
assert.match(render, /手动安装说明|手动更新/, 'settings explain manual DMG updates');
assert.doesNotMatch(render + shell, /\/api\/sync|Git 同步|git-remote|primary-claim|自动化主设备/,
  'settings and shell expose no retired Git or device-role controls');
assert.doesNotMatch(shell, /btn-sync|btn-undo|sync-banner/, 'the shell has no sync or undo controls');
console.log('Settings retirement contract tests passed');
