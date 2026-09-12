import { registerModalCloseHook } from '../shell';
import { setAskDeps, type AskDeps } from './actions';
import { invalidateSourceReads } from './source-reader';

/** 问答 feature 边界。 */

/** 注入跨域依赖并注册弹层关闭钩子；由组合根在 renderShell 之后调用一次。 */
export function mountAsk(deps: AskDeps): void {
  setAskDeps(deps);
  registerModalCloseHook(invalidateSourceReads);
}

export {
  askNewThread,
  askOpenThread,
  beginAskRename,
  deleteAskThread,
  getAskDraft,
  reloadAskStore,
  renderAsk,
  resetAskForWorkspace,
  setAskDraft,
} from './actions';
export { openSource } from './source-reader';
export { askSourceButton, renderAskAnswer } from './render';
export type { AskDeps } from './actions';
export type {
  AskAnswer,
  AskConflict,
  AskConflictSide,
  AskFact,
  AskHistoryTurn,
  AskMsg,
  AskResponse,
  AskThread,
  SourceReadPayload,
} from './types';
