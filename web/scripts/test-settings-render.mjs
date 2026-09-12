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
  removeProfile,
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
const removeCalls = [];
const toasts = [];
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
  if (url === '/api/settings/profile/remove') {
    const body = JSON.parse(String(options?.body ?? '{}'));
    removeCalls.push({ body, options });
    return Promise.resolve({
      ok: true,
      workspace_id: body.workspace_id,
      active: body.workspace_id === 'ws-active',
      restart_required: body.workspace_id === 'ws-active',
    });
  }
  return actions.api(url, options);
};

mountSettings({
  api: recordingApi,
  mutation: (work) => work(),
  toast: (message, kind) => { toasts.push({ message, kind }); },
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
export const profileCallsAfterRace = profileCalls;

// 工作台列表：当前工作台也能移除（后端会返回 restart_required），非当前工作台另有切换按钮。
const twoProfileView = makeView();
await renderSettings(twoProfileView, {
  api: (url) => {
    if (url === '/api/settings/profiles') {
      return Promise.resolve({ profiles: [
        { workspace_id: 'ws-active', workspace_short_code: 'wsA', display_name: '当前工作台', path: '/tmp/a', compatibility: 'ok', device_role: 'primary', active: true, provider_status: { model: 'configured', feishu: 'configured' }, sync_summary: { state: 'ready', pending_commits: 0 } },
        { workspace_id: 'ws-other', workspace_short_code: 'wsB', display_name: '另一台', path: '/tmp/b', compatibility: 'ok', device_role: 'secondary', active: false, provider_status: { model: 'missing', feishu: 'missing' }, sync_summary: { state: 'ready', pending_commits: 2 } },
      ] });
    }
    if (url === '/api/settings/automation') return Promise.resolve({ jobs: {} });
    return Promise.resolve({ status: { feishu_auth: { needs_reauthorize: false } } });
  },
  mutation: (work) => work(), toast: () => {}, refresh: () => {},
});
export const profilesHtml = twoProfileView.innerHTML;

// 移除本机 profile：确认 → POST JSON；空 id 不发请求；当前工作台提示需要重启。
await removeProfile('ws-active');
await new Promise((r) => setTimeout(r, 10));
removeProfile('');
await new Promise((r) => setTimeout(r, 10));
export const removeProbe = {
  calls: removeCalls.map((call) => ({
    body: call.body,
    method: call.options?.method,
    contentType: call.options?.headers?.['Content-Type'],
  })),
  toasts: toasts.map((entry) => entry.message),
};
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

  assert.equal(mod.profileCallsAfterRace, 2, 'both settings reads must actually start');
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
  // 每个工作台都能移除；只有非当前工作台才有切换按钮。
  assert.match(mod.profilesHtml, /data-action="profile-remove" data-workspace="ws-active"/);
  assert.match(mod.profilesHtml, /data-action="profile-remove" data-workspace="ws-other"/);
  assert.match(mod.profilesHtml, /data-action="profile-switch" data-workspace="ws-other"/);
  assert.ok(
    !/data-action="profile-switch" data-workspace="ws-active"/.test(mod.profilesHtml),
    'the active workspace offers no switch button',
  );
  assert.match(mod.profilesHtml, /移除当前工作台后，需要重启工作台才会生效/);

  // 移除请求本身：一次性确认字段、JSON 头、空 id 不发请求、当前工作台提示重启。
  assert.equal(mod.removeProbe.calls.length, 1, 'an empty workspace id must not issue a request');
  assert.deepEqual(mod.removeProbe.calls[0].body, { workspace_id: 'ws-active', confirmed: true });
  assert.equal(mod.removeProbe.calls[0].method, 'POST');
  assert.equal(mod.removeProbe.calls[0].contentType, 'application/json');
  assert.ok(
    mod.removeProbe.toasts.some((message) => message.includes('重启工作台后生效')),
    'removing the active workspace must say a restart is required',
  );

  console.log('Settings render race tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
