import type { ShellTab } from '../shell';

/**
 * 项目域的组合根依赖（Step 8）。
 *
 * 详情导航要切 tab 并触发组合根的 ``render()``，激活/归档与改名后要刷新；这些编排住在
 * 组合根（§4.1/§4.2），因此按入参注入，避免 projects → legacy-main 的反向依赖。
 */

export interface ProjectDeps {
  /** 当前 tab（打开详情前记录来路）。 */
  currentTab: () => ShellTab;
  /** 切换 tab。 */
  setTab: (tab: ShellTab) => void;
  /** 触发组合根重新渲染。 */
  render: () => void;
  /** 全量刷新（激活/归档后）。 */
  refreshAll: () => Promise<unknown>;
  /** 只读状态刷新（改名后）。 */
  refreshState: () => Promise<boolean>;
}

let projectDeps: ProjectDeps | null = null;

export function setProjectDeps(deps: ProjectDeps): void {
  projectDeps = deps;
}

/** 组合根尚未注入时返回 null；调用点用可选链，语义与"注入前不动作"一致。 */
export function getProjectDeps(): ProjectDeps | null {
  return projectDeps;
}
