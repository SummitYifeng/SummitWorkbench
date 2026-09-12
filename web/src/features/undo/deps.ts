/**
 * 撤销域的组合根依赖（Step 6）。
 *
 * 还原成功后需要组合根做一次全量刷新（state + review 编排住在组合根，§4.2），
 * 这里只暴露一个最小的注入点，避免 undo → legacy-main 的反向依赖。
 */

export interface UndoDeps {
  /** 还原成功后的全量刷新。 */
  refreshAll: () => Promise<unknown>;
}

let undoDeps: UndoDeps | null = null;

export function setUndoDeps(deps: UndoDeps): void {
  undoDeps = deps;
}

export function getUndoDeps(): UndoDeps | null {
  return undoDeps;
}
