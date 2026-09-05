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
