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
import {
  renderSettings,
  mountSettings,
  previewGitRemoteNormalization,
  applyGitRemoteNormalization,
  rollbackGitRemoteNormalization,
  runAcceptancePreflight,
} from './features/settings';

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

const settingsView = makeView();
const fields = {
  'remote-candidate-url': { value: 'https://github.com/example/repo.git' },
  'remote-github-username': { value: 'example' },
  'remote-github-pat': { value: 'synthetic-pat' },
  'view-settings': settingsView,
};
globalThis.document = { getElementById: (id) => fields[id] ?? null, querySelector: () => null };
globalThis.window = {
  confirm: () => true,
  location: { search: '', pathname: '/', hash: '', href: '' },
  history: { replaceState: () => {} },
};

// 设置页写动作仍必须逐字保留 POST + JSON 头（搬迁不得改变请求契约）。
const writeCalls = [];
const payloadFor = (url) => {
  if (url.endsWith('/git/remote/preview')) {
    return { old_url: 'git@github.com:example/repo.git', candidate_url: 'https://github.com/example/repo.git', branch: 'main', candidate_ahead: 0, candidate_behind: 0, plan_id: 'plan-1' };
  }
  if (url.endsWith('/git/remote/apply')) return { new_url: 'https://github.com/example/repo.git' };
  if (url.endsWith('/git/remote/rollback')) return { restored_url: 'git@github.com:example/repo.git' };
  return { ok: true, report: 'synthetic preflight' };
};
const recordingApi = (url, options) => {
  if (url.startsWith('/api/settings/git/remote/') || url === '/api/settings/acceptance-preflight') {
    writeCalls.push({ url, options });
    return Promise.resolve(payloadFor(url));
  }
  return actions.api(url, options);
};

mountSettings({
  api: recordingApi,
  mutation: (work) => work(),
  toast: () => {},
  refresh: () => {},
  workspaceId: () => 'ws-1',
  clearDraftSnapshot: () => {},
  disposeApiClient: () => {},
  disposeWorkspaceStore: () => {},
});

await previewGitRemoteNormalization();
await applyGitRemoteNormalization('plan-1');
await rollbackGitRemoteNormalization();
await runAcceptancePreflight();
await new Promise((r) => setTimeout(r, 10));

export const writeCallSummary = writeCalls.map((call) => ({
  url: call.url,
  method: call.options?.method,
  contentType: call.options?.headers?.['Content-Type'],
}));

const view = makeView();
profileCalls = 0;
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
  assert.deepEqual(
    mod.writeCallSummary.map((call) => call.url),
    [
      '/api/settings/git/remote/preview',
      '/api/settings/git/remote/apply',
      '/api/settings/git/remote/rollback',
      '/api/settings/acceptance-preflight',
    ],
    'each settings write action must issue exactly one request',
  );
  for (const call of mod.writeCallSummary) {
    assert.equal(call.method, 'POST', call.url + ' must be POSTed');
    assert.equal(call.contentType, 'application/json', call.url + ' must send a JSON body');
  }
  assert.match(mod.finalHtml, /✓ 已配置/, 'the newer settings render must win');
  assert.doesNotMatch(mod.finalHtml, /未配置/, 'a stale settings response must not overwrite newer content');
  console.log('Settings render race tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
