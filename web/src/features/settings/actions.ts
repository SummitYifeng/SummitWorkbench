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
        '<br>branch：' + esc(result.branch) + ' · ahead ' + result.candidate_ahead + ' · behind ' + result.candidate_behind +
        '<div class="row"><button class="primary" type="button" data-action="git-remote-apply" data-plan="' + esc(result.plan_id) + '">确认并转换</button>' +
        '<button class="ghost" type="button" data-action="git-remote-rollback">取消</button></div></div>';
    }
    toast('候选 remote 预览通过；尚未修改本机配置', 'ok');
  } catch (err) {
    toast(String(err), 'err');
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
    toast(String(err), 'err');
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
    toast(String(err), 'err');
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
    toast(String(err), 'err');
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
    toast(result.detail ? result.status + '：' + result.detail : '自动化任务已完成：' + result.status, result.ok ? 'ok' : 'err');
    const view = document.getElementById('view-settings');
    if (view) void renderSettingsView(view);
  } catch (err) {
    toast(String(err), 'err');
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
  if (!window.confirm('迁移前必须确认同步状态 ready、工作树干净且远端可达。确定由当前 Mac 执行？')) return;
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
    toast(String(err), 'err');
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
  void api('/api/settings/profile/remove', {
    method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, confirmed: true }),
  }).then(() => { toast('本机 profile 已移除', 'ok'); void renderSettingsView(document.getElementById('view-settings') as HTMLElement); })
    .catch((err: unknown) => toast(String(err), 'err'));
}

/** data-action="settings-doctor-online"：带确认的在线检查（原派发器内联分支）。 */
export function runSettingsDoctorOnline(): void {
  if (!window.confirm('在线检查会访问 provider，并可能轮换飞书 token。确定继续？')) return;
  void runSettingsDoctor(true).catch((err: unknown) => toast(String(err), 'err'));
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
    .catch((err: unknown) => toast(String(err), 'err'));
}
