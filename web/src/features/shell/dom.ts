/**
 * DOM 根的惰性访问器。
 *
 * 这些根过去在 legacy-main 顶层求值（`const app = document.getElementById('app')`），
 * 有两个后果：Node 下 import 功能模块的渲染测试会因 `document is not defined` 直接抛错，
 * 且任何早于 `renderShell()` 的求值都会静默拿到 `null`。惰性函数同时消除这两点。
 *
 * 下面四个 id 是跨模块 DOM 契约：由 `renderShell()` 产出，各 feature 只经本模块访问，
 * 不得再自行写字符串。
 */

export const APP_ID = 'app';
export const TOASTS_ID = 'toasts';
export const MODAL_BACKDROP_ID = 'modal-backdrop';
export const MODAL_ID = 'modal';

export function appRoot(): HTMLElement {
  return document.getElementById(APP_ID) as HTMLElement;
}

export function toastRoot(): HTMLElement {
  return document.getElementById(TOASTS_ID) as HTMLElement;
}

/** 某个 tab 的内容容器（`#view-today` 等），由 `renderShell()` 产出。 */
export function viewElement(tab: string): HTMLElement | null {
  return document.getElementById('view-' + tab);
}

export function modalBackdrop(): HTMLElement {
  return document.getElementById(MODAL_BACKDROP_ID) as HTMLElement;
}

export function modalRoot(): HTMLElement {
  return document.getElementById(MODAL_ID) as HTMLElement;
}
