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

export interface ApiRequestOptions {
  timeoutMs?: number;
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
  // 错误码是内部标识（`invalid_source_path`、`validation_error`…），保留在 `ApiError.code`
  // 供诊断使用，但**不拼进给使用者看的文案**（2026-09-14：界面上一律中文，不混英文码）。
  return new ApiError(summary, status, code, operationId);
}

/**
 * 把任意异常归一化成给使用者看的一句中文。
 *
 * 调用点过去的写法是 `toast(String(err), 'err')`，那会直接把
 * `TypeError: Failed to fetch` / `AbortError` 这类英文原文贴到界面上；
 * 统一走本函数：`ApiError` 用它已经归一化过的 message，浏览器网络错误给中文兜底。
 */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) {
    const name = error.name || '';
    const raw = error.message || '';
    if (/AbortError/i.test(name)) return '请求已取消';
    if (/Failed to fetch|NetworkError|Load failed|fetch failed/i.test(raw)) {
      return '连不上本地服务，请确认工作台还在运行';
    }
    if (raw.trim()) return raw;
    return '未知错误';
  }
  const text = String(error ?? '').trim();
  return text || '未知错误';
}

export interface ApiClient {
  request<T>(url: string, init?: RequestInit, options?: ApiRequestOptions): Promise<T>;
  dispose(): void;
}

export function createApiClient(options: {
  onFailure?: () => void;
  onSuccess?: (url: string) => void;
} = {}): ApiClient {
  const controllers = new Set<AbortController>();
  let disposed = false;
  return {
    async request<T>(url: string, init?: RequestInit, requestOptions: ApiRequestOptions = {}): Promise<T> {
      if (disposed) throw new ApiError('工作台请求已结束', 499, 'client_disposed');
      const controller = new AbortController();
      controllers.add(controller);
      const callerSignal = init?.signal;
      const timeoutMs = requestOptions.timeoutMs ?? (
        (init?.method ?? 'GET').toUpperCase() === 'GET' ? 15_000 : 30_000
      );
      let timedOut = false;
      let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
      const abortFromCaller = (): void => controller.abort();
      if (callerSignal) {
        if (callerSignal.aborted) controller.abort();
        else callerSignal.addEventListener('abort', abortFromCaller, { once: true });
      }
      if (timeoutMs > 0) {
        timeoutHandle = setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs);
      }
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
        if (timedOut) throw new ApiError('请求超时，结果尚未确认，请查看页面状态后再继续', 408, 'request_timeout');
        options.onFailure?.();
        throw error;
      } finally {
        if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
        callerSignal?.removeEventListener('abort', abortFromCaller);
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
