import { toastRoot } from './dom';

/** 右下角瞬时提示（原 legacy-main 的 `toast`，逐字搬迁，仅把根改为惰性访问）。 */
export function toast(msg: string, kind: 'ok' | 'err' | 'info' = 'info'): void {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  toastRoot().appendChild(el);
  window.setTimeout(() => el.remove(), 4600);
}
