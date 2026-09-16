/** 今日页行内编辑的时间换算（纯函数；从 legacy-main 抽出，Step 1）。 */

import { businessDatetimeLocal } from '../../core/time';

/** unix 秒（字符串）→ 本地 datetime-local 输入值（YYYY-MM-DDTHH:MM）；无效返回空串。 */
export function tsToDatetimeLocal(ts: string | null | undefined): string {
  return businessDatetimeLocal(ts);
}

/** unix 秒 + 分钟偏移 → datetime-local 输入值（结束时间缺省 = 开始 + 60 分钟）。 */
export function plusMinutesInput(ts: string | null | undefined, minutes: number): string {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  return businessDatetimeLocal(String(seconds + minutes * 60));
}
