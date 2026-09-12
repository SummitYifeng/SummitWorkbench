import { setProjectDeps, type ProjectDeps } from './deps';

/** 项目 feature 的挂载点：注入组合根依赖。 */
export function mountProjects(deps: ProjectDeps): void {
  setProjectDeps(deps);
}

export type { ProjectDeps } from './deps';
