import type { ReviewFilter } from './types';

/**
 * 审批页的界面状态（Step 8b）。
 *
 * 用一个可变对象而不是 `export let`：ESM 的 import 绑定只读，而 `actions.ts` 与
 * `assemble.ts` 都要改这些字段；对象属性赋值不受该限制，也省掉十几个 accessor。
 * workspace 换代时的清空统一走 `resetReviewForWorkspace()`。
 */
export const reviewUi = {
  filter: 'all' as ReviewFilter,
  selected: new Set<string>(),
  planReady: false,
  /** apply（写回）在途保护：双击/重复点击不能发出第二次 /api/review/apply */
  applyBusy: false,
};

/** workspace 换代时清空审批页界面状态（原 doCheckVersion 内联的 5 行，逐字搬迁）。 */
export function resetReviewForWorkspace(): void {
reviewUi.filter = 'all';
reviewUi.selected.clear();
// 旧工作区的预演/在途写回标记不得带入新工作区。
reviewUi.planReady = false;
reviewUi.applyBusy = false;
}
