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
  claimAutomationPrimary,
  downgradeAutomationPrimary,
  publishWorkspaceToRemote,
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

// G1：主设备卡片。别的设备持有声明时必须渲染「勾选确认 + 接管 + generation」，
// 本机角色为 automation-primary 时另有降级按钮。
const primaryProfile = (role) => ({
  workspace_id: 'ws-1', workspace_short_code: 'ws1', display_name: '合成工作区',
  path: '/tmp/synthetic-workspace', compatibility: 'ok', device_role: role, active: true,
  provider_status: { model: 'configured', feishu: 'configured' },
  sync_summary: { state: 'ready', pending_commits: 0 },
});
const primaryView = makeView();
await renderSettings(primaryView, {
  api: (url) => {
    if (url === '/api/settings/profiles') {
      return Promise.resolve({ profiles: [primaryProfile('automation-primary')], current_device_id: 'dev-local' });
    }
    if (url === '/api/settings/automation') return Promise.resolve({ jobs: {} });
    if (url === '/api/sync/status') {
      return Promise.resolve({ automation_primary_device_id: 'dev-other', automation_primary_generation: 3 });
    }
    return Promise.resolve({ status: { feishu_auth: { needs_reauthorize: false } } });
  },
  mutation: (work) => work(), toast: () => {}, refresh: () => {},
});
export const primaryTakeoverHtml = primaryView.innerHTML;

const primaryOwnView = makeView();
await renderSettings(primaryOwnView, {
  api: (url) => {
    if (url === '/api/settings/profiles') {
      return Promise.resolve({ profiles: [primaryProfile('automation-primary')], current_device_id: 'dev-local' });
    }
    if (url === '/api/settings/automation') return Promise.resolve({ jobs: {} });
    if (url === '/api/sync/status') {
      return Promise.resolve({ automation_primary_device_id: 'dev-local', automation_primary_generation: 4 });
    }
    return Promise.resolve({ status: { feishu_auth: { needs_reauthorize: false } } });
  },
  mutation: (work) => work(), toast: () => {}, refresh: () => {},
});
export const primaryOwnHtml = primaryOwnView.innerHTML;

// G2：没有远端时必须给出可执行的首次发布入口；已经有远端时不再显示。
const publishHiddenView = makeView();
await renderSettings(publishHiddenView, {
  api: (url) => {
    if (url === '/api/settings/profiles') {
      return Promise.resolve({ profiles: [{ ...primaryProfile('secondary'), remote_url: 'https://github.com/example/existing.git' }], current_device_id: 'dev-local' });
    }
    if (url === '/api/settings/automation') return Promise.resolve({ jobs: {} });
    if (url === '/api/sync/status') return Promise.resolve({});
    return Promise.resolve({ status: { feishu_auth: { needs_reauthorize: false } } });
  },
  mutation: (work) => work(), toast: () => {}, refresh: () => {},
});
export const publishHiddenHtml = publishHiddenView.innerHTML;

fields['publish-remote-url'] = { value: 'https://github.com/example/new-repo.git' };
fields['publish-github-username'] = { value: 'example' };
fields['publish-github-pat'] = { value: 'synthetic-publish-pat' };
fields['publish-result'] = makeView();
const publishCalls = [];
mountSettings({
  api: (url, options) => {
    if (url === '/api/settings/git/remote/publish') {
      publishCalls.push({ body: JSON.parse(String(options?.body ?? '{}')), options });
      return Promise.resolve({ ok: true, remote_url: 'https://github.com/example/new-repo.git', branch: 'main' });
    }
    return recordingApi(url, options);
  },
  mutation: (work) => work(),
  toast: (message, kind) => { toasts.push({ message, kind }); },
  refresh: () => {},
  workspaceId: () => 'ws-1',
  clearDraftSnapshot: () => {}, disposeApiClient: () => {}, disposeWorkspaceStore: () => {},
});
await publishWorkspaceToRemote();
export const publishPatValueAfter = fields['publish-github-pat'].value;
export const publishProbe = {
  calls: publishCalls.map((call) => ({
    body: call.body,
    method: call.options?.method,
    contentType: call.options?.headers?.['Content-Type'],
  })),
  resultHtml: fields['publish-result'].innerHTML,
};

// G1 写请求：未勾选确认时一个请求都不发；勾选后必须带回 device_id/takeover/expected_generation。
fields['primary-claim-result'] = makeView();
fields['primary-takeover-ack'] = { checked: false };
const primaryClaims = [];
mountSettings({
  api: (url, options) => {
    if (url === '/api/sync/primary/claim' || url === '/api/sync/primary/downgrade') {
      primaryClaims.push({ url, body: JSON.parse(String(options?.body ?? '{}')), options });
      return Promise.resolve({ ok: true, device_role: 'automation-primary' });
    }
    return recordingApi(url, options);
  },
  mutation: (work) => work(),
  toast: (message, kind) => { toasts.push({ message, kind }); },
  refresh: () => {},
  workspaceId: () => 'ws-1',
  clearDraftSnapshot: () => {}, disposeApiClient: () => {}, disposeWorkspaceStore: () => {},
});
await claimAutomationPrimary('dev-local', true, '3');
export const primaryBlockedCount = primaryClaims.length;
fields['primary-takeover-ack'].checked = true;
await claimAutomationPrimary('dev-local', true, '3');
await claimAutomationPrimary('', false, '');
await downgradeAutomationPrimary();
export const primaryProbe = primaryClaims.map((call) => ({
  url: call.url,
  body: call.body,
  method: call.options?.method,
  contentType: call.options?.headers?.['Content-Type'],
}));

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

  // G2：没有远端 ⇒ 首次发布入口；已有远端 ⇒ 不再显示（避免必然失败的按钮）。
  assert.match(mod.finalHtml, /首次发布到远端/, 'a workspace without a remote gets a publish entry point');
  assert.match(mod.finalHtml, /id="publish-remote-url"/, 'the publish form collects an HTTPS URL');
  assert.match(mod.finalHtml, /data-action="git-remote-publish"/, 'the publish button is rendered');
  assert.doesNotMatch(
    mod.publishHiddenHtml,
    /data-action="git-remote-publish"/,
    'a workspace that already has a remote is not offered first publish',
  );
  assert.doesNotMatch(mod.publishHiddenHtml, /首次发布到远端/, 'the publish card disappears once bound');

  // G1：没有声明时给"声明"入口；别的设备持有时给"勾选确认 + 接管 + generation"与降级入口。
  assert.match(mod.finalHtml, /尚未声明/, 'settings says when no primary is declared yet');
  assert.match(mod.finalHtml, /声明本机为主设备/, 'settings offers the first claim entry point');
  assert.match(mod.primaryTakeoverHtml, /id="primary-takeover-ack"/, 'takeover requires an explicit ack checkbox');
  assert.match(mod.primaryTakeoverHtml, /data-action="primary-claim"/, 'takeover button is rendered');
  assert.match(mod.primaryTakeoverHtml, /data-generation="3"/, 'takeover carries the current generation');
  assert.match(mod.primaryTakeoverHtml, /本机 device id：dev-local/, 'settings shows the local device id');
  assert.match(mod.primaryTakeoverHtml, /dev-other · generation 3/, 'settings shows the current primary and generation');
  assert.match(mod.primaryTakeoverHtml, /接管后果/, 'takeover consequences are stated before the click');
  assert.match(mod.primaryTakeoverHtml, /data-action="primary-downgrade"/, 'downgrade entry point is rendered');
  assert.match(mod.primaryOwnHtml, /本机已是主设备/, 'an idempotent device is told it is already primary');
  assert.doesNotMatch(
    mod.primaryOwnHtml,
    /data-action="primary-claim" data-device="dev-local" data-takeover="true"/,
    'an idempotent device is not offered a takeover',
  );

  // G1 写请求契约：未勾选不发请求；勾选后 POST JSON 且带回 expected_generation。
  assert.equal(mod.primaryBlockedCount, 0, 'takeover without the ack checkbox must not issue a request');
  assert.deepEqual(
    mod.primaryProbe.map((call) => call.url),
    ['/api/sync/primary/claim', '/api/sync/primary/downgrade'],
    'only the two explicit primary actions issue requests',
  );
  assert.deepEqual(mod.primaryProbe[0].body, {
    device_id: 'dev-local', takeover: true, expected_generation: 3,
  });
  assert.deepEqual(mod.primaryProbe[1].body, {});
  for (const call of mod.primaryProbe) {
    assert.equal(call.method, 'POST', call.url + ' must be POSTed');
    assert.equal(call.contentType, 'application/json', call.url + ' must send a JSON body');
  }

  // G2 写请求：一次 POST、JSON 头、表单值原样进 body、成功后清空令牌输入框。
  assert.equal(mod.publishProbe.calls.length, 1, 'publishing issues exactly one request');
  assert.deepEqual(mod.publishProbe.calls[0].body, {
    candidate_url: 'https://github.com/example/new-repo.git',
    git_username: 'example',
    pat: 'synthetic-publish-pat',
  });
  assert.equal(mod.publishProbe.calls[0].method, 'POST');
  assert.equal(mod.publishProbe.calls[0].contentType, 'application/json');
  assert.equal(mod.publishPatValueAfter, '', 'the PAT input must be cleared after a successful publish');
  assert.match(mod.publishProbe.resultHtml, /origin 与 upstream 已绑定/, 'the publish result explains what changed');

  console.log('Settings render race tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
