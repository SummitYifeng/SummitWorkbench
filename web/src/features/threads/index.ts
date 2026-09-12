import { setThreadsDeps, type ThreadsDeps } from './deps';

/** 线程 feature 边界（日志与产物都归档进项目/知识线程档案）。 */

/** 注入组合根依赖；由组合根在 renderShell 之后调用一次。 */
export function mountThreads(deps: ThreadsDeps): void {
  setThreadsDeps(deps);
}

export { openLogModal } from './log-modal';
export { openArtifactModal, artifactStateConfirmText } from './artifact-modal';
export type { ThreadsDeps } from './deps';
export type { ArtifactDraft, LogDraft } from './types';
