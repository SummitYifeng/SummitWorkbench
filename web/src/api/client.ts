/** Typed fetch boundary shared by every feature. */

export interface ApiErrorPayload {
  message?: string;
  code?: string;
  operation_id?: string;
  details?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly operationId: string | null;

  constructor(message: string, status: number, code: string | null = null, operationId: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.operationId = operationId;
  }
}

/** 从校验错误 envelope 提取第一条可执行原因（后端 details: [{loc, msg}]）。 */
function firstValidationDetail(details: unknown): string {
  if (!Array.isArray(details) || details.length === 0) return '';
  const first = details[0];
  if (!first || typeof first !== 'object') return '';
  const msg = (first as { msg?: unknown }).msg;
  return typeof msg === 'string' && msg.trim() ? msg.trim() : '';
}

export function normalizeApiError(status: number, payload: unknown): ApiError {
  const value = payload && typeof payload === 'object' ? payload as ApiErrorPayload : {};
  const code = typeof value.code === 'string' ? value.code : null;
  const operationId = typeof value.operation_id === 'string' ? value.operation_id : null;
  const message = typeof value.message === 'string' ? value.message : '请求失败：HTTP ' + status;
  // envelope 的 message 往往是笼统的「请求参数不符合接口约束」；补上首条 detail，
  // 用户才能知道是哪一项、为什么被拒（例如正文超过长度上限）。
  const detail = firstValidationDetail(value.details);
  const summary = detail ? message + '：' + detail : message;
  return new ApiError(summary + (code ? ' [' + code + ']' : ''), status, code, operationId);
}

export interface ApiClient {
  request<T>(url: string, init?: RequestInit): Promise<T>;
  dispose(): void;
}

export function createApiClient(options: {
  onFailure?: () => void;
  onSuccess?: (url: string) => void;
} = {}): ApiClient {
  const controllers = new Set<AbortController>();
  let disposed = false;
  return {
    async request<T>(url: string, init?: RequestInit): Promise<T> {
      if (disposed) throw new ApiError('工作台请求已结束', 499, 'client_disposed');
      const controller = new AbortController();
      controllers.add(controller);
      try {
        const response = await fetch(url, { ...init, signal: controller.signal });
        if (!response.ok) {
          options.onFailure?.();
          let payload: unknown = null;
          try { payload = await response.json(); } catch { /* 非 JSON 错误 */ }
          throw normalizeApiError(response.status, payload);
        }
        options.onSuccess?.(url);
        return await response.json() as T;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        options.onFailure?.();
        throw error;
      } finally {
        controllers.delete(controller);
      }
    },
    dispose(): void {
      disposed = true;
      for (const controller of controllers) controller.abort();
      controllers.clear();
    },
  };
}
