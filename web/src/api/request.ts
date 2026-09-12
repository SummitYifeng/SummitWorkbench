import { workspaceStore } from '../core/workspace-store';
import { createApiClient } from './client';

/** 工作区在请求往返期间被切换（换代）时抛出，调用方据此丢弃过期响应。 */
export class StaleWorkspaceResponseError extends Error {
  constructor() {
    super('工作区已切换，忽略旧请求结果');
    this.name = 'StaleWorkspaceResponseError';
  }
}

export function isStaleWorkspaceResponse(error: unknown): boolean {
  return error instanceof StaleWorkspaceResponseError;
}

let apiRequestSequence = 0;

/**
 * 连接从"失败"恢复为"成功"时的观察者。
 *
 * 原先 `apiClient` 的 `onSuccess` 直接调用 `checkVersion('connection-restored')`，这会
 * 让请求层反向依赖版本模块。改为注册表：版本/生命周期模块在 mount 时注册回调。
 */
type ConnectionRestoredListener = (url: string) => void;
const connectionRestoredListeners: ConnectionRestoredListener[] = [];
let connectionHadFailure = false;

export function onConnectionRestored(listener: ConnectionRestoredListener): void {
  connectionRestoredListeners.push(listener);
}

const apiClient = createApiClient({
  onFailure: () => { connectionHadFailure = true; },
  onSuccess: (url) => {
    if (connectionHadFailure && url !== '/api/version') {
      connectionHadFailure = false;
      for (const listener of connectionRestoredListeners) listener(url);
    }
  },
});

/** 统一的 JSON 请求入口：带工作区换代与请求序号头，并在换代后丢弃结果。 */
export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const generation = workspaceStore.generation;
  const requestSequence = ++apiRequestSequence;
  const headers = new Headers(init?.headers);
  headers.set('X-WB-Workspace-Generation', String(generation));
  headers.set('X-WB-Request-Sequence', String(requestSequence));
  const result = await apiClient.request<T>(url, { ...init, headers });
  if (generation !== workspaceStore.generation) throw new StaleWorkspaceResponseError();
  return result;
}

/** 切换 profile / 换代时丢弃在途请求。 */
export function disposeApiClient(): void {
  apiClient.dispose();
}
