import guideMd from '../../guide.md?raw';
import { esc, mdToHtml } from '../../md';

/** 指南页渲染（从 legacy-main 抽出，Step 1 起为纯字符串，不触碰 DOM）。 */

export function guideSummaryHtml(q: string): string {
  // <summary> 只允许短语内容：转义后仅放行行内代码
  const safe = esc(q);
  return safe.replace(/`([^`]+?)`/g, '<code>$1</code>');
}

let guideCache: string | null = null;

/** 仅测试用：丢弃模块级缓存，让 guideBodyHtml() 重新计算。 */
export function resetGuideCache(): void {
  guideCache = null;
}

export function guideBodyFrom(markdown: string): string {
  const lines = markdown.split('\n');
  const faqIdx = lines.findIndex((l) => /^#{1,4}\s*.*常见问题/.test(l));
  let html = mdToHtml((faqIdx === -1 ? lines : lines.slice(0, faqIdx)).join('\n'));
  if (faqIdx !== -1) {
    const rest = lines.slice(faqIdx + 1);
    const tailIdx = rest.findIndex((l) => /^#{1,4}\s/.test(l));
    const qaLines = tailIdx === -1 ? rest : rest.slice(0, tailIdx);
    const tail = tailIdx === -1 ? [] : rest.slice(tailIdx);
    const items: { q: string; a: string[] }[] = [];
    let cur: { q: string; a: string[] } | null = null;
    for (const line of qaLines) {
      const qm = line.match(/^\*\*Q[:：]\s*(.+?)\s*\*\*$/);
      if (qm) {
        cur = { q: qm[1].trim(), a: [] };
        items.push(cur);
        continue;
      }
      if (!cur || !line.trim()) continue;
      cur.a.push(line);
    }
    const faqHtml = items
      .map(
        (it) =>
          '<details class="faq-item"><summary>' + guideSummaryHtml(it.q) + '</summary>' +
          (it.a.length ? '<div class="faq-answer">' + mdToHtml(it.a.join('\n')) + '</div>' : '') +
          '</details>'
      )
      .join('');
    html += '<h3>常见问题</h3>' + faqHtml;
    if (tail.length) html += mdToHtml(tail.join('\n'));
  }
  return html;
}

export function guideBodyHtml(): string {
  if (guideCache) return guideCache;
  guideCache = guideBodyFrom(guideMd);
  return guideCache;
}

export function guideHtml(): string {
  return '<div class="guide">' +
    '<div class="guide-tools"><label for="guide-search">搜索指南</label>' +
    '<input id="guide-search" type="search" placeholder="搜索本地指南…">' +
    '<button class="ghost" type="button" id="guide-search-clear" hidden>清除</button></div>' +
    '<nav class="guide-index" aria-label="指南目录"><strong>目录</strong><div id="guide-index-links"></div></nav>' +
    '<p class="hint guide-no-results" id="guide-no-results" hidden>没有匹配内容，请清除搜索词。</p>' +
    '<div id="guide-content">' + guideBodyHtml() + '</div></div>';
}
