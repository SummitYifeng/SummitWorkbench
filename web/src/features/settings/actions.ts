import { sendNativeMessage } from '../../lifecycle/native-bridge';
import { esc } from '../../md';
import { getSettingsDeps, api, mutation, toast } from './deps';
import { renderSettings as renderSettingsRenderer } from './render';
import type { AcceptancePreflightPayload, RemoteNormalizationPreviewPayload } from './types';

/** 设置页写动作（原 legacy-main 逐条搬迁）。 */

export async function previewGitRemoteNormalization(): Promise<void> {
  const candidate = (document.getElementById('remote-candidate-url') as HTMLInputElement | null)?.value.trim() ?? '';
  const username = (document.getElementById('remote-github-username') as HTMLInputElement | null)?.value.trim() ?? '';
  const pat = (document.getElementById('remote-github-pat') as HTMLInputElement | null)?.value ?? '';
  if (!candidate || !username || !pat) {
    toast('请填写 HTTPS 地址、GitHub username 和 workspace-scoped PAT', 'err');
    return;
  }
  try {
    const result = await api<RemoteNormalizationPreviewPayload>('/api/settings/git/remote/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_url: candidate, git_username: username, pat }),
    });
    const output = document.getElementById('remote-normalization-result');
    if (output) {
      output.innerHTML = '<div class="success">预览通过：候选仓库已认证、workspace marker、分支/upstream 和 fetch 均通过。' +
        '<br>当前：' + esc(result.old_url) + '<br>候选：' + esc(result.candidate_url) +
        '<br>分支：' + esc(result.branch) + ' · 本机领先 ' + result.candidate_ahead + ' · 远端领先 ' + result.candidate_behind +
        '<div class="row"><button class="primary" type="button" data-action="git-remote-apply" data-plan="' + esc(result.plan_id) + '">确认并转换</button>' +
        '<button class="ghost" type="button" data-action="git-remote-rollback">取消</button></div></div>';
    }
    toast('候选 remote 预览通过；尚未修改本机配置', 'ok');
  } catch (err) {
    toast(err, 'err');
  }
}

export async function applyGitRemoteNormalization(planId: string): Promise<void> {
  if (!window.confirm('确认将 origin 和本机 profile 转换为 HTTPS？不会提交、推送或修改 vault 内容。')) return;
  const username = (document.getElementById('remote-github-username') as HTMLInputElement | null)?.value.trim() ?? '';
  const patInput = document.getElementById('remote-github-pat') as HTMLInputElement | null;
  const pat = patInput?.value ?? '';
  try {
    const result = await api<{ new_url: string }>('/api/settings/git/remote/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId, git_username: username, pat }),
    });
    if (patInput) patInput.value = '';
    const output = document.getElementById('remote-normalization-result');
    if (output) output.innerHTML = '<div class="success">转换完成：' + esc(result.new_url) +
      '<br>未提交、未推送、未修改 vault。若需撤销，可使用“回滚最近一次转换”。</div>';
    toast('Git remote 已转换为 HTTPS', 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    toast(err, 'err');
  }
}

export async function rollbackGitRemoteNormalization(): Promise<void> {
  if (!window.confirm('确认回滚最近一次 remote 转换？')) return;
  try {
    const result = await api<{ restored_url: string }>('/api/settings/git/remote/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true }),
    });
    const output = document.getElementById('remote-normalization-result');
    if (output) output.innerHTML = '<div class="success">已恢复：' + esc(result.restored_url) + '</div>';
    toast('remote 转换已回滚', 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    toast(err, 'err');
  }
}

/** G1：后端稳定错误码 → 用户能照做的短句（绝不把原始文本直接甩给用户）。 */
/** 自动化任务结果的中文口径：后端状态码（success / degraded…）不直接进界面。 */
function automationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    success: '运行成功',
    degraded: '降级完成',
    failed: '运行失败',
    'not-primary': '本机不是主设备',
    skipped: '本次跳过',
  };
  return labels[status] ?? '已完成';
}

const PRIMARY_FAILURE_HINTS: Record<string, string> = {
  primary_already_claimed: '另一台 Mac 已经是主设备。要由本机接管，请先勾选确认再点「接管主设备」。',
  primary_generation_conflict: '主设备声明已经变化（另一台机器刚改过）。请刷新设置页后重新确认。',
  primary_takeover_invalid: '本机已经是主设备，不需要接管。',
  primary_state_corrupt: 'vault 内的主设备声明已损坏，需要人工检查内部文件 .summit-workbench/automation-primary.json。',
  workspace_not_configured: '当前没有已连接的工作台。',
  profile_missing: '本机没有这个工作台的档案。',
};

function primaryFailureMessage(err: unknown): string {
  const code = (err as { code?: string | null } | null)?.code ?? null;
  if (code && PRIMARY_FAILURE_HINTS[code]) return PRIMARY_FAILURE_HINTS[code];
  return String(err);
}

function showPrimaryResult(message: string, ok: boolean): void {
  const output = document.getElementById('primary-claim-result');
  if (output) output.innerHTML = '<div class="' + (ok ? 'success' : 'error') + '">' + esc(message) + '</div>';
}

/**
 * G1：声明/接管主设备。
 *
 * 别的设备持有主设备时必须：勾选确认 + 显式 takeover + 带回当前 generation，三者缺一不发请求。
 */
export async function claimAutomationPrimary(
  deviceId: string,
  takeoverRequested: boolean,
  generation: string,
): Promise<void> {
  if (!deviceId) {
    toast('没有读到本机 device id，请刷新设置页后重试', 'err');
    return;
  }
  const body: Record<string, unknown> = { device_id: deviceId, takeover: takeoverRequested };
  if (takeoverRequested) {
    const ack = document.getElementById('primary-takeover-ack') as HTMLInputElement | null;
    if (!ack?.checked) {
      toast('接管需要先勾选确认（定时自动化会转移到本机）', 'err');
      return;
    }
    const expected = Number(generation);
    if (!Number.isInteger(expected) || expected < 1) {
      toast('没有读到当前 generation，请刷新设置页后重试', 'err');
      return;
    }
    if (!window.confirm('确认由本机接管定时自动化？generation 会递增，另一台机器需要重新确认。')) return;
    body.expected_generation = expected;
  }
  try {
    await api<{ ok: boolean; device_role?: string }>('/api/sync/primary/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const message = takeoverRequested
      ? '已接管主设备：定时自动化现在在本机运行。'
      : '已声明本机为主设备：定时自动化现在在本机运行。';
    showPrimaryResult(message, true);
    toast(message, 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    const message = primaryFailureMessage(err);
    showPrimaryResult(message, false);
    toast(message, 'err');
  }
}

/** G1：降级为备用设备（只改本机档案，vault 内的主设备声明不动）。 */
export async function downgradeAutomationPrimary(): Promise<void> {
  if (!window.confirm('确认本机降级为备用设备？本机将不再运行定时自动化；vault 内的主设备声明保持不变。')) return;
  try {
    await api<{ ok: boolean; device_role: string }>('/api/sync/primary/downgrade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const message = '本机已降级为备用设备：定时自动化不再在本机运行。';
    showPrimaryResult(message, true);
    toast(message, 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    const message = primaryFailureMessage(err);
    showPrimaryResult(message, false);
    toast(message, 'err');
  }
}

/** G2：首次发布的稳定错误码 → 用户能照做的短句。 */
const PUBLISH_FAILURE_HINTS: Record<string, string> = {
  remote_not_empty: '目标远端已有提交：请新建一个空仓库（不要勾选 README / .gitignore）。',
  remote_unreachable: '无法访问目标远端：检查地址、网络或代理设置。',
  git_auth_failed: 'GitHub 用户名或访问令牌不正确（令牌需要 repo 权限）。',
  git_tls_failed: 'HTTPS 证书校验失败：检查系统时间或代理证书。',
  remote_url_userinfo: '地址里不要写用户名或密码，凭据填在下面的输入框里。',
  remote_scheme_unsupported: '只支持 https:// 开头的仓库地址。',
  remote_already_configured: '本工作台已经有远端了；如需更换请用「预览 HTTPS 转换」。',
  dirty_tree: '工作台有未提交改动：请先同步或提交后再发布。',
  vault_has_no_commits: '本工作台还没有任何提交，没有可发布的内容。',
  vault_not_a_repository: '本工作台还没有纳入版本管理：请重新创建工作台，或从另一台 Mac 克隆。',
  remote_publish_failed: '目标远端不可推送：检查令牌权限与仓库设置。',
  remote_publish_rolled_back: '发布失败，已恢复到没有远端的状态，可以修改后重试。',
  git_username_invalid: 'GitHub 用户名不能为空。',
  git_credential_missing: '访问令牌不能为空。',
};

function publishFailureMessage(err: unknown): string {
  const code = (err as { code?: string | null } | null)?.code ?? null;
  if (code && PUBLISH_FAILURE_HINTS[code]) return PUBLISH_FAILURE_HINTS[code];
  return String(err);
}

function showPublishResult(message: string, ok: boolean): void {
  const output = document.getElementById('publish-result');
  if (output) output.innerHTML = '<div class="' + (ok ? 'success' : 'error') + '">' + esc(message) + '</div>';
}

/**
 * G2：把还没有远端的工作台绑定到一个新建的空远端并首次推送。
 *
 * 只走 HTTPS；令牌一次性交给后端，由后端写进本机 Keychain（不进 vault、不进提交）。
 */
export async function publishWorkspaceToRemote(): Promise<void> {
  const candidate = (document.getElementById('publish-remote-url') as HTMLInputElement | null)?.value.trim() ?? '';
  const username = (document.getElementById('publish-github-username') as HTMLInputElement | null)?.value.trim() ?? '';
  const patInput = document.getElementById('publish-github-pat') as HTMLInputElement | null;
  const pat = patInput?.value ?? '';
  if (!candidate || !username || !pat) {
    toast('请填写 HTTPS 地址、GitHub 用户名和访问令牌', 'err');
    return;
  }
  if (!window.confirm('确认把本工作台发布到这个远端？会在远端新建分支并推送当前历史，不会 force。')) return;
  try {
    const result = await api<{ remote_url: string; branch: string }>('/api/settings/git/remote/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_url: candidate, git_username: username, pat }),
    });
    if (patInput) patInput.value = '';
    showPublishResult(
      '已发布到 ' + result.remote_url + '（branch ' + result.branch + '）：origin 与 upstream 已绑定，接下来可以点「立即同步」。',
      true,
    );
    toast('首次发布完成', 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  } catch (err) {
    const message = publishFailureMessage(err);
    showPublishResult(message, false);
    toast(message, 'err');
  }
}

export async function runAcceptancePreflight(): Promise<void> {
  try {
    const result = await api<AcceptancePreflightPayload>('/api/settings/acceptance-preflight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const output = document.getElementById('acceptance-preflight-result');
    if (output) output.innerHTML = '<pre class="diagnostics-output">' + esc(result.report) + '</pre>';
    toast(result.ok ? '验收预检通过' : '验收预检未通过，请查看报告', result.ok ? 'ok' : 'err');
  } catch (err) {
    toast(err, 'err');
  }
}

const FEISHU_STATE_KEY = 'wb.feishu.state';

/**
 * 飞书授权回跳后的结果提示。
 *
 * 分发包内置了应用凭据，同事本机没有可改的配置：授权失败时必须把「找谁、做什么」
 * 显示出来（最常见的失败是管理员还没把他加入应用「可用范围」），而不是静默回到设置页。
 */
export async function reportFeishuCallbackResult(view: HTMLElement): Promise<void> {
  const outcome = new URLSearchParams(window.location.search).get('feishu');
  if (outcome !== 'failed' && outcome !== 'connected') return;
  const target = view.querySelector('#feishu-result');
  const state = sessionStorage.getItem(FEISHU_STATE_KEY) ?? '';
  sessionStorage.removeItem(FEISHU_STATE_KEY);
  let message: string;
  let kind: 'ok' | 'err';
  if (outcome === 'connected') {
    message = '飞书已连接 ✓';
    kind = 'ok';
  } else {
    message = '飞书授权未完成，请重新点击「授权飞书」';
    kind = 'err';
    if (state) {
      try {
        const status = await api<{ status: string; reason?: string | null }>(
          '/api/settings/feishu/status?state=' + encodeURIComponent(state),
        );
        if (status.reason) message = status.reason;
      } catch (_) {
        // 状态已过期：退回兜底文案，不阻断设置页
      }
    }
  }
  if (target) {
    const box = document.createElement('p');
    box.className = kind === 'ok' ? 'hint' : 'error';
    box.textContent = message;
    target.replaceChildren(box);
  }
  toast(message, kind);
  // 清掉查询串：刷新或切换页签时不重复提示
  window.history.replaceState(null, '', window.location.pathname + window.location.hash);
}

export async function renderSettingsView(view: HTMLElement): Promise<void> {
  await renderSettingsRenderer(view, {
    api,
    mutation,
    toast,
    refresh: () => { void renderSettingsView(view); },
  });
  await reportFeishuCallbackResult(view);
}

export async function runAutomationJob(job: string): Promise<void> {
  try {
    const result = await mutation(() => api<{ ok: boolean; status: string; detail?: string | null }>(
      '/api/settings/automation/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job }),
      },
    ));
    toast(result.detail ? result.status + '：' + result.detail : '自动化任务已完成：' + automationStatusLabel(result.status), result.ok ? 'ok' : 'err');
    const view = document.getElementById('view-settings');
    if (view) void renderSettingsView(view);
  } catch (err) {
    toast(err, 'err');
  }
}

export async function copyAutomationSummary(summary: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(summary);
    toast('错误摘要已复制', 'ok');
  } catch {
    toast('复制失败，请手动记录摘要：' + summary, 'err');
  }
}

export async function switchProfile(workspaceId: string): Promise<void> {
  const prepared = await api<{ plan_id: string }>('/api/settings/profile/prepare', {
    method: 'POST', body: JSON.stringify({ workspace_id: workspaceId }),
  });
  const committed = await api<{ restart_required: boolean }>('/api/settings/profile/commit', {
    method: 'POST', body: JSON.stringify({ plan_id: prepared.plan_id }),
  });
  getSettingsDeps()?.clearDraftSnapshot(getSettingsDeps()?.workspaceId());
  getSettingsDeps()?.disposeWorkspaceStore();
  getSettingsDeps()?.disposeApiClient();
  if (committed.restart_required && sendNativeMessage({ type: 'quit' })) return;
  window.location.reload();
}

export async function migrateWorkspace(deviceId: string): Promise<void> {
  if (!window.confirm('迁移前必须确认同步状态正常、工作树干净且远端可达。确定由当前 Mac 执行？')) return;
  try {
    const result = await mutation(() => api<{ status: string; restart_required?: boolean }>('/api/workspace/migration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed_device_id: deviceId }),
    }));
    toast(result.status === 'already-current' ? '工作区已经是最新 schema' : '工作区迁移完成，即将重新打开', 'ok');
    if (result.status !== 'already-current' && sendNativeMessage({ type: 'quit' })) return;
    window.location.reload();
  } catch (err) {
    toast(err, 'err');
  }
}

export async function runSettingsDoctor(online = false): Promise<void> {
  const result = await api<{ ok: boolean; checks: { name: string; status: string; detail: string }[] }>(
    '/api/settings/doctor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ online }),
    },
  );
  const failed = result.checks.filter((check) => check.status === 'fail').length;
  const label = online ? '在线检查' : '离线检查';
  toast(failed ? label + '发现 ' + failed + ' 项问题' : label + '完成', failed ? 'err' : 'ok');
}

/** data-action="profile-remove"：移除本机 profile（原派发器内联分支）。 */
export function removeProfile(workspaceId: string): void {
  if (!workspaceId || !window.confirm('只移除本机 profile/runtime，不删除 vault、远端或 Keychain。确定继续？')) return;
  // 移除当前工作台时后端返回 restart_required：运行中的服务仍绑着它，必须重启才生效。
  void api<{ ok: boolean; restart_required?: boolean }>('/api/settings/profile/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId, confirmed: true }),
  }).then((result) => {
    toast(result.restart_required ? '本机 profile 已移除；重启工作台后生效' : '本机 profile 已移除', 'ok');
    void renderSettingsView(document.getElementById('view-settings') as HTMLElement);
  })
    .catch((err: unknown) => toast(err, 'err'));
}

/** data-action="settings-doctor-online"：带确认的在线检查（原派发器内联分支）。 */
export function runSettingsDoctorOnline(): void {
  if (!window.confirm('在线检查会访问 provider，并可能轮换飞书 token。确定继续？')) return;
  void runSettingsDoctor(true).catch((err: unknown) => toast(err, 'err'));
}

/** data-action="reopen-onboarding"（原派发器内联分支）。 */
export function reopenOnboarding(): void {
  window.location.href = '/onboarding';
}

/** data-action="feishu-reauth"（原派发器内联分支）。 */
export function authorizeFeishu(): void {
  void api<{ authorize_url: string; state?: string }>('/api/settings/feishu/authorize-url', { method: 'POST' })
    .then((result) => {
      // 记住 state，才能在回跳失败时取回具体原因（见 reportFeishuCallbackResult）
      if (result.state) sessionStorage.setItem(FEISHU_STATE_KEY, result.state);
      window.location.href = result.authorize_url;
    })
    .catch((err: unknown) => toast(err, 'err'));
}
