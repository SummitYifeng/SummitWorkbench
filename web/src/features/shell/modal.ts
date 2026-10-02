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
  if (typeof document.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') {
    document.dispatchEvent(new CustomEvent('swb:modal-opened', { detail: modal }));
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
  const draftForm = modal.querySelector<HTMLFormElement>('form[data-draft-type][data-draft-id]');
  if (draftForm) modal.dataset.draftEntity = draftForm.dataset.draftType + ':' + draftForm.dataset.draftId;
  else delete modal.dataset.draftEntity;
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
  if (hasDraft) {
    if (modal.querySelector('.modal-draft-close')) return;
    const choice = document.createElement('section');
    choice.className = 'modal-draft-close';
    choice.setAttribute('role', 'alert');
    choice.innerHTML = '<p>这份内容还在保存。请选择如何处理：</p>' +
      '<div class="row"><button type="button" data-draft-close="keep">保留草稿并关闭</button>' +
      '<button type="button" class="ghost" data-draft-close="continue">继续编辑</button>' +
      '<button type="button" class="ghost" data-draft-close="discard">放弃草稿</button></div>' +
      '<p class="hint" data-draft-close-status aria-live="polite"></p>';
    modal.appendChild(choice);
    choice.querySelector<HTMLButtonElement>('[data-draft-close="continue"]')?.addEventListener('click', () => choice.remove());
    for (const button of choice.querySelectorAll<HTMLButtonElement>('[data-draft-close="keep"], [data-draft-close="discard"]')) {
      button.addEventListener('click', () => {
        const status = choice.querySelector<HTMLElement>('[data-draft-close-status]');
        if (status) status.textContent = button.dataset.draftClose === 'keep' ? '正在确认草稿已保存在本机…' : '正在删除本机草稿…';
        for (const option of choice.querySelectorAll<HTMLButtonElement>('button')) option.disabled = true;
        const finish = (close: boolean, message?: string): void => {
          if (close) closeModal();
          else {
            if (status) status.textContent = message ?? '操作暂未完成，请继续编辑或重试。';
            for (const option of choice.querySelectorAll<HTMLButtonElement>('button')) option.disabled = false;
          }
        };
        if (typeof document.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') {
          document.dispatchEvent(new CustomEvent('swb:modal-close-choice', {
            detail: { choice: button.dataset.draftClose, modal, finish },
          }));
        } else {
          finish(false, '无法确认草稿操作，请继续编辑。');
        }
      });
    }
    return;
  }
  closeModal();
}
