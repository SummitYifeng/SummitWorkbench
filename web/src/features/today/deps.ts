/**
 * 今日域的组合根依赖（Step 8d）。
 *
 * `api`/`mutation`/`toast`/`refreshState`/`renderToday` 以模块级绑定存在，让搬运来的函数体
 * 逐字不变；`setTodayDeps()` 在 `renderShell()` 之后重新绑定。
 */
export interface TodayDeps {
  api: <T>(url: string, init?: RequestInit) => Promise<T>;
  mutation: <T>(request: () => Promise<T>) => Promise<T>;
  toast: (msg: string, kind?: 'ok' | 'err' | 'info') => void;
  refreshState: () => Promise<boolean>;
  renderToday: (view: HTMLElement) => void;
}

let todayDeps: TodayDeps | null = null;

function notInjected(): never {
  throw new Error('TodayDeps 未注入：mountTodayActions() 必须在 renderShell() 之后调用');
}

export let api: TodayDeps['api'] = notInjected;
export let mutation: TodayDeps['mutation'] = notInjected;
export let toast: TodayDeps['toast'] = notInjected;
export let refreshState: TodayDeps['refreshState'] = notInjected;
export let renderToday: TodayDeps['renderToday'] = notInjected;

export function setTodayDeps(deps: TodayDeps): void {
  todayDeps = deps;
  api = deps.api;
  mutation = deps.mutation;
  toast = deps.toast;
  refreshState = deps.refreshState;
  renderToday = deps.renderToday;
}

export function getTodayDeps(): TodayDeps | null {
  return todayDeps;
}
