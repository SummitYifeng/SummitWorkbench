// 简报/问答使用的 Markdown 子集渲染（与后端 views.md_to_html 同规则：标题/列表/引用/行内）。
// 安全：先整体 HTML 转义，再只对明确模式做替换，不注入任意 HTML。

export function esc(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (c: string): string => {
    const map: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return map[c] ?? c;
  });
}

function wikilinks(text: string): string {
  const parts: string[] = [];
  let rest = text;
  for (;;) {
    const start = rest.indexOf('[[');
    if (start === -1) {
      parts.push(rest);
      break;
    }
    const end = rest.indexOf(']]', start + 2);
    if (end === -1) {
      parts.push(rest);
      break;
    }
    parts.push(rest.slice(0, start));
    parts.push('<span class="wikilink">' + rest.slice(start + 2, end) + '</span>');
    rest = rest.slice(end + 2);
  }
  return parts.join('');
}

function inlineMarkup(text: string): string {
  const safe = esc(text);
  const bold = safe.replace(/\*{2}(.+?)\*{2}/g, '<strong>$1</strong>');
  const code = bold.replace(/`([^`]+?)`/g, '<code>$1</code>');
  return wikilinks(code);
}

export function mdToHtml(markdown: string): string {
  const parts: string[] = [];
  let inList = false;
  const closeList = (): void => {
    if (inList) {
      parts.push('</ul>');
      inList = false;
    }
  };
  for (const raw of markdown.split('\n')) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) {
      closeList();
      continue;
    }
    if (line.startsWith('### ')) {
      closeList();
      parts.push('<h4>' + inlineMarkup(line.slice(4)) + '</h4>');
    } else if (line.startsWith('## ')) {
      closeList();
      parts.push('<h3>' + inlineMarkup(line.slice(3)) + '</h3>');
    } else if (line.startsWith('# ')) {
      closeList();
      parts.push('<h2>' + inlineMarkup(line.slice(2)) + '</h2>');
    } else if (line.startsWith('> ')) {
      closeList();
      parts.push('<blockquote>' + inlineMarkup(line.slice(2)) + '</blockquote>');
    } else if (line.trimStart().startsWith('- ')) {
      if (!inList) {
        parts.push('<ul>');
        inList = true;
      }
      parts.push('<li>' + inlineMarkup(line.trimStart().slice(2)) + '</li>');
    } else {
      closeList();
      parts.push('<p>' + inlineMarkup(line) + '</p>');
    }
  }
  closeList();
  return parts.join('\n');
}
