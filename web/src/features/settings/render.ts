/** 设置页渲染与只读数据读取（原 features/settings/index.ts，Step 8c 拆分）。 */
import { esc } from '../../md';
import { formatBusinessTime } from '../../core/time';

export interface ProfileSummary {
  workspace_id: string;
  workspace_short_code: string;
  display_name: string;
  path: string;
  compatibility: string;
  active: boolean;
  provider_status: Record<string, string>;
}

interface ProfileList { profiles: ProfileSummary[]; current_device_id?: string | null }

/** `/api/settings/model-parameters` 的只读参数项（不含任何凭据）。 */
interface ModelParameter {
  capability: string;
  purpose: string;
  configured: boolean;
  model_id?: string;
  thinking?: string;
  max_output_tokens?: number;
  context_window_tokens?: number;
  timeout_seconds?: number;
  pricing_configured?: boolean;
}
interface ModelParameterPayload {
  note: string;
  items: ModelParameter[];
}

export interface SettingsActions {
  api: <T>(url: string, init?: RequestInit) => Promise<T>;
  mutation: <T>(request: () => Promise<T>) => Promise<T>;
  toast: (message: unknown, kind?: 'ok' | 'err' | 'info') => void;
  refresh: () => void;
  /** 「立即运行」的注入入口（不传时退回全局动作，避免循环依赖）。 */
}


function badge(kind: 'model' | 'feishu', status: string | undefined, reauth = false): string {
  if (kind === 'feishu' && reauth) return '<span class="conn-badge reauth">⚠ 需重新授权</span>';
  if (status === 'read-error') return '<span class="conn-badge reauth">暂时无法读取</span>';
  if (status === 'verification-failed') return '<span class="conn-badge failed">需要验证连接</span>';
  if (status === 'configured' || status === 'configured-keychain') {
    return '<span class="conn-badge ok">✓ 已配置（尚未现场验证）</span>';
  }
  if (status === 'error' || status === 'failed' || status === 'verification-failed') {
    return '<span class="conn-badge failed">✗ 验证失败</span>';
  }
  return '<span class="conn-badge off">' + (kind === 'model' ? '未配置' : '未连接') + '</span>';
}

/**
 * 只读参数卡：把「每个任务实际生效的模型参数」摊开。
 *
 * 动机（2026-09-18）：长逐字稿结构化失败的真因在 `max_output_tokens` 与 `thinking`，
 * 而设置页过去只让填 model / base_url —— 用户没有任何地方能看到生效值，只能翻代码。
 */
function modelParameterCard(payload: ModelParameterPayload | null): string {
  if (!payload || !payload.items?.length) return '';
  const rows = payload.items.map((item) => {
    if (!item.configured) {
      return '<tr><td>' + esc(item.capability) + '</td><td colspan="5" class="meta">读取失败（请检查配置）</td></tr>';
    }
    const thinking = item.thinking === 'disabled' ? '关闭（更快更省）' : (item.thinking ?? 'default');
    return '<tr><td>' + esc(item.capability) + '<div class="meta">' + esc(item.purpose) + '</div></td>' +
      '<td>' + esc(item.model_id ?? '—') + '</td>' +
      '<td>' + esc(thinking) + '</td>' +
      '<td>' + esc(String(item.max_output_tokens ?? '—')) + '</td>' +
      '<td>' + esc(String(item.context_window_tokens ?? '—')) + '</td>' +
      '<td>' + esc(String(item.timeout_seconds ?? '—')) + 's</td></tr>';
  }).join('');
  return '<div class="card settings-card"><div class="card-head"><strong>模型参数（只读）</strong>' +
    '<span class="conn-badge off">生效值</span></div>' +
    '<p class="settings-card-desc">每个任务实际用的参数。改这些需要编辑工作台配置文件（应用内不提供改写入）。</p>' +
    '<table class="model-params"><thead><tr><th>任务</th><th>模型</th><th>思考模式</th>' +
    '<th>输出上限</th><th>上下文窗口</th><th>超时</th></tr></thead><tbody>' + rows + '</tbody></table>' +
    '<p class="hint">' + esc(payload.note) + '</p></div>';
}

/**
 * 设置页渲染序号：保存/刷新/切页会并发触发多次读取，先发起的旧响应
 * 不得覆盖后发起的新内容（例如刚保存模型后的刷新被保存前的读取盖回）。
 */
let settingsRenderSequence = 0;
type SettingsReadKey = 'profiles' | 'state' | 'modelParams';
const settingsLastGood: Partial<Record<SettingsReadKey, { value: unknown; at: string }>> = {};

async function readSetting<T>(
  actions: SettingsActions,
  key: SettingsReadKey,
  url: string,
): Promise<{ value: T | null; error: string | null; readAt: string | null }> {
  try {
    const value = await actions.api<T>(url);
    const at = new Date().toISOString();
    settingsLastGood[key] = { value, at };
    return { value, error: null, readAt: at };
  } catch (error) {
    const last = settingsLastGood[key];
    return {
      value: (last?.value as T | undefined) ?? null,
      error: String(error),
      readAt: last?.at ?? null,
    };
  }
}

function readFailure(label: string, error: string, at: string | null): string {
  return '<div class="settings-read-error" role="status"><span>' + esc(label) +
    '暂时无法读取：' + esc(error) + (at ? ' · 保留上次读取于 ' + esc(formatBusinessTime(at)) : '') +
    '</span> <button class="ghost" type="button" data-action="settings-retry">重试</button></div>';
}

export async function renderSettings(view: HTMLElement, actions: SettingsActions): Promise<void> {
  const requestId = ++settingsRenderSequence;
  const [profilesRead, stateRead, modelParamsRead] = await Promise.all([
    readSetting<ProfileList>(actions, 'profiles', '/api/settings/profiles'),
    readSetting<{ status: { feishu_auth?: { needs_reauthorize?: boolean } } }>(actions, 'state', '/api/state'),
    readSetting<ModelParameterPayload>(actions, 'modelParams', '/api/settings/model-parameters'),
  ]);
  try {
    if (requestId !== settingsRenderSequence) return;
    const response = profilesRead.value;
    const state = stateRead.value;
    const modelParams = modelParamsRead.value;
    const active = response?.profiles.find((p) => p.active) ?? response?.profiles[0];
    const modelStatus = active?.provider_status.model ?? (!response ? 'read-error' : undefined);
    const feishuStatus = active?.provider_status.feishu ?? (!response ? 'read-error' : undefined);
    const feishuReauth = Boolean(state?.status.feishu_auth?.needs_reauthorize);
    const workspace = active
      ? '<div class="settings-path">' + esc(active.display_name) + '<span class="meta">' + esc(active.path) + '</span></div>'
      : response
        ? '<div class="settings-path">（尚无工作区）</div>'
        : readFailure('工作区信息', profilesRead.error ?? '读取失败', profilesRead.readAt);
    const model = '<div class="card settings-card" id="model-card"><div class="card-head"><strong>AI 模型（DeepSeek）</strong>' + badge('model', modelStatus) + '</div>' +
      '<p class="settings-card-desc">会议结构化、简报和任务分类都靠它。当前状态表示配置是否存在；连接检查只在你点击验证时联网。</p>' +
      (profilesRead.error ? readFailure('模型配置', profilesRead.error, profilesRead.readAt) : '') +
      '<form id="model-settings-form" autocomplete="off"><label>DeepSeek API Key<input id="model-secret" type="password" autocomplete="new-password" placeholder="sk-…"></label>' +
      '<div class="row"><button class="primary" type="submit">连接并验证</button><button class="ghost" id="model-show-advanced" type="button">自定义模型（一般不用）</button></div>' +
      '<div class="settings-advanced" id="model-advanced" hidden><div class="grid2"><label>模型 ID<input id="model-id" value="deepseek-flash"></label>' +
      '<label>服务地址<input id="model-base-url" value="https://api.deepseek.com/v1"></label></div><p class="hint">默认使用 DeepSeek 官方地址；只有特殊网关才需要改。</p></div></form><div id="model-result"></div></div>';
    const modelParameters = (modelParams ? modelParameterCard(modelParams) : '') +
      (modelParamsRead.error ? readFailure('模型参数', modelParamsRead.error, modelParamsRead.readAt) : '');
    const feishu = '<div class="card settings-card"><div class="card-head"><strong>飞书</strong>' + badge('feishu', feishuStatus, feishuReauth) + '</div>' +
      '<p class="settings-card-desc">授权后，工作台才能读日历和任务，也能把完成动作写回飞书。此状态来自本机配置，不代表刚刚完成连接检查。</p>' +
      (profilesRead.error ? readFailure('飞书配置', profilesRead.error, profilesRead.readAt) : '') +
      (stateRead.error ? readFailure('飞书授权状态', stateRead.error, stateRead.readAt) : '') +
      '<div class="row"><button class="primary" data-action="feishu-reauth">' +
      (feishuReauth || feishuStatus !== 'configured' ? '授权飞书' : '重新授权飞书') + '</button><button class="ghost" data-action="settings-doctor-online">检查飞书连接</button></div><div id="feishu-result"></div></div>';
    const automationCard = '<div class="card settings-card"><div class="card-head"><strong>更新与交接</strong><span class="conn-badge off">手动</span></div>' +
      '<p class="settings-card-desc">简报和周复盘在工作台中手动生成。安装包通过 DMG 手动更新；文件夹同步由 OneDrive 客户端负责，请退出工作台并确认 OneDrive 已完成后再换设备。</p>' +
      '</div>';
    const profiles = response?.profiles.map((profile) => '<article class="card entry ' + (profile.active ? 'ok' : '') + '"><div class="entry-top"><strong>' +
      esc(profile.display_name) + '</strong><span class="badge">' + esc(profile.active ? '当前' : '其他工作台') + '</span></div><p class="meta">' +
      esc(profile.path) + '</p><p class="meta">连接：' + badge('model', profile.provider_status.model) + ' ' +
      badge('feishu', profile.provider_status.feishu, feishuReauth) + '</p>' +
      (profile.active ? '' : '<button class="primary" data-action="profile-switch" data-workspace="' + esc(profile.workspace_id) + '">切换到它</button>') +
      // 移除此 Mac 上的 profile：只删本机 profile/runtime/草稿，vault、远端与 Keychain 不动。
      // 当前工作台也能移除（后端返回 restart_required），否则没有第二台工作台时就永远删不掉。
      '<button class="ghost" data-action="profile-remove" data-workspace="' + esc(profile.workspace_id) + '">移除此 Mac 上的工作台</button>' +
      '</article>').join('') ?? readFailure('工作台列表', profilesRead.error ?? '读取失败', profilesRead.readAt);
    const profilesStatus = profilesRead.error && response ? readFailure('工作台列表', profilesRead.error, profilesRead.readAt) : '';
    const removeHint = response?.profiles.some((profile) => profile.active)
      ? '<p class="hint">移除只影响这台 Mac：vault、远端仓库和 Keychain 凭据都不动。移除当前工作台后，需要重启工作台才会生效。</p>'
      : '';
    const advanced = '<details class="settings-advanced-block"><summary><span class="bf-chev">›</span>高级与维护（模型参数 · 工作区 · 诊断）</summary>' +
      // 「自动化与更新」与「模型参数（只读）」原在主区，2026-09-18 按使用者要求移入这里：
      // 主区只留 工作区 / AI 模型 / 飞书 三张卡，每张一行。
      '<section class="block"><h3 class="section-title">更新与交接</h3>' + automationCard + '</section>' +
      (modelParameters === '' ? '' : '<section class="block"><h3 class="section-title">模型参数（只读）</h3>' + modelParameters + '</section>') +
      '<section class="block"><h3 class="section-title">工作台切换</h3><p class="hint">同一时间只打开一个工作台；切换前会先完成安全检查。</p>' + profiles + profilesStatus + removeHint + '</section>' +
      '<section class="block"><h3 class="section-title">健康检查</h3><p class="hint">离线检查不联网；在线检查会真实访问模型与飞书。</p><div class="row"><button class="ghost" data-action="settings-doctor">离线检查</button><button class="ghost" data-action="settings-doctor-online">在线检查</button></div></section>' +
      '<section class="block"><h3 class="section-title">诊断与支持</h3><div class="row"><button class="ghost" data-action="diagnostics-preview">查看诊断包清单</button><button class="ghost" data-action="diagnostics-export">导出诊断包</button><button class="ghost" data-action="diagnostics-open-log">打开日志目录</button></div><div id="diagnostics-preview"></div></section></details>';
    view.innerHTML = '<div class="settings-head"><h2 class="page-title">设置</h2><p class="hint">常用连接在这里完成；高级选项默认收起来。</p><button class="ghost" data-action="reopen-onboarding">重新打开连接向导</button></div><section class="settings-grid settings-grid-single">' +
      // 主区三张卡，每张一行（使用者要求：工作区 / AI 模型 / 飞书）。
      '<div class="card settings-card"><div class="card-head"><strong>工作区</strong>' + (response ? '<span class="conn-badge ok">✓ 已连接</span>' : badge('model', 'read-error')) + '</div><p class="settings-card-desc">会议、任务和项目都整理在这个文件夹里。</p>' + workspace + (profilesRead.error ? readFailure('工作区信息', profilesRead.error, profilesRead.readAt) : '') + '</div>' + model + feishu + '</section><section class="block">' + advanced + '</section>';

    view.querySelector<HTMLFormElement>('#model-settings-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      void saveModel(view, actions);
    });
    view.querySelector<HTMLButtonElement>('[data-action="model-verify"]')?.addEventListener('click', () => {
      void verifySavedModel(view, actions);
    });
    view.querySelector<HTMLButtonElement>('#model-show-advanced')?.addEventListener('click', (event) => {
      const box = view.querySelector<HTMLElement>('#model-advanced');
      if (!box) return;
      box.hidden = !box.hidden;
      (event.currentTarget as HTMLButtonElement).textContent = box.hidden ? '自定义模型（一般不用）' : '收起自定义';
    });
    view.querySelectorAll<HTMLButtonElement>('[data-action="settings-retry"]').forEach((button) => {
      button.addEventListener('click', () => { void renderSettings(view, actions); });
    });
  } catch (error) {
    if (requestId !== settingsRenderSequence) return;
    view.innerHTML = '<div class="error">设置暂时无法读取：' + esc(String(error)) + '</div>';
  }
}

export async function saveModel(view: HTMLElement, actions: SettingsActions): Promise<void> {
  const secret = view.querySelector<HTMLInputElement>('#model-secret')?.value.trim() ?? '';
  const modelId = view.querySelector<HTMLInputElement>('#model-id')?.value.trim() || 'deepseek-flash';
  const baseUrl = view.querySelector<HTMLInputElement>('#model-base-url')?.value.trim() || 'https://api.deepseek.com/v1';
  const result = view.querySelector<HTMLElement>('#model-result');
  if (!secret) { actions.toast('请先粘贴 DeepSeek API Key', 'err'); return; }
  if (result) result.innerHTML = '<p class="meta" aria-live="polite">正在保存配置…</p>';
  try {
    await actions.api('/api/settings/provider', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      provider: 'model', settings: { capability: 'shared', credential_capability: 'shared', model_id: modelId, base_url: baseUrl, credential_account: 'shared' }, secret,
    }) });
    if (view.querySelector<HTMLInputElement>('#model-secret')) view.querySelector<HTMLInputElement>('#model-secret')!.value = '';
    if (result) result.innerHTML = '<p class="meta" aria-live="polite">配置已保存，正在验证连接…</p>';
    actions.refresh();
    await verifySavedModel(view, actions);
  } catch (error) {
    if (result) result.innerHTML = '<div class="msg err" role="alert">配置未能保存：' + esc(String(error)) + '</div>';
    actions.toast(error, 'err');
  }
}

export async function verifySavedModel(view: HTMLElement, actions: SettingsActions): Promise<void> {
  const result = view.querySelector<HTMLElement>('#model-result');
  if (result) result.innerHTML = '<p class="meta" aria-live="polite">正在连接 DeepSeek 验证…</p>';
  try {
    const verified = await actions.api<{ ok: boolean; message: string }>('/api/settings/provider/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: 'model' }),
    });
    if (!verified.ok) throw new Error(verified.message || '连接检查未通过');
    if (result) result.innerHTML = '<div class="msg ok">✓ 配置已保存，连接验证通过：' + esc(verified.message) + '</div>';
    actions.toast('DeepSeek 连接验证通过', 'ok');
    actions.refresh();
  } catch (error) {
    if (result) result.innerHTML = '<div class="msg err" role="status">配置已保存，连接尚未验证：' + esc(String(error)) +
      '。无需再次粘贴密钥，可稍后重试。</div><button class="ghost" type="button" data-action="model-verify">重新验证连接</button>';
    actions.toast('配置已保存，连接尚未验证', 'info');
  }
}
