import type { ImportReceipt } from './types';

/**
 * 「今日」页的界面状态（原 legacy-main 的模块级 `let`，Step 8d）。
 *
 * 与 `reviewUi` 同理：`renderToday` 要读、capture/import 动作要写，而 ESM 的 import 绑定
 * 只读，所以用一个可变对象承载，而不是导出一堆访问器。
 */
export const todayUi = {
  importing: false,
  importOpen: false,
  capturing: false,
  importResults: [] as ImportReceipt[],
};

/** 切换 workspace 时重置（原 applyVersionPayload 内联的两行，逐字保留）。 */
export function resetTodayForWorkspace(): void {
  todayUi.importResults = [];
  todayUi.importOpen = false;
}
