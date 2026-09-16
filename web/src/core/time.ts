/** Stable user-facing time formatting; never depends on the machine timezone or locale. */

const BUSINESS_TIME_ZONE = 'Asia/Shanghai';

function parts(value: Date): Record<string, string> {
  const output: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat('en-CA-u-nu-latn', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(value)) {
    if (part.type !== 'literal') output[part.type] = part.value;
  }
  return output;
}

/** Offset/Z timestamps become Beijing time; date-only values remain dates. */
export function formatBusinessTime(value: string | null | undefined): string {
  const raw = value?.trim();
  if (!raw) return '—';
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return '无效时间';
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) return '时区未知';
  const p = parts(date);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}

/** Unix seconds to a Beijing datetime-local value (datetime-local has no offset). */
export function businessDatetimeLocal(value: string | null | undefined): string {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const p = parts(date);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
