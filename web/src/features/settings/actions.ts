import { sendNativeMessage } from '../../lifecycle/native-bridge';
import { getSettingsDeps, api, mutation, toast } from './deps';
import { renderSettings as renderSettingsRenderer } from './render';

/** Settings actions for model, Feishu authorization, workspace selection, and diagnostics. */

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
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
  const committed = await api<{ restart_required: boolean }>('/api/settings/profile/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: prepared.plan_id }),
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
