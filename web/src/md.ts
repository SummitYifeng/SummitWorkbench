// 简报 / 项目档案共用的 Markdown 子集渲染。
// 与后端 `webapp/views.py::md_to_html` **同规则**（改一边必须改另一边）：
//   块：标题 · 段落（软换行合并）· 无序/有序/任务列表（支持嵌套）· 表格 · 引用 · 代码块
//   行内：**粗体** · *斜体* · `代码` · [[目标|显示名]]
// 安全：**先整体 HTML 转义，再只对明确模式做替换**——不注入任意 HTML，也不信任 vault / 模型文本。

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

/** [[目标|显示名]] → 只显示「显示名」（有 title 保留目标）；[[目标]] → 显示目标。 */
function wikilinks(text: string): string {
  return text.replace(/\[\[([^\]]+?)\]\]/g, (_match: string, inner: string): string => {
    const bar = inner.indexOf('|');
    const target = bar === -1 ? inner : inner.slice(0, bar);
    const label = bar === -1 ? inner : inner.slice(bar + 1);
    const shown = label.trim() ? label : target;
    return '<span class="wikilink" title="' + target + '">' + shown + '</span>';
  });
}

/** 行内 Markdown → HTML（供单行片段使用：时间线摘要这类没有块结构、只有行内标记的文本）。
 *  不配对的标记（截断产生的孤立 `**`）不会被替换，原样保留，不会吞掉后面的内容。 */
export function inlineMd(text: string): string {
  return inlineMarkup(text);
}

function inlineMarkup(text: string): string {
  const safe = esc(text);
  const bold = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const em = bold.replace(/(^|[^*])\*([^*\n]+?)\*/g, '$1<em>$2</em>');
  const code = em.replace(/`([^`]+?)`/g, '<code>$1</code>');
  return wikilinks(code);
}

const FENCE = /^\s*```/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const LIST_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const TASK = /^\[([ xX])\]\s*(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
// 表格分隔行：至少要有一列 `---`，允许首尾竖线与对齐冒号。
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/;
const INDENTED = /^\s{2,}/;
// CJK（含全角标点）：软换行拼接时中文之间不插空格，否则会出现「收口； 相关方培训」这种缝。
const CJK = /[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]/;

// 判断边界字符时要跳过行内标记（**、`、空白），否则「…HII**、」接「**「活满」…」会在
// 两个 ** 之间判定成非中文，缝出一个空格。
const EDGE_LEAD = /^[\s*`]+/;
const EDGE_TAIL = /[\s*`]+$/;

function cjkBoundary(left: string, right: string): boolean {
  const a = left.replace(EDGE_TAIL, '').slice(-1);
  const b = right.replace(EDGE_LEAD, '').slice(0, 1);
  return Boolean(a) && Boolean(b) && CJK.test(a) && CJK.test(b);
}

/** 按 Markdown 软换行拼接多行：中文接中文直接连，其余补一个空格。 */
function joinSoft(parts: string[]): string {
  let out = '';
  for (const part of parts) {
    if (!out) {
      out = part;
      continue;
    }
    out += cjkBoundary(out, part) ? part : ' ' + part;
  }
  return out;
}

interface ListItem {
  indent: number;
  ordered: boolean;
  text: string;
}

function isTableStart(lines: string[], index: number): boolean {
  return (
    lines[index].includes('|') && index + 1 < lines.length && TABLE_SEP.test(lines[index + 1])
  );
}

function isBlockStart(lines: string[], index: number): boolean {
  const line = lines[index];
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    QUOTE.test(line) ||
    LIST_ITEM.test(line) ||
    isTableStart(lines, index)
  );
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map((cell) => cell.trim());
}

function listItemContent(item: ListItem): string {
  const task = TASK.exec(item.text);
  if (task) {
    const done = task[1].toLowerCase() === 'x';
    return (
      '<span class="task' +
      (done ? ' done' : '') +
      '">' +
      (done ? '☑' : '☐') +
      '</span> ' +
      inlineMarkup(task[2])
    );
  }
  return inlineMarkup(item.text);
}

/** 收一段列表：项本身 + 缩进续行（Markdown 的惰性续行，如「2. …」下面那行说明）。 */
function collectList(lines: string[], start: number): [ListItem[], number] {
  const items: ListItem[] = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) break;
    const match = LIST_ITEM.exec(line);
    if (match) {
      items.push({ indent: match[1].length, ordered: /^\d/.test(match[2]), text: match[3] });
      i += 1;
      continue;
    }
    if (items.length > 0 && INDENTED.test(line) && !isBlockStart(lines, i)) {
      items[items.length - 1].text = joinSoft([items[items.length - 1].text, line.trim()]);
      i += 1;
      continue;
    }
    break;
  }
  return [items, i];
}

function renderItems(items: ListItem[]): string {
  let html = '';
  // reclose：嵌套列表要落在父项 <li> **内部**，所以开嵌套列表前先把父项的 </li> 摘下来，
  // 等嵌套列表收尾再补回去（否则会渲染成 <li>外层</li><ul>…</ul> 这种兄弟结构）。
  const stack: { ordered: boolean; indent: number; reclose: boolean }[] = [];
  const open = (ordered: boolean, indent: number): void => {
    let reclose = false;
    if (stack.length > 0 && html.endsWith('</li>')) {
      html = html.slice(0, -'</li>'.length);
      reclose = true;
    }
    html += ordered ? '<ol>' : '<ul>';
    stack.push({ ordered, indent, reclose });
  };
  const close = (): void => {
    const top = stack.pop();
    html += top && top.ordered ? '</ol>' : '</ul>';
    if (top && top.reclose) html += '</li>';
  };
  for (const item of items) {
    while (stack.length > 0 && item.indent < stack[stack.length - 1].indent) close();
    const top = stack[stack.length - 1];
    if (!top || item.indent > top.indent) open(item.ordered, item.indent);
    else if (top.ordered !== item.ordered) {
      close();
      open(item.ordered, item.indent);
    }
    html += '<li>' + listItemContent(item) + '</li>';
  }
  while (stack.length > 0) close();
  return html;
}

export function mdToHtml(markdown: string): string {
  const lines = String(markdown ?? '').split('\n');
  const parts: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (FENCE.test(line)) {
      const lang = line.trim().replace(/^`+/, '').trim();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过收尾 fence（缺失时也不吞掉后面的内容）
      parts.push(
        '<pre><code' +
          (lang ? ' class="lang-' + esc(lang) + '"' : '') +
          '>' +
          esc(body.join('\n')) +
          '</code></pre>',
      );
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      const level = Math.min(heading[1].length, 3) + 1;
      parts.push('<h' + level + '>' + inlineMarkup(heading[2]) + '</h' + level + '>');
      i += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i])) {
        body.push((QUOTE.exec(lines[i]) as RegExpExecArray)[1]);
        i += 1;
      }
      parts.push('<blockquote><p>' + inlineMarkup(joinSoft(body)) + '</p></blockquote>');
      continue;
    }

    if (isTableStart(lines, i)) {
      const head = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      // 行里含 `|` 不等于还是表格行：紧跟其后的列表项（尤其 [[目标|显示名]]）不能被吞成一行。
      while (i < lines.length && lines[i].trim() && lines[i].includes('|') && !isBlockStart(lines, i)) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      parts.push(
        '<table><thead><tr>' +
          head.map((cell) => '<th>' + inlineMarkup(cell) + '</th>').join('') +
          '</tr></thead><tbody>' +
          rows
            .map(
              (row) =>
                '<tr>' + row.map((cell) => '<td>' + inlineMarkup(cell) + '</td>').join('') + '</tr>',
            )
            .join('') +
          '</tbody></table>',
      );
      continue;
    }

    if (LIST_ITEM.test(line)) {
      const [items, next] = collectList(lines, i);
      parts.push(renderItems(items));
      i = next;
      continue;
    }

    // 段落：连续的非空、非块起始行合并成一段（Markdown 的软换行）。
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) {
      para.push(lines[i].trim());
      i += 1;
    }
    if (para.length === 0) {
      para.push(line.trim());
      i += 1;
    }
    parts.push('<p>' + inlineMarkup(joinSoft(para)) + '</p>');
  }
  return parts.join('\n');
}
