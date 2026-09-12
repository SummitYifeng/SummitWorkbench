import { setUndoDeps, type UndoDeps } from './deps';

/** 撤销 feature 边界。 */

/** 注入组合根依赖；由组合根在 renderShell 之后调用一次。 */
export function mountUndo(deps: UndoDeps): void {
  setUndoDeps(deps);
}

export { openUndoModal, UNDO_FLYNOTE, undoEmptyHtml, undoErrorHtml, undoListHtml } from './modal';
export type { UndoDeps } from './deps';
export type { UndoDiffPayload, UndoHistoryPayload, WbCommitItem } from './types';
