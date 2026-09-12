export const CLIENT_BUILD = __WB_BUILD__;

export interface VersionPayload {
  product_id: 'com.summitworkbench.panel';
  api_protocol: number;
  frontend_build: string;
  server_version: string;
  server_instance: string;
  started_at: string;
  mode: 'production' | 'development-managed' | 'development-external';
  workspace_id?: string;
}

export type VersionStatus = 'checking' | 'synced' | 'update-pending' | 'reconnecting' | 'failed';

export function validateVersionPayload(value: unknown): VersionPayload {
  if (!value || typeof value !== 'object') throw new Error('版本响应不是 JSON 对象');
  const payload = value as Record<string, unknown>;
  const modes = ['production', 'development-managed', 'development-external'];
  if (
    payload.product_id !== 'com.summitworkbench.panel' ||
    typeof payload.api_protocol !== 'number' ||
    typeof payload.frontend_build !== 'string' ||
    typeof payload.server_version !== 'string' ||
    typeof payload.server_instance !== 'string' ||
    typeof payload.started_at !== 'string' ||
    !modes.includes(String(payload.mode))
  ) {
    throw new Error('版本响应字段无效');
  }
  if (payload.api_protocol < 2) throw new Error('版本响应协议不兼容');
  if (payload.workspace_id !== undefined && typeof payload.workspace_id !== 'string') {
    throw new Error('版本响应 workspace 作用域无效');
  }
  return payload as unknown as VersionPayload;
}

export function canonicalPanelUrl(currentHref: string, targetBuild: string): string {
  const url = new URL(currentHref);
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  url.searchParams.set('build', targetBuild);
  return url.toString();
}

export function shouldPreventReload(
  storage: Pick<Storage, 'getItem'>,
  targetBuild: string,
  nowMs: number,
): boolean {
  if (storage.getItem('wb.update.last-target') !== targetBuild) return false;
  const attemptedAt = Date.parse(storage.getItem('wb.update.last-attempt-at') ?? '');
  return Number.isFinite(attemptedAt) && nowMs - attemptedAt < 30_000;
}

/**
 * 版本状态的展示（原 legacy-main，Step 9）。
 *
 * 组合根决定"何时改状态"（重查策略、跨域状态重置、reload 决策），本模块只管"状态怎么显示"：
 * 只依赖 `CLIENT_BUILD` 与传入的远端版本，因此放在 L0 不会反向依赖任何 feature。这也正是
 * `doCheckVersion` 留在组合根的原因 —— 它要重置四个域的状态并调用 `refreshAll()`。
 */
export function versionStatusLabel(status: VersionStatus, remote: VersionPayload | null): string {
  if (status === 'checking') return '正在检查版本';
  if (status === 'synced') {
    return remote
      ? '界面 ' + CLIENT_BUILD + ' · 服务 ' + remote.server_version + ' · 已同步'
      : '已同步';
  }
  if (status === 'update-pending') return '新版本已就绪';
  if (status === 'reconnecting') return '正在重新连接';
  return '更新未完成';
}

export function setVersionStatus(status: VersionStatus, remote: VersionPayload | null): void {
  const el = document.getElementById('version-status');
  if (el) {
    el.className = 'version-status ' + status;
    el.textContent = versionStatusLabel(status, remote);
  }
  const banner = document.getElementById('version-error-banner');
  if (banner) banner.hidden = status !== 'failed';
}

/** 版本更新导航：记录本次尝试后跳到目标构建的 URL（原 legacy-main，逐字搬迁）。 */
export function reloadToBuild(targetBuild: string, remote: VersionPayload | null): void {
  try {
    window.sessionStorage.setItem('wb.update.last-target', targetBuild);
    window.sessionStorage.setItem('wb.update.last-attempt-at', new Date().toISOString());
  } catch {
    // sessionStorage 不可用时仍尝试导航；页面自身会通过 URL 继续握手。
  }
  setVersionStatus('update-pending', remote);
  window.location.assign(canonicalPanelUrl(window.location.href, targetBuild));
}
