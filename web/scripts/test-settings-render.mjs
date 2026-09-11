import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// 真实并发回归（非源码正则）：模拟「设置页还挂着旧读取 → 保存模型触发刷新」。
// 旧响应最后返回时必须被丢弃，不能把刚保存后的"已配置"覆盖回"未配置"。
const scriptPath = fileURLToPath(import.meta.url);
const webRoot = resolve(scriptPath, '..', '..');
const srcDir = join(webRoot, 'src');
const tmpDir = join(webRoot, '.settings-render-test-tmp');
const entry = `
import { renderSettings } from './features/settings';

globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

function deferred() {
  let resolveFn = () => {};
  const promise = new Promise((r) => { resolveFn = r; });
  return { promise, resolve: resolveFn };
}

const older = deferred();
const newer = deferred();
let profileCalls = 0;

const profilePayload = (modelStatus) => ({
  profiles: [{
    workspace_id: 'ws-1',
    workspace_short_code: 'ws1',
    display_name: '合成工作区',
    path: '/tmp/synthetic-workspace',
    compatibility: 'ok',
    device_role: 'primary',
    active: true,
    provider_status: { model: modelStatus, feishu: 'configured' },
    sync_summary: { state: 'ready', pending_commits: 0 },
  }],
});

const actions = {
  api: (url) => {
    if (url === '/api/settings/profiles') {
      profileCalls += 1;
      return profileCalls === 1 ? older.promise : newer.promise;
    }
    if (url === '/api/settings/automation') return Promise.resolve({ jobs: {} });
    return Promise.resolve({ status: { feishu_auth: { needs_reauthorize: false } } });
  },
  mutation: (work) => work(),
  toast: () => {},
  refresh: () => {},
};

function makeView() {
  const el = { _html: '', querySelector: () => null, querySelectorAll: () => [] };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(value) { el._html = value; },
  });
  return el;
}

const view = makeView();
const firstRender = renderSettings(view, actions);
const secondRender = renderSettings(view, actions);

// 新读取先返回"已配置"，旧读取最后返回"未配置"（典型的过期响应覆盖）。
newer.resolve(profilePayload('configured'));
await new Promise((r) => setTimeout(r, 0));
older.resolve(profilePayload('missing'));
await Promise.all([firstRender, secondRender]);

export const finalHtml = view.innerHTML;
export { profileCalls };
`;

mkdirSync(tmpDir, { recursive: true });
try {
  const result = await build({
    stdin: { contents: entry, resolveDir: srcDir, sourcefile: 'settings-render-test.ts', loader: 'ts' },
    bundle: true,
    write: false,
    format: 'esm',
    platform: 'node',
    target: 'node18',
    logLevel: 'error',
  });
  const bundlePath = join(tmpDir, 'settings-render-test.mjs');
  writeFileSync(bundlePath, result.outputFiles[0].text);
  const mod = await import(pathToFileURL(bundlePath).href + '?t=' + Date.now());

  assert.equal(mod.profileCalls, 2, 'both settings reads must actually start');
  assert.match(mod.finalHtml, /✓ 已配置/, 'the newer settings render must win');
  assert.doesNotMatch(mod.finalHtml, /未配置/, 'a stale settings response must not overwrite newer content');
  console.log('Settings render race tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
