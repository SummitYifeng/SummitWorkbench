import type { ProjectState } from '../projects';

/**
 * 线程弹层的组合根依赖（Step 7）。
 *
 * 两个弹层都需要「已建档项目」下拉数据、实体草稿的 workspace 作用域与写入器；按 §4.2
 * 一律走函数入参，避免 threads → legacy-main 的反向依赖。
 */

export interface ThreadsDeps {
  /** 已建档项目（下拉/多选数据源）。 */
  projects: () => ProjectState[];
  /** 实体草稿的 workspace 作用域。 */
  workspaceId: () => string | undefined;
  /** 写实体草稿（保留组合根的配额告警语义）。 */
  persistEntityDraft: <T>(entity: string, value: T) => void;
}

let threadsDeps: ThreadsDeps | null = null;

export function setThreadsDeps(deps: ThreadsDeps): void {
  threadsDeps = deps;
}

/** 组合根尚未注入时返回 null；调用点用可选链，语义与"注入前不动作"一致。 */
export function getThreadsDeps(): ThreadsDeps | null {
  return threadsDeps;
}
