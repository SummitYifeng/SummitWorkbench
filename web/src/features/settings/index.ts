/** 设置 feature 边界（Step 8c：渲染在 render.ts，写动作在 actions.ts）。 */
export type { ProfileSummary, SettingsActions } from './render';
export { renderSettings } from './render';
export { mountSettings } from './mount';
export {
  applyGitRemoteNormalization,
  authorizeFeishu,
  claimAutomationPrimary,
  copyAutomationSummary,
  downgradeAutomationPrimary,
  migrateWorkspace,
  previewGitRemoteNormalization,
  removeProfile,
  renderSettingsView,
  reopenOnboarding,
  reportFeishuCallbackResult,
  rollbackGitRemoteNormalization,
  runAcceptancePreflight,
  runAutomationJob,
  runSettingsDoctor,
  runSettingsDoctorOnline,
  switchProfile,
} from './actions';
export type { SettingsDeps } from './deps';
export type { AcceptancePreflightPayload, RemoteNormalizationPreviewPayload } from './types';
export type { SyncPrimaryStatus } from './render';
