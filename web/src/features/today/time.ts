/** 今日页行内编辑的时间换算（纯函数；从 legacy-main 抽出，Step 1）。 */

/** unix 秒（字符串）→ 本地 datetime-local 输入值（YYYY-MM-DDTHH:MM）；无效返回空串。 */
export function tsToDatetimeLocal(ts: string | null | undefined): string {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const d = new Date(seconds * 1000);
  const pad = (x: number): string => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

/** unix 秒 + 分钟偏移 → datetime-local 输入值（结束时间缺省 = 开始 + 60 分钟）。 */
export function plusMinutesInput(ts: string | null | undefined, minutes: number): string {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const d = new Date((seconds + minutes * 60) * 1000);
  const pad = (x: number): string => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}
