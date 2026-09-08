/** 今日页 feature：简报、捕捉快捷行与会议导入抽屉。 */
import { todayHtml } from './render';
import type { TodayActions, TodayState } from './types';

export function mountToday(
  view: HTMLElement,
  state: TodayState | null,
  options: {
    importing: boolean;
    importOpen: boolean;
    health: { tone: string; label: string };
    actions: TodayActions;
  },
): void {
  const captureValue = view.querySelector<HTMLInputElement>('#capture-input')?.value ?? '';
  view.innerHTML = todayHtml({ state, ...options }, captureValue);
  if (!state) return;

  view.querySelector<HTMLFormElement>('#capture-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = view.querySelector<HTMLInputElement>('#capture-input');
    const text = input?.value.trim() ?? '';
    if (!text) return;
    void options.actions.capture(text).then(() => {
      if (input) input.value = '';
    });
  });

  const drawer = view.querySelector<HTMLElement>('#import-drawer');
  const importButton = view.querySelector<HTMLButtonElement>('#btn-import-meeting');
  const closeButton = view.querySelector<HTMLButtonElement>('#btn-import-close');
  const setOpen = (open: boolean): void => {
    options.actions.toggleImport(open);
    if (drawer) drawer.hidden = !open;
    if (importButton) importButton.textContent = open ? '－ 收起导入' : '＋ 导入会议纪要';
  };
  importButton?.addEventListener('click', () => setOpen(!options.importOpen));
  closeButton?.addEventListener('click', () => setOpen(false));
  importButton && (importButton.textContent = options.importOpen ? '－ 收起导入' : '＋ 导入会议纪要');

  const zone = view.querySelector<HTMLElement>('#dropzone');
  const fileInput = view.querySelector<HTMLInputElement>('#file-input');
  const pick = view.querySelector<HTMLButtonElement>('#btn-pick');
  if (!zone || !fileInput) return;
  pick?.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) void options.actions.importFile(file);
    fileInput.value = '';
  });
  zone.addEventListener('dragover', (event) => {
    event.preventDefault();
    zone.classList.add('dragover');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    zone.classList.remove('dragover');
    const file = event.dataTransfer?.files?.[0];
    if (file) void options.actions.importFile(file);
  });
}

export { todayHtml } from './render';
export type { TodayActions, TodayRenderOptions, TodayState } from './types';
