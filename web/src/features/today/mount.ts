import { setTodayDeps, type TodayDeps } from './deps';

/** 今日 feature 的挂载点：注入组合根依赖（必须在 renderShell() 之后调用）。 */
export function mountTodayActions(deps: TodayDeps): void {
  setTodayDeps(deps);
}
