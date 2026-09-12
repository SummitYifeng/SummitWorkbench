/** 项目详情的返回焦点：只认可见且已布局的链接（原 legacy-main 逐字搬迁）。 */
export function focusVisibleProjectLink(name: string): boolean {
  const target = Array.from(document.querySelectorAll<HTMLElement>('[data-action="open-view"]'))
    .find((el) => el.dataset.name === name && getComputedStyle(el).display !== 'none' &&
      getComputedStyle(el).visibility !== 'hidden' && el.getClientRects().length > 0);
  if (!target) return false;
  target.focus();
  return document.activeElement === target;
}
