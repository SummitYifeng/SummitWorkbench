import { esc } from '../../md';
import { guideHtml } from './render';

/** 指南 feature 边界：写入骨架后绑定目录、搜索与清空按钮（原 renderGuide）。 */
export function mountGuide(view: HTMLElement): void {
  view.innerHTML = guideHtml();
  const content = document.getElementById('guide-content');
  const index = document.getElementById('guide-index-links');
  if (!content || !index) return;
  const nodes = Array.from(content.children);
  let section: HTMLElement | null = null;
  let sectionIndex = 0;
  for (const node of nodes) {
    if (!section || node.tagName === 'H2' || node.tagName === 'H3') {
      section = document.createElement('section');
      section.className = 'guide-section';
      sectionIndex += 1;
      section.id = 'guide-section-' + sectionIndex;
      content.appendChild(section);
    }
    section.appendChild(node);
  }
  const sections = Array.from(content.querySelectorAll<HTMLElement>('.guide-section'));
  const headings = Array.from(content.querySelectorAll<HTMLElement>('h2, h3'));
  index.innerHTML = headings.map((heading, headingIndex) => {
    heading.id = 'guide-heading-' + headingIndex;
    const sectionId = heading.closest<HTMLElement>('.guide-section')?.id ?? '';
    return '<a href="#' + heading.id + '" class="guide-index-link level-' + heading.tagName.toLowerCase() + '" data-guide-section="' + esc(sectionId) + '">' +
      esc(heading.textContent ?? '') + '</a>';
  }).join('');
  const search = document.getElementById('guide-search') as HTMLInputElement | null;
  const clear = document.getElementById('guide-search-clear') as HTMLButtonElement | null;
  const empty = document.getElementById('guide-no-results');
  const applySearch = (): void => {
    const query = search?.value.trim().toLocaleLowerCase() ?? '';
    let visible = 0;
    sections.forEach((item) => {
      const match = !query || (item.textContent ?? '').toLocaleLowerCase().includes(query);
      item.hidden = !match;
      if (match) visible += 1;
    });
    index.querySelectorAll<HTMLAnchorElement>('.guide-index-link').forEach((link) => {
      const sectionId = link.dataset.guideSection;
      link.hidden = Boolean(sectionId && document.getElementById(sectionId)?.hidden);
    });
    if (clear) clear.hidden = !query;
    if (empty) empty.hidden = visible > 0;
  };
  search?.addEventListener('input', applySearch);
  clear?.addEventListener('click', () => {
    if (!search) return;
    search.value = '';
    applySearch();
    search.focus();
  });
}

export { guideBodyFrom, guideBodyHtml, guideHtml, guideSummaryHtml, resetGuideCache } from './render';
