import { viewElement } from './dom';

/** 外壳的六个 tab：顺序即 DOM 顺序，也是 render() 的派发顺序。
 *
 * 2026-09-14：「决策」不再是独立页签——决策在各项目页的「决策记录」里看，
 * 跨项目找决策用「第二大脑」提问（决策台账页是 vault 内容的第三份副本、只增不减）。
 */
export const TAB_IDS = ['today', 'review', 'ask', 'projects', 'guide', 'settings'] as const;

export type ShellTab = (typeof TAB_IDS)[number];

/** 任意字符串归一化为合法 tab；未知值回退今日页（含已下线的 `decisions`）。 */
export function normalizeTab(value: string | undefined): ShellTab {
  return (TAB_IDS as readonly string[]).includes(value ?? '') ? (value as ShellTab) : 'today';
}

/** tab 按钮的 aria/active 状态与六视图显隐（原 render() 的前半段，逐条保留）。 */
export function applyTabChrome(tab: ShellTab): void {
  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((b) => {
    const active = b.dataset.tab === tab;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', active ? 'true' : 'false');
    b.setAttribute('tabindex', active ? '0' : '-1');
  });
  const views: Record<ShellTab, HTMLElement> = {
    today: viewElement('today') as HTMLElement,
    review: viewElement('review') as HTMLElement,
    ask: viewElement('ask') as HTMLElement,
    projects: viewElement('projects') as HTMLElement,
    guide: viewElement('guide') as HTMLElement,
    settings: viewElement('settings') as HTMLElement,
  };
  for (const name of TAB_IDS) {
    views[name].style.display = tab === name ? '' : 'none';
  }
  for (const name of TAB_IDS) {
    const view = views[name];
    view.setAttribute('aria-hidden', view.style.display === 'none' ? 'true' : 'false');
  }
}
