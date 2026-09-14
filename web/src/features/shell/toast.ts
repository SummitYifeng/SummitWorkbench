import { errorText } from '../../api/client';
import { toastRoot } from './dom';

/**
 * 右下角瞬时提示（原 legacy-main 的 `toast`，逐字搬迁，仅把根改为惰性访问）。
 *
 * 2026-09-14：`msg` 放宽为 `unknown` 并统一过 `errorText` 归一化——
 * 调用点不再需要 `String(err)`（那会把 `TypeError: Failed to fetch` 原样贴到界面上）。
 */
export function toast(msg: unknown, kind: 'ok' | 'err' | 'info' = 'info'): void {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = errorText(msg);
  toastRoot().appendChild(el);
  window.setTimeout(() => el.remove(), 4600);
}
