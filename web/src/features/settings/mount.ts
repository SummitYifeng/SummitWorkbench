import { setSettingsDeps, type SettingsDeps } from './deps';

/** 设置 feature 的挂载点：注入组合根依赖。 */
export function mountSettings(deps: SettingsDeps): void {
  setSettingsDeps(deps);
}
