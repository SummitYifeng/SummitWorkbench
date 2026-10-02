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
  runAutomationFromForm,
} from './features/settings';
import { saveModel, verifySavedModel } from './features/settings/render';

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

// 接住设置页发给原生壳的消息（「启用定时」保存后要通知 SMAppService 启停 helper）。
const nativeMessages = [];
globalThis.window.webkit = {
  messageHandlers: { wbLifecycle: { postMessage: (message) => nativeMessages.push(message) } },
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

// 回归：「立即运行」必须先保存表单再运行（勾了启用却没保存时，后端会按未启用跳过）。
const automationRequests = [];
const runJobs = [];
nativeMessages.length = 0;
const automationActions = {
  api: (url, init) => {
    automationRequests.push({ url, init });
    return Promise.resolve({ ok: true, status: 'degraded' });
  },
  mutation: (work) => work(),
  toast: () => {},
  refresh: () => {},
  runJob: (job) => { runJobs.push(job); return Promise.resolve(); },
};
const weekdayInputs = [0, 1, 2, 3, 4, 5, 6].map((value) => ({ value: String(value) }));
const automationForm = {
  dataset: { job: 'brief' },
  elements: {
    namedItem: (name) => (name === 'enabled' ? { checked: true } : { value: '08:00' }),
  },
  querySelectorAll: () => weekdayInputs,
};
const automationRunButton = {
  dataset: { job: 'brief' },
  closest: (selector) => (selector === 'form' ? automationForm : null),
};
await runAutomationFromForm(automationRunButton, automationActions);
export const automationRunProbe = {
  order: automationRequests.map((call) => call.init?.method ?? 'GET'),
  putBody: automationRequests[0] ? JSON.parse(String(automationRequests[0].init.body)) : null,
  putContentType: automationRequests[0]?.init?.headers?.['Content-Type'],
  runRequests: automationRequests.filter((call) => call.init?.method === 'POST').length,
  ranJob: runJobs[0] ?? null,
  nativeMessages: nativeMessages.slice(),
};

const modelSecret = { value: 'synthetic-model-key' };
const modelResult = { innerHTML: '' };
const modelView = { querySelector: (selector) => selector === '#model-secret' ? modelSecret : selector === '#model-result' ? modelResult : null };
const modelCalls = [];
let verifyCount = 0;
const modelActions = {
  api: async (url, init) => {
    modelCalls.push({ url, init });
    if (url.endsWith('/verify') && ++verifyCount === 1) throw new Error('offline');
    return { ok: true, message: '连接正常' };
  },
  mutation: (work) => work(), toast: (message, kind) => toasts.push({ message, kind }), refresh: () => {},
};
await saveModel(modelView, modelActions);
export const modelSaveFailureProbe = { html: modelResult.innerHTML, calls: modelCalls.length, secret: modelSecret.value };
await verifySavedModel(modelView, modelActions);
export const modelSavedRetryProbe = { html: modelResult.innerHTML, calls: modelCalls.length, urls: modelCalls.map((call) => call.url) };

const partialFailureView = makeView();
await renderSettings(partialFailureView, {
  api: async (url) => {
    if (url === '/api/settings/profiles') throw new Error('profile read failed');
    if (url === '/api/settings/automation') throw new Error('automation read failed');
    if (url === '/api/settings/model-parameters') throw new Error('advanced read failed');
    if (url === '/api/sync/status') throw new Error('sync read failed');
    return { status: { feishu_auth: { needs_reauthorize: false } } };
  },
  mutation: (work) => work(), toast: () => {}, refresh: () => {},
});
export const partialFailureHtml = partialFailureView.innerHTML;
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
  // 2026-09-14：设备 id / generation 这类内部标识不再铺在主视图里——代际说「第 N 代」，
  // 设备 id 收进「设备标识」折叠区（排查问题时才展开）。
  assert.match(mod.primaryTakeoverHtml, /当前主设备：另一台机器 · 第 3 代/, 'settings shows the current primary and generation in plain Chinese');
  assert.match(mod.primaryTakeoverHtml, /<details class="settings-ids">/, 'device ids are folded away');
  assert.match(mod.primaryTakeoverHtml, /本机 device id：dev-local/, 'settings keeps the local device id available when expanded');
  assert.match(mod.primaryTakeoverHtml, /当前主设备 device id：dev-other/, 'settings keeps the primary device id available when expanded');
  assert.doesNotMatch(mod.primaryTakeoverHtml, /generation 3/, 'raw generation wording must not reach the UI');
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

  // 「立即运行」必须先保存当前表单：勾了「启用定时」却没点保存就运行时，后端按未启用跳过
  // （`skipped：任务未启用`，2026-09-18 使用者反馈）。这里断言保存先落盘、随后才触发运行
  // （运行请求本身由 actions.runJob 发出，本用例注入的是记录用的替身）。
  assert.deepEqual(mod.automationRunProbe.order, ['PUT'], 'run must persist the form before running the job');
  assert.deepEqual(mod.automationRunProbe.putBody, {
    job: 'brief', enabled: true, hour: 8, minute: 0, weekdays: [0, 1, 2, 3, 4, 5, 6],
  });
  assert.equal(mod.automationRunProbe.putContentType, 'application/json');
  assert.equal(mod.automationRunProbe.ranJob, 'brief');
  assert.deepEqual(
    mod.automationRunProbe.nativeMessages,
    [{ type: 'automationSettingsChanged', enabled: true }],
    'turning the schedule on must tell the native shell to register the helper',
  );

  assert.match(mod.partialFailureHtml, /id="model-card"/, 'core model settings survive an unrelated read failure');
  assert.match(mod.partialFailureHtml, /<strong>飞书<\/strong>/, 'the Feishu card remains available');
  assert.match(mod.partialFailureHtml, /工作区信息暂时无法读取/, 'workspace read failure is local to its card');
  assert.match(mod.partialFailureHtml, /自动化设置暂时无法读取/, 'advanced settings failure is local to advanced settings');
  assert.match(mod.partialFailureHtml, /模型参数暂时无法读取/, 'read-only parameter failure is localized');
  assert.match(mod.modelSaveFailureProbe.html, /配置已保存，连接尚未验证/, 'verification failure is distinct from a failed save');
  assert.match(mod.modelSaveFailureProbe.html, /无需再次粘贴密钥/, 'verification retry does not ask for the secret again');
  assert.equal(mod.modelSaveFailureProbe.secret, '', 'the saved secret is cleared from the form');
  assert.match(mod.modelSavedRetryProbe.html, /连接验证通过/, 'retry can confirm the saved configuration');
  assert.equal(mod.modelSavedRetryProbe.calls, 3, 'retry verifies without saving the credential again');
  assert.deepEqual(mod.modelSavedRetryProbe.urls, [
    '/api/settings/provider', '/api/settings/provider/verify', '/api/settings/provider/verify',
  ]);

  console.log('Settings render race tests passed');
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}
