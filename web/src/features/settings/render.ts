/** 设置页渲染与只读数据读取（原 features/settings/index.ts，Step 8c 拆分）。 */
import { esc } from '../../md';
import { formatBusinessTime } from '../../core/time';
import { sendNativeMessage } from '../../lifecycle/native-bridge';
import { syncEvidenceLabel, syncStateLabel } from '../sync/labels';

export interface ProfileSummary {
  workspace_id: string;
  workspace_short_code: string;
  display_name: string;
  path: string;
  compatibility: string;
  device_role: string;
  active: boolean;
  provider_status: Record<string, string>;
  sync_summary: { state: string; pending_commits: number | null };
  remote_url?: string | null;
}

interface ProfileList { profiles: ProfileSummary[]; current_device_id?: string | null }
interface AutomationJob {
  enabled: boolean; hour: number; minute: number; weekdays: number[];
  last_run_at?: string | null; last_success_at?: string | null;
  retry_at?: string | null; next_run_at?: string | null;
  last_error_code?: string | null; last_status: string; last_detail?: string | null;
  supported?: boolean; unavailable_reason?: string | null;
}
interface AutomationSettings { jobs: Record<string, AutomationJob> }

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

/** `/api/sync/status` 里与 automation-primary 归属有关的字段（G1）。 */
export interface SyncPrimaryStatus {
  remote_checked_at?: string | null;
  remote_check_status?: string;
  automation_primary_device_id?: string | null;
  automation_primary_generation?: number | null;
}

export interface SettingsActions {
  api: <T>(url: string, init?: RequestInit) => Promise<T>;
  mutation: <T>(request: () => Promise<T>) => Promise<T>;
  toast: (message: unknown, kind?: 'ok' | 'err' | 'info') => void;
  refresh: () => void;
  /** 「立即运行」的注入入口（不传时退回全局动作，避免循环依赖）。 */
  runJob?: (job: string) => Promise<void>;
}

const AUTOMATION_LABELS: Record<string, string> = {
  brief: '晨间简报', weekly: '每周复盘', 'meeting-sync': '会议同步',
};
const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

function badge(kind: 'model' | 'feishu', status: string | undefined, reauth = false): string {
  if (kind === 'feishu' && reauth) return '<span class="conn-badge reauth">⚠ 需重新授权</span>';
  if (status === 'configured') {
    return '<span class="conn-badge ok">✓ 已' + (kind === 'feishu' ? '授权' : '配置') + '</span>';
  }
  if (status === 'error' || status === 'failed' || status === 'verification-failed') {
    return '<span class="conn-badge failed">✗ 验证失败</span>';
  }
  return '<span class="conn-badge off">' + (kind === 'model' ? '未配置' : '未连接') + '</span>';
}

function automationHtml(job: string, schedule: AutomationJob): string {
  const time = String(schedule.hour).padStart(2, '0') + ':' + String(schedule.minute).padStart(2, '0');
  const status: Record<string, string> = {
    never: '尚未运行', success: '运行成功', degraded: '降级完成', failed: '运行失败',
    'not-primary': '本机不是主设备', skipped: '本次跳过',
  };
  const attempt = schedule.last_run_at ? ' · ' + esc(formatBusinessTime(schedule.last_run_at)) : '';
  const success = schedule.last_success_at ? esc(formatBusinessTime(schedule.last_success_at)) : '—';
  const next = schedule.retry_at ?? schedule.next_run_at;
  const nextLine = next ? esc(formatBusinessTime(next)) : '—';
  const supported = schedule.supported !== false;
  const unavailable = supported ? '' : '<div class="meta automation-detail">自动会议同步暂不可用；请到「今日」页点击“导入会议纪要”上传逐字稿。</div>';
  const disabled = supported ? '' : ' disabled';
  return '<form class="card automation-form" data-job="' + esc(job) + '"><div class="automation-row"><div><strong>' +
    esc(AUTOMATION_LABELS[job] ?? job) + '</strong><div class="meta" title="内部状态码：' + esc(schedule.last_status) + '">最近：' +
    esc(status[schedule.last_status] ?? '未知状态') +
    attempt + '</div><div class="meta">上次成功：' + success + ' · 下次尝试：' + nextLine + '</div>' +
    (schedule.last_detail ? '<div class="meta automation-detail">' + esc(schedule.last_detail) + '</div>' : '') + unavailable +
    '</div><label class="automation-enabled"><input name="enabled" type="checkbox"' + (schedule.enabled ? ' checked' : '') + disabled + '>' + (supported ? '启用定时' : '暂不可用') + '</label></div>' +
    '<div class="automation-controls"><label>时间 <input name="time" type="time" value="' + time + '"></label><span class="meta">星期</span>' +
    WEEKDAY_LABELS.map((label, index) => '<label class="weekday"><input name="weekday" type="checkbox" value="' + index + '"' +
      (schedule.weekdays.includes(index) ? ' checked' : '') + '>' + label + '</label>').join('') + '</div>' +
    '<div class="row"><button class="primary" type="submit">保存</button><button class="ghost" type="button" data-action="automation-run" data-job="' +
    esc(job) + '"' + disabled + '>立即运行</button></div></form>';
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

function httpsCandidate(url: string | null | undefined): string {
  if (!url) return '';
  if (url.startsWith('https://')) return url;
  const match = url.match(/^git@github\.com:(.+)$/);
  return match ? 'https://github.com/' + match[1] : '';
}

/**
 * G1：定时自动化主设备的显式入口（此前只有后端 API，界面没有任何入口）。
 *
 * 三种状态分别给不同动作：本机已是主设备（幂等说明）、尚无声明（直接声明）、
 * 别的设备持有（必须勾选确认 + 带回当前 generation 才能接管）。本机角色为
 * automation-primary 时另给降级入口，否则角色只能升不能降。
 */
function primaryRoleHtml(
  currentDeviceId: string | null | undefined,
  role: string | undefined,
  primaryDeviceId: string | null | undefined,
  generation: number | null | undefined,
): string {
  const localId = currentDeviceId ?? '';
  const isLocalPrimary = Boolean(primaryDeviceId) && primaryDeviceId === localId;
  const generationText = generation === null || generation === undefined ? '' : String(generation);
  const roleLabel = role === 'automation-primary'
    ? '主设备（定时自动化在本机运行）'
    : '备用设备（不运行定时自动化）';
  let action: string;
  if (isLocalPrimary) {
    action = '<button class="primary" type="button" disabled>本机已是主设备</button>';
  } else if (!primaryDeviceId) {
    action = '<button class="primary" type="button" data-action="primary-claim" data-device="' + esc(localId) +
      '" data-takeover="false">声明本机为主设备</button>';
  } else {
    action = '<label class="automation-enabled"><input id="primary-takeover-ack" type="checkbox">我确认由本机接管定时自动化</label>' +
      '<button class="primary" type="button" data-action="primary-claim" data-device="' + esc(localId) +
      '" data-takeover="true" data-generation="' + esc(generationText) + '">接管主设备</button>';
  }
  const downgrade = role === 'automation-primary'
    ? '<button class="ghost" type="button" data-action="primary-downgrade">降级为备用设备</button>'
    : '';
  // 对外不显示设备 id / generation 这类内部标识：主设备说「本机 / 另一台机器」，代际说「第 N 代」。
  const primaryLine = primaryDeviceId
    ? (isLocalPrimary ? '本机' : '另一台机器') +
      (generationText ? ' · 第 ' + esc(generationText) + ' 代' : '')
    : '（尚未声明：定时自动化不会在任何机器上运行）';
  // 设备标识（UUID）只在排查问题时有用 ⇒ 收进折叠区，需要时给支持人员看。
  const idsDetail = '<details class="settings-ids"><summary>设备标识（排查问题时才需要）</summary>' +
    '<div class="settings-path"><span class="meta">本机 device id：' + esc(localId || '（未读到）') + '</span></div>' +
    (primaryDeviceId
      ? '<div class="settings-path"><span class="meta">当前主设备 device id：' + esc(primaryDeviceId) + '</span></div>'
      : '') +
    '</details>';
  return '<section class="block"><h3 class="section-title">定时自动化主设备</h3>' +
    '<p class="hint">同一时间只应有一台 Mac 跑定时自动化。接管会把归属转到本机、代际加一（第 N 代 → 第 N+1 代），并需要与另一台机器沟通。</p>' +
    '<div class="settings-path"><span class="meta">当前主设备：' + primaryLine + '</span></div>' +
    '<div class="settings-path"><span class="meta">本机角色：' + esc(roleLabel) + '</span></div>' +
    (primaryDeviceId && !isLocalPrimary
      ? '<p class="hint">接管后果：定时自动化转移到本机、代际加一，另一台机器需要重新声明或确认。</p>'
      : '') +
    '<div class="row">' + action + downgrade + '</div>' + idsDetail +
    '<div id="primary-claim-result"></div></section>';
}

/**
 * 设置页渲染序号：保存/刷新/切页会并发触发多次读取，先发起的旧响应
 * 不得覆盖后发起的新内容（例如刚保存模型后的刷新被保存前的读取盖回）。
 */
let settingsRenderSequence = 0;

export async function renderSettings(view: HTMLElement, actions: SettingsActions): Promise<void> {
  const requestId = ++settingsRenderSequence;
  view.innerHTML = '<div class="loading">正在读取设置…</div>';
  try {
    const [response, automation, state, sync, modelParams] = await Promise.all([
      actions.api<ProfileList>('/api/settings/profiles'),
      actions.api<AutomationSettings>('/api/settings/automation'),
      actions.api<{ status: { feishu_auth?: { needs_reauthorize?: boolean } } }>('/api/state'),
      actions.api<SyncPrimaryStatus>('/api/sync/status'),
      // 只读参数卡：读不到就降级为不显示，绝不让整页失败（设置页曾经因为一个
      // 接口 409 整页变成错误页）。
      actions.api<ModelParameterPayload>('/api/settings/model-parameters').catch(() => null),
    ]);
    if (requestId !== settingsRenderSequence) return;
    const active = response.profiles.find((p) => p.active) ?? response.profiles[0];
    const modelStatus = active?.provider_status.model;
    const feishuStatus = active?.provider_status.feishu;
    const feishuReauth = Boolean(state.status.feishu_auth?.needs_reauthorize);
    const workspace = active
      ? '<div class="settings-path">' + esc(active.display_name) + '<span class="meta">' + esc(active.path) + '</span></div>'
      : '<div class="settings-path">（尚无工作区）</div>';
    const model = '<div class="card settings-card" id="model-card"><div class="card-head"><strong>AI 模型（DeepSeek）</strong>' + badge('model', modelStatus) + '</div>' +
      '<p class="settings-card-desc">会议结构化、简报和任务分类都靠它。第一次使用只需粘贴 API Key，点「连接并验证」。</p>' +
      '<form id="model-settings-form" autocomplete="off"><label>DeepSeek API Key<input id="model-secret" type="password" autocomplete="new-password" placeholder="sk-…"></label>' +
      '<div class="row"><button class="primary" type="submit">连接并验证</button><button class="ghost" id="model-show-advanced" type="button">自定义模型（一般不用）</button></div>' +
      '<div class="settings-advanced" id="model-advanced" hidden><div class="grid2"><label>模型 ID<input id="model-id" value="deepseek-flash"></label>' +
      '<label>服务地址<input id="model-base-url" value="https://api.deepseek.com/v1"></label></div><p class="hint">默认使用 DeepSeek 官方地址；只有特殊网关才需要改。</p></div></form><div id="model-result"></div></div>';
    const modelParameters = modelParameterCard(modelParams);
    const feishu = '<div class="card settings-card"><div class="card-head"><strong>飞书</strong>' + badge('feishu', feishuStatus, feishuReauth) + '</div>' +
      '<p class="settings-card-desc">授权后，工作台才能读日历和任务，也能把完成动作写回飞书。</p><div class="row"><button class="primary" data-action="feishu-reauth">' +
      (feishuReauth || feishuStatus !== 'configured' ? '授权飞书' : '重新授权飞书') + '</button><button class="ghost" data-action="settings-doctor-online">检查飞书连接</button></div><div id="feishu-result"></div></div>';
    const automationCard = '<div class="card settings-card"><div class="card-head"><strong>自动化与更新</strong><span class="conn-badge off">按需开启</span></div>' +
      '<p class="settings-card-desc">像闹钟一样自动生成简报、复盘和同步会议；开着才会自动跑。</p>' +
      Object.entries(automation.jobs).map(([job, schedule]) => automationHtml(job, schedule)).join('') +
      '<div class="settings-update"><label class="automation-enabled"><input id="auto-update-check" type="checkbox"' +
      (localStorage.getItem('wb.update.auto-check') !== 'false' ? ' checked' : '') + '>每天自动检查新版本（只提示，不自动安装）</label></div></div>';
    const profiles = response.profiles.map((profile) => '<article class="card entry ' + (profile.active ? 'ok' : '') + '"><div class="entry-top"><strong>' +
      esc(profile.display_name) + '</strong><span class="badge">' + esc(profile.active ? '当前' : '其他工作台') + '</span></div><p class="meta">' +
      esc(profile.path) + '</p><p class="meta">同步：' + esc(syncStateLabel(profile.sync_summary.state)) + ' · ' + esc(syncEvidenceLabel(sync?.remote_check_status, sync?.remote_checked_at)) + ' · 连接：' + badge('model', profile.provider_status.model) + ' ' +
      badge('feishu', profile.provider_status.feishu, feishuReauth) + '</p>' +
      (profile.active ? '' : '<button class="primary" data-action="profile-switch" data-workspace="' + esc(profile.workspace_id) + '">切换到它</button>') +
      // 移除此 Mac 上的 profile：只删本机 profile/runtime/草稿，vault、远端与 Keychain 不动。
      // 当前工作台也能移除（后端返回 restart_required），否则没有第二台工作台时就永远删不掉。
      '<button class="ghost" data-action="profile-remove" data-workspace="' + esc(profile.workspace_id) + '">移除此 Mac 上的工作台</button>' +
      '</article>').join('');
    const removeHint = response.profiles.some((profile) => profile.active)
      ? '<p class="hint">移除只影响这台 Mac：vault、远端仓库和 Keychain 凭据都不动。移除当前工作台后，需要重启工作台才会生效。</p>'
      : '';
    // G2：还没有远端的工作台此前只能手工 git remote add / push。这里给一条可执行的发布路径：
    // 先在 GitHub 建**空**仓库（不勾选 README），再把 HTTPS 地址 + 用户名 + 令牌填进来。
    const publishSection = active && !active.remote_url
      ? '<section class="block"><h3 class="section-title">首次发布到远端</h3>' +
        '<p class="hint">本工作台还没有远端，所以无法在多台 Mac 之间同步。先到 GitHub 新建一个<strong>空</strong>仓库' +
        '（不要勾选 README / .gitignore / license），再把它的 HTTPS 地址填到下面。' +
        '发布只会新建分支并推送当前历史，<strong>不会</strong> force，也不会改动工作台里的文件。</p>' +
        '<div class="settings-path"><span class="meta">即将发布：' + esc(active.path) + '</span></div>' +
        '<form id="git-remote-publish-form"><div class="grid2">' +
        '<label>HTTPS 仓库地址<input id="publish-remote-url" placeholder="https://github.com/用户名/仓库.git"></label>' +
        '<label>GitHub 用户名<input id="publish-github-username"></label>' +
        '<label>访问令牌（仅本次使用）<input id="publish-github-pat" type="password"></label></div>' +
        '<p class="hint">令牌只写入这台 Mac 的 Keychain，不会进 vault、不会进提交。</p>' +
        '<div class="row"><button class="primary" type="button" data-action="git-remote-publish">绑定并首次发布</button></div></form>' +
        '<div id="publish-result"></div></section>'
      : '';
    const advanced = '<details class="settings-advanced-block"><summary><span class="bf-chev">›</span>高级与维护（自动化 · 模型参数 · 多工作台 · Git 同步 · 诊断）</summary>' +
      // 「自动化与更新」与「模型参数（只读）」原在主区，2026-09-18 按使用者要求移入这里：
      // 主区只留 工作区 / AI 模型 / 飞书 三张卡，每张一行。
      '<section class="block"><h3 class="section-title">自动化与更新</h3><p class="hint">像闹钟一样自动生成简报、复盘和同步会议；开着才会自动跑。勾选「启用定时」后必须点「保存」。</p>' + automationCard + '</section>' +
      (modelParameters === '' ? '' : '<section class="block"><h3 class="section-title">模型参数（只读）</h3>' + modelParameters + '</section>') +
      '<section class="block"><h3 class="section-title">工作台切换</h3><p class="hint">同一时间只打开一个工作台；切换前会先完成安全检查。</p>' + profiles + removeHint + '</section>' +
      '<section class="block"><h3 class="section-title">Git 同步</h3><p class="hint">需要多台设备同步时再使用。系统会先验证，不会把访问令牌写进 vault。</p>' +
      '<form id="remote-normalization-form"><div class="grid2"><label>HTTPS 仓库地址<input id="remote-candidate-url" value="' + esc(httpsCandidate(active?.remote_url)) + '"></label>' +
      '<label>GitHub 用户名<input id="remote-github-username"></label><label>访问令牌（仅本次使用）<input id="remote-github-pat" type="password"></label></div>' +
      '<div class="row"><button class="primary" type="button" data-action="git-remote-preview">预览 HTTPS 转换</button><button class="ghost" type="button" data-action="git-remote-rollback">回滚最近一次转换</button></div></form><div id="remote-normalization-result"></div></section>' +
      primaryRoleHtml(response.current_device_id, active?.device_role, sync?.automation_primary_device_id, sync?.automation_primary_generation) +
      publishSection +
      '<section class="block"><h3 class="section-title">健康检查</h3><p class="hint">离线检查不联网；在线检查会真实访问模型与飞书。</p><div class="row"><button class="ghost" data-action="settings-doctor">离线检查</button><button class="ghost" data-action="settings-doctor-online">在线检查</button></div></section>' +
      '<section class="block"><h3 class="section-title">诊断与支持</h3><div class="row"><button class="ghost" data-action="diagnostics-preview">查看诊断包清单</button><button class="ghost" data-action="diagnostics-export">导出诊断包</button><button class="ghost" data-action="diagnostics-open-log">打开日志目录</button></div><div id="diagnostics-preview"></div></section></details>';
    view.innerHTML = '<div class="settings-head"><h2 class="page-title">设置</h2><p class="hint">常用连接在这里完成；高级选项默认收起来。</p><button class="ghost" data-action="reopen-onboarding">重新打开连接向导</button></div><section class="settings-grid settings-grid-single">' +
      // 主区三张卡，每张一行（使用者要求：工作区 / AI 模型 / 飞书）。
      '<div class="card settings-card"><div class="card-head"><strong>工作区</strong><span class="conn-badge ok">✓ 已就绪</span></div><p class="settings-card-desc">会议、任务和项目都整理在这个文件夹里。</p>' + workspace + '</div>' + model + feishu + '</section><section class="block">' + advanced + '</section>';

    view.querySelector<HTMLFormElement>('#model-settings-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      void saveModel(view, actions);
    });
    view.querySelectorAll<HTMLFormElement>('.automation-form').forEach((form) => form.addEventListener('submit', (event) => {
      event.preventDefault();
      void saveAutomation(form, actions);
    }));
    view.querySelectorAll<HTMLButtonElement>('[data-action="automation-run"]').forEach((btn) => btn.addEventListener('click', (event) => {
      event.preventDefault();
      void runAutomationFromForm(btn, actions);
    }));
    view.querySelector<HTMLButtonElement>('#model-show-advanced')?.addEventListener('click', (event) => {
      const box = view.querySelector<HTMLElement>('#model-advanced');
      if (!box) return;
      box.hidden = !box.hidden;
      (event.currentTarget as HTMLButtonElement).textContent = box.hidden ? '自定义模型（一般不用）' : '收起自定义';
    });
    view.querySelector<HTMLInputElement>('#auto-update-check')?.addEventListener('change', (event) => {
      const enabled = (event.target as HTMLInputElement).checked;
      localStorage.setItem('wb.update.auto-check', enabled ? 'true' : 'false');
      sendNativeMessage({ type: 'updateAutoCheckChanged', enabled });
      actions.toast(enabled ? '已开启每天自动检查更新' : '已关闭自动检查更新', 'ok');
    });
  } catch (error) {
    if (requestId !== settingsRenderSequence) return;
    view.innerHTML = '<div class="error">设置暂时无法读取：' + esc(String(error)) + '</div>';
  }
}

async function saveModel(view: HTMLElement, actions: SettingsActions): Promise<void> {
  const secret = view.querySelector<HTMLInputElement>('#model-secret')?.value.trim() ?? '';
  const modelId = view.querySelector<HTMLInputElement>('#model-id')?.value.trim() || 'deepseek-flash';
  const baseUrl = view.querySelector<HTMLInputElement>('#model-base-url')?.value.trim() || 'https://api.deepseek.com/v1';
  const result = view.querySelector<HTMLElement>('#model-result');
  if (!secret) { actions.toast('请先粘贴 DeepSeek API Key', 'err'); return; }
  if (result) result.innerHTML = '<p class="meta">正在连接 DeepSeek 验证…</p>';
  try {
    await actions.api('/api/settings/provider', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      provider: 'model', settings: { capability: 'shared', credential_capability: 'shared', model_id: modelId, base_url: baseUrl, credential_account: 'shared' }, secret,
    }) });
    const verified = await actions.api<{ ok: boolean; message: string }>('/api/settings/provider/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: 'model' }) });
    if (result) result.innerHTML = '<div class="msg ok">✓ 已连接 DeepSeek：' + esc(verified.message) + '</div>';
    actions.toast('DeepSeek 已连接 ✓', 'ok');
    if (view.querySelector<HTMLInputElement>('#model-secret')) view.querySelector<HTMLInputElement>('#model-secret')!.value = '';
    actions.refresh();
  } catch (error) {
    if (result) result.innerHTML = '<div class="msg err">✗ ' + esc(String(error)) + '</div>';
    actions.toast(error, 'err');
  }
}

export function automationFormPayload(form: HTMLFormElement): {
  job: string | undefined;
  enabled: boolean;
  hour: number;
  minute: number;
  weekdays: number[];
} {  const [hour, minute] = ((form.elements.namedItem('time') as HTMLInputElement).value || '08:00').split(':').map(Number);
  const weekdays = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')).map((input) => Number(input.value));
  return {
    job: form.dataset.job,
    enabled: (form.elements.namedItem('enabled') as HTMLInputElement).checked,
    hour,
    minute,
    weekdays,
  };
}

export async function saveAutomation(form: HTMLFormElement, actions: SettingsActions): Promise<boolean> {
  const payload = automationFormPayload(form);
  try {
    await actions.api('/api/settings/automation', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    sendNativeMessage({ type: 'automationSettingsChanged', enabled: payload.enabled });
    actions.toast('自动化设置已保存', 'ok');
    return true;
  } catch (error) { actions.toast(error, 'err'); return false; }
}

/**
 * 「立即运行」：**先保存当前表单，再运行**。
 *
 * 2026-09-18 使用者反馈：在卡片里勾上「启用」后直接点「立即运行」，右下角一直显示
 * `skipped：任务未启用`。原因是复选框只是表单字段，没点「保存」就从未落盘，而后端
 * 按**已保存**的开关判定是否运行 ⇒ 手动运行读到的仍是 disabled，且界面上完全看不出
 * 「勾了但没保存」。这里把两者绑定：先落盘（只有保存成功才继续），再触发运行。
 */
export async function runAutomationFromForm(btn: HTMLElement, actions: SettingsActions): Promise<void> {
  const job = btn.dataset.job ?? '';
  if (!job) return;
  const form = btn.closest('form');
  // 用方法存在性判断而不是 ``instanceof HTMLFormElement``：后者在跨 realm / 测试桩下不可靠，
  // 而「有没有表单」这里只影响是否先保存。
  if (form && typeof (form as HTMLFormElement).elements?.namedItem === 'function') {
    const saved = await saveAutomation(form as HTMLFormElement, actions);
    if (!saved) return; // 保存失败已由 saveAutomation 提示；此处不运行，避免再次给出误导性的「未启用」
  }
  if (actions.runJob) await actions.runJob(job);
  actions.refresh();
}
