/** 设置页渲染与只读数据读取（原 features/settings/index.ts，Step 8c 拆分）。 */
import { esc } from '../../md';
import { sendNativeMessage } from '../../lifecycle/native-bridge';

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
  last_run_at?: string | null; last_status: string; last_detail?: string | null;
}
interface AutomationSettings { jobs: Record<string, AutomationJob> }

export interface SettingsActions {
  api: <T>(url: string, init?: RequestInit) => Promise<T>;
  mutation: <T>(request: () => Promise<T>) => Promise<T>;
  toast: (message: string, kind?: 'ok' | 'err' | 'info') => void;
  refresh: () => void;
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
  return '<form class="card automation-form" data-job="' + esc(job) + '"><div class="automation-row"><div><strong>' +
    esc(AUTOMATION_LABELS[job] ?? job) + '</strong><div class="meta">最近：' + esc(status[schedule.last_status] ?? schedule.last_status) +
    (schedule.last_run_at ? ' · ' + esc(schedule.last_run_at) : '') + '</div>' +
    (schedule.last_detail ? '<div class="meta automation-detail">' + esc(schedule.last_detail) + '</div>' : '') +
    '</div><label class="automation-enabled"><input name="enabled" type="checkbox"' + (schedule.enabled ? ' checked' : '') + '>启用</label></div>' +
    '<div class="automation-controls"><label>时间 <input name="time" type="time" value="' + time + '"></label><span class="meta">星期</span>' +
    WEEKDAY_LABELS.map((label, index) => '<label class="weekday"><input name="weekday" type="checkbox" value="' + index + '"' +
      (schedule.weekdays.includes(index) ? ' checked' : '') + '>' + label + '</label>').join('') + '</div>' +
    '<div class="row"><button class="primary" type="submit">保存</button><button class="ghost" type="button" data-action="automation-run" data-job="' +
    esc(job) + '">立即运行</button></div></form>';
}

function httpsCandidate(url: string | null | undefined): string {
  if (!url) return '';
  if (url.startsWith('https://')) return url;
  const match = url.match(/^git@github\.com:(.+)$/);
  return match ? 'https://github.com/' + match[1] : '';
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
    const [response, automation, state] = await Promise.all([
      actions.api<ProfileList>('/api/settings/profiles'),
      actions.api<AutomationSettings>('/api/settings/automation'),
      actions.api<{ status: { feishu_auth?: { needs_reauthorize?: boolean } } }>('/api/state'),
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
      '<p class="settings-card-desc">简报、任务分类和智能问答都靠它。第一次使用只需粘贴 API Key，点「连接并验证」。</p>' +
      '<form id="model-settings-form" autocomplete="off"><label>DeepSeek API Key<input id="model-secret" type="password" autocomplete="new-password" placeholder="sk-…"></label>' +
      '<div class="row"><button class="primary" type="submit">连接并验证</button><button class="ghost" id="model-show-advanced" type="button">自定义模型（一般不用）</button></div>' +
      '<div class="settings-advanced" id="model-advanced" hidden><div class="grid2"><label>模型 ID<input id="model-id" value="deepseek-v4-flash"></label>' +
      '<label>服务地址<input id="model-base-url" value="https://api.deepseek.com/v1"></label></div><p class="hint">默认使用 DeepSeek 官方地址；只有特殊网关才需要改。</p></div></form><div id="model-result"></div></div>';
    const feishu = '<div class="card settings-card"><div class="card-head"><strong>飞书</strong>' + badge('feishu', feishuStatus, feishuReauth) + '</div>' +
      '<p class="settings-card-desc">授权后，工作台才能读日历和任务，也能把完成动作写回飞书。</p><div class="row"><button class="primary" data-action="feishu-reauth">' +
      (feishuReauth || feishuStatus !== 'configured' ? '授权飞书' : '重新授权飞书') + '</button><button class="ghost" data-action="settings-doctor-online">检查飞书连接</button></div><div id="feishu-result"></div></div>';
    const automationCard = '<div class="card settings-card"><div class="card-head"><strong>自动化与更新</strong><span class="conn-badge off">按需开启</span></div>' +
      '<p class="settings-card-desc">像闹钟一样自动生成简报、复盘和同步会议；开着才会自动跑。</p>' +
      Object.entries(automation.jobs).map(([job, schedule]) => automationHtml(job, schedule)).join('') +
      '<div class="settings-update"><label class="automation-enabled"><input id="auto-update-check" type="checkbox"' +
      (localStorage.getItem('wb.update.auto-check') !== 'false' ? ' checked' : '') + '>每天自动检查新版本（只提示，不自动安装）</label></div></div>';
    const profiles = response.profiles.map((profile) => '<article class="card entry ' + (profile.active ? 'ok' : '') + '"><div class="entry-top"><strong>' +
      esc(profile.display_name) + '</strong><span class="badge">' + esc(profile.active ? '当前' : profile.workspace_short_code) + '</span></div><p class="meta">' +
      esc(profile.path) + '</p><p class="meta">同步：' + esc(profile.sync_summary.state) + ' · 连接：' + badge('model', profile.provider_status.model) + ' ' +
      badge('feishu', profile.provider_status.feishu, feishuReauth) + '</p>' +
      (profile.active ? '' : '<button class="primary" data-action="profile-switch" data-workspace="' + esc(profile.workspace_id) + '">切换到它</button>') +
      // 移除此 Mac 上的 profile：只删本机 profile/runtime/草稿，vault、远端与 Keychain 不动。
      // 当前工作台也能移除（后端返回 restart_required），否则没有第二台工作台时就永远删不掉。
      '<button class="ghost" data-action="profile-remove" data-workspace="' + esc(profile.workspace_id) + '">移除此 Mac 上的工作台</button>' +
      '</article>').join('');
    const removeHint = response.profiles.some((profile) => profile.active)
      ? '<p class="hint">移除只影响这台 Mac：vault、远端仓库和 Keychain 凭据都不动。移除当前工作台后，需要重启工作台才会生效。</p>'
      : '';
    const advanced = '<details class="settings-advanced-block"><summary><span class="bf-chev">›</span>高级与维护（多工作台 · Git 同步 · 诊断）</summary>' +
      '<section class="block"><h3 class="section-title">工作台切换</h3><p class="hint">同一时间只打开一个工作台；切换前会先完成安全检查。</p>' + profiles + removeHint + '</section>' +
      '<section class="block"><h3 class="section-title">Git 同步</h3><p class="hint">需要多台设备同步时再使用。系统会先验证，不会把访问令牌写进 vault。</p>' +
      '<form id="remote-normalization-form"><div class="grid2"><label>HTTPS 仓库地址<input id="remote-candidate-url" value="' + esc(httpsCandidate(active?.remote_url)) + '"></label>' +
      '<label>GitHub 用户名<input id="remote-github-username"></label><label>访问令牌（仅本次使用）<input id="remote-github-pat" type="password"></label></div>' +
      '<div class="row"><button class="primary" type="button" data-action="git-remote-preview">预览 HTTPS 转换</button><button class="ghost" type="button" data-action="git-remote-rollback">回滚最近一次转换</button></div></form><div id="remote-normalization-result"></div></section>' +
      '<section class="block"><h3 class="section-title">健康检查</h3><p class="hint">离线检查不联网；在线检查会真实访问模型与飞书。</p><div class="row"><button class="ghost" data-action="settings-doctor">离线检查</button><button class="ghost" data-action="settings-doctor-online">在线检查</button></div></section>' +
      '<section class="block"><h3 class="section-title">诊断与支持</h3><div class="row"><button class="ghost" data-action="diagnostics-preview">查看诊断包清单</button><button class="ghost" data-action="diagnostics-export">导出诊断包</button><button class="ghost" data-action="diagnostics-open-log">打开日志目录</button></div><div id="diagnostics-preview"></div></section></details>';
    view.innerHTML = '<div class="settings-head"><h2 class="page-title">设置</h2><p class="hint">常用连接在这里完成；高级选项默认收起来。</p><button class="ghost" data-action="reopen-onboarding">重新打开连接向导</button></div><section class="settings-grid">' +
      '<div class="card settings-card"><div class="card-head"><strong>工作区</strong><span class="conn-badge ok">✓ 已就绪</span></div><p class="settings-card-desc">会议、任务和项目都整理在这个文件夹里。</p>' + workspace + '</div>' + model + feishu + automationCard + '</section><section class="block">' + advanced + '</section>';

    view.querySelector<HTMLFormElement>('#model-settings-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      void saveModel(view, actions);
    });
    view.querySelectorAll<HTMLFormElement>('.automation-form').forEach((form) => form.addEventListener('submit', (event) => {
      event.preventDefault();
      void saveAutomation(form, actions);
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
  const modelId = view.querySelector<HTMLInputElement>('#model-id')?.value.trim() || 'deepseek-v4-flash';
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
    actions.toast(String(error), 'err');
  }
}

async function saveAutomation(form: HTMLFormElement, actions: SettingsActions): Promise<void> {
  const [hour, minute] = ((form.elements.namedItem('time') as HTMLInputElement).value || '08:00').split(':').map(Number);
  const weekdays = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')).map((input) => Number(input.value));
  try {
    await actions.api('/api/settings/automation', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      job: form.dataset.job, enabled: (form.elements.namedItem('enabled') as HTMLInputElement).checked, hour, minute, weekdays,
    }) });
    sendNativeMessage({ type: 'automationSettingsChanged', enabled: Boolean(document.querySelector('.automation-form input[name="enabled"]:checked')) });
    actions.toast('自动化设置已保存', 'ok');
  } catch (error) { actions.toast(String(error), 'err'); }
}
