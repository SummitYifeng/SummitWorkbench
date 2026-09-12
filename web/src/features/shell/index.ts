/** 应用外壳边界：DOM 根、toast 与弹层基座。不得 import 任何 domain feature。 */
export {
  APP_ID,
  MODAL_BACKDROP_ID,
  MODAL_ID,
  TOASTS_ID,
  appRoot,
  modalBackdrop,
  modalRoot,
  toastRoot,
  viewElement,
} from './dom';
export { toast } from './toast';
export { focusVisibleProjectLink } from './focus';
export { applyTabChrome, normalizeTab, TAB_IDS, type ShellTab } from './tabs';
export { mountShell, type ShellActions } from './shell';
export {
  activateModal,
  closeModal,
  openModal,
  registerModalCloseHook,
  requestModalClose,
  setModalReturnFocus,
} from './modal';
