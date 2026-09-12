import { modalBackdrop, modalRoot } from './dom';

/**
 * 弹层关闭钩子。
 *
 * `closeModal()` 过去直接写 `sourceReadSequence += 1`（ask 域"在途来源读取"的作废计数器），
 * 这让 shell 反向依赖 ask。改成注册表后，各域在 `mount*` 时注册自己的失效逻辑，
 * shell 只在关闭时逐个调用，依赖方向保持 shell ← 各域。
 */
type ModalCloseHook = () => void;
const modalCloseHooks: ModalCloseHook[] = [];

export function registerModalCloseHook(hook: ModalCloseHook): void {
  modalCloseHooks.push(hook);
}

/** 嵌套弹层只记录最外层打开前的焦点；关闭时归还。 */
let modalReturnFocus: HTMLElement | null = null;

/**
 * 异步弹层在内容到位后把返回焦点改绑到稳定的触发元素
 * （同步冲突横幅在异步加载期间可能重渲染，不能依赖 activateModal 捕获的 activeElement）。
 */
export function setModalReturnFocus(returnFocus: HTMLElement | null): void {
  if (returnFocus) modalReturnFocus = returnFocus;
}

export function activateModal(html: string, includeCloseButton = false): HTMLElement {
  const backdrop = modalBackdrop();
  const modal = modalRoot();
  if (backdrop.hidden) {
    modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  modal.innerHTML = html;
  backdrop.hidden = false;
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('tabindex', '-1');
  const heading = modal.querySelector<HTMLElement>('h2, h3');
  if (heading) {
    if (!heading.id) heading.id = 'modal-title';
    modal.setAttribute('aria-labelledby', heading.id);
  } else {
    modal.removeAttribute('aria-labelledby');
  }
  if (includeCloseButton) {
    const close = document.createElement('button');
    close.className = 'ghost close-modal';
    close.textContent = '关闭';
    close.style.marginTop = '12px';
    modal.appendChild(close);
    close.addEventListener('click', requestModalClose);
  }
  const first = modal.querySelector<HTMLElement>('button, input, select, textarea, [tabindex="0"]');
  (first ?? modal).focus();
  return modal;
}

export function openModal(html: string): HTMLElement {
  const modal = activateModal(html, true);
  modal.dataset.draftDirty = '0';
  delete modal.dataset.draftEntity;
  modal.oninput = () => {
    if (modal.dataset.draftEntity) modal.dataset.draftDirty = '1';
  };
  modal.onchange = () => {
    if (modal.dataset.draftEntity) modal.dataset.draftDirty = '1';
  };
  return modal;
}

export function closeModal(): void {
  for (const hook of modalCloseHooks) hook();
  modalBackdrop().hidden = true;
  modalReturnFocus?.focus();
  modalReturnFocus = null;
}

export function requestModalClose(): void {
  const modal = modalRoot();
  const hasDraft = modal?.dataset.draftDirty === '1';
  if (hasDraft && !window.confirm('当前弹层里有未保存内容。继续关闭并放弃草稿吗？')) return;
  closeModal();
}
