import type { SettingsActions } from './render';

/**
 * 设置域的组合根依赖（Step 8c）。
 *
 * `api`/`mutation`/`toast` 沿用既有 `SettingsActions` 形态；其余是切换 profile / 迁移工作区
 * 必须由组合根提供的副作用入口（丢弃草稿快照、释放 api client 与 workspace store）。
 */
export interface SettingsDeps extends SettingsActions {
  /** 当前工作区 id（草稿快照作用域）。 */
  workspaceId: () => string | undefined;
  /** 丢弃草稿快照（切 profile / 迁移前）。 */
  clearDraftSnapshot: (workspaceId: string | undefined) => void;
  /** 释放请求边界（原 apiClient.dispose()）。 */
  disposeApiClient: () => void;
  /** 释放 workspace store（原 workspaceStore.dispose()）。 */
  disposeWorkspaceStore: () => void;
}

let settingsDeps: SettingsDeps | null = null;

function notInjected(): never {
  throw new Error('SettingsDeps 未注入：mountSettings() 必须在 renderShell() 之后调用');
}

/** 已注入的依赖；`api`/`mutation`/`toast` 直接以模块名绑定，让搬运来的函数体保持逐字不变。 */
export let api: SettingsActions['api'] = notInjected;
export let mutation: SettingsActions['mutation'] = notInjected;
export let toast: SettingsActions['toast'] = notInjected;

export function setSettingsDeps(deps: SettingsDeps): void {
  settingsDeps = deps;
  api = deps.api;
  mutation = deps.mutation;
  toast = deps.toast;
}

export function getSettingsDeps(): SettingsDeps | null {
  return settingsDeps;
}
