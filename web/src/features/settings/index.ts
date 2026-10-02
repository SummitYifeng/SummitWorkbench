/** 设置 feature 边界（Step 8c：渲染在 render.ts，写动作在 actions.ts）。 */
export type { ProfileSummary, SettingsActions } from './render';
export { renderSettings } from './render';
export { mountSettings } from './mount';
export {
  authorizeFeishu,
  copyAutomationSummary,
  removeProfile,
  renderSettingsView,
  reopenOnboarding,
  reportFeishuCallbackResult,
  runSettingsDoctor,
  runSettingsDoctorOnline,
  switchProfile,
} from './actions';
export type { SettingsDeps } from './deps';
