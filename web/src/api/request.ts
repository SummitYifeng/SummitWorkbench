import { workspaceStore } from '../core/workspace-store';
import { createApiClient } from './client';
import type { ApiRequestOptions } from './client';
import { ApiError } from './client';
import { publishOperationFeedback } from '../features/shell/operation-feedback';

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

const RECEIPT_MUTATIONS = new Set([
  '/api/capture', '/api/journal/log', '/api/journal/thought', '/api/inbox/promote',
]);
const FEEDBACK_MUTATIONS = new Set([
  ...RECEIPT_MUTATIONS,
  '/api/tasks/complete', '/api/tasks/update', '/api/meetings/update',
  '/api/review/decide', '/api/review/batch', '/api/review/edit', '/api/review/apply',
]);

function mutationFingerprint(url: string, body: string): string {
  // The fingerprint is only a localStorage key; the request body itself is never persisted.
  let hash = 2166136261;
  for (const char of url + '\n' + body) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return (hash >>> 0).toString(16);
}

function requestIdFor(url: string, body: string): string {
  const key = 'swb:operation-request:' + mutationFingerprint(url, body);
  try {
    const previous = localStorage.getItem(key);
    if (previous) return previous;
    const id = crypto.randomUUID();
    localStorage.setItem(key, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

function clearRequestId(url: string, body: string): void {
  try { localStorage.removeItem('swb:operation-request:' + mutationFingerprint(url, body)); }
  catch { /* Private browsing/storage restrictions do not block a save. */ }
}

function usesOperationReceipt(url: string, body: string, method: string): boolean {
  if (method !== 'POST' || !RECEIPT_MUTATIONS.has(url)) return false;
  if (url !== '/api/inbox/promote') return true;
  try {
    const payload: unknown = JSON.parse(body);
    const target = payload && typeof payload === 'object' ? (payload as { target?: unknown }).target : null;
    return target === 'project' || target === 'thought';
  } catch { return false; }
}

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
export async function api<T>(url: string, init?: RequestInit, options?: ApiRequestOptions): Promise<T> {
  const generation = workspaceStore.generation;
  const requestSequence = ++apiRequestSequence;
  const headers = new Headers(init?.headers);
  headers.set('X-WB-Workspace-Generation', String(generation));
  headers.set('X-WB-Request-Sequence', String(requestSequence));
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = typeof init?.body === 'string' ? init.body : '';
  const baseUrl = url.split('?')[0];
  const usesReceipt = usesOperationReceipt(baseUrl, body, method);
  const recordsFeedback = method === 'POST' && FEEDBACK_MUTATIONS.has(baseUrl);
  const requestId = usesReceipt ? requestIdFor(baseUrl, body) : null;
  if (requestId) headers.set('X-WB-Request-Id', requestId);
  let result: T;
  try {
    result = await apiClient.request<T>(url, { ...init, headers }, options);
    if (recordsFeedback && result && typeof result === 'object') {
      const response = result as Record<string, unknown>;
      publishOperationFeedback(
        requestId ?? (typeof response.operation_id === 'string' ? response.operation_id : crypto.randomUUID()),
        response,
      );
    }
    if (requestId && !(result && typeof result === 'object' && 'status' in result && result.status === 'unknown')) {
      clearRequestId(baseUrl, body);
    }
  } catch (error) {
    if (!requestId || (error instanceof ApiError && error.status !== 408 && error.status < 500)) throw error;
    try {
      const receipt = await apiClient.request<{
        status?: string;
        response?: T;
      }>('/api/operations/' + encodeURIComponent(requestId), {
        headers: new Headers({
          'X-WB-Workspace-Generation': String(generation),
          'X-WB-Request-Sequence': String(++apiRequestSequence),
        }),
      }, { timeoutMs: 10_000 });
      if (receipt.status === 'completed' && receipt.response) {
        clearRequestId(baseUrl, body);
        result = receipt.response;
      } else {
        result = {
          ok: false,
          status: 'unknown',
          operation_id: requestId,
          message: '正在核实本次操作，暂时无法确认结果。请稍后查询操作回执，不要重新提交。',
        } as T;
      }
    } catch (receiptError) {
      const notFound = receiptError instanceof ApiError && receiptError.status === 404;
      result = {
        ok: false,
        status: notFound ? 'not_found' : 'unknown',
        operation_id: requestId,
        message: notFound
          ? '本机未找到这次操作回执，操作尚未登记；可以安全重试。'
          : '本次操作结果暂时无法确认。请求编号：' + requestId + '；请恢复连接后查询回执，不要重新提交。',
      } as T;
    }
    if (recordsFeedback && result && typeof result === 'object') {
      publishOperationFeedback(requestId, result as Record<string, unknown>);
    }
  }
  if (generation !== workspaceStore.generation) throw new StaleWorkspaceResponseError();
  return result;
}

/** 切换 profile / 换代时丢弃在途请求。 */
export function disposeApiClient(): void {
  apiClient.dispose();
}
