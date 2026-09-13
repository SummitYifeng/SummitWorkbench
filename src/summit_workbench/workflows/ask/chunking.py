"""按 ``#`` 与 ``##`` 区块切分笔记正文，产出「路径#区块」级锚点。

引用粒度就是这里定的：**块**，不是整篇。锚点形如 ``hii/notes/foo#逐项商标归属与状态``，
与 Obsidian 的 ``[[文件#标题]]`` 语法一致，因此同一个引用在 Workbench 来源面板与
Obsidian 里都能直接跳转。

约定：

- **块边界＝`#` 与 `##`**（一级与二级标题都切块）。原始材料常用一级标题分大章
  （如 HII IP 原件的 20 个 ``#`` 章节），只切 ``##`` 会让这些章节的正文并进相邻块、无法定点引用；
  而 Obsidian 的 ``[[文件#标题]]`` 本来就不区分标题级别，扩到 ``#`` 才与它一致。
- **例外：文首的 H1 是「笔记标题」不是章节**，不切块（见 `chunk_markdown` 的说明）。
- **`###` 及更深不切块**，留在所属的一二级块内（避免把长文切得过碎）。
- 首个块边界之前的正文是「前言块」，锚点不带 ``#``（就是笔记本身）。
- ``` 围栏代码块里的 ``#`` / ``##`` 不算标题（避免把示例文本切碎）。
- 同名标题重复出现时，第 2 次起在锚点追加 `` 2``、`` 3``（Obsidian 对同名标题只解析到第一个，
  所以我们显式区分，并在 conventions.md 里写明）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `# 标题` 与 `## 标题` 都是块边界；`### 标题` 不匹配（第三个字符是 `#` 而非空白）。
HEADING = re.compile(r"^#{1,2}\s+(.*?)\s*$")
# 仅一级标题：用来识别「文首的笔记标题」（见 chunk_markdown 的例外说明）。
TITLE = re.compile(r"^#\s+\S")
FENCE = re.compile(r"^\s*(?:```|~~~)")


@dataclass(frozen=True)
class Chunk:
    """一个可被检索、可被引用的正文块。"""

    source_id: str  # vault 相对路径（无 .md）
    heading: str  # 区块标题；前言块为 ""
    text: str  # 含标题行在内的块正文
    order: int  # 在文中的出现次序（0 起）

    @property
    def anchor(self) -> str:
        return f"{self.source_id}#{self.heading}" if self.heading else self.source_id


def chunk_markdown(source_id: str, body: str) -> list[Chunk]:
    """把 ``body`` 切成 ``#`` / ``##`` 区块；空正文返回空列表。

    **文首 H1 例外**：如果正文第一个非空行是 ``# 标题``，那是**笔记标题**而不是章节标题，

    不切块（留在前言块里）。理由：它下面的正文只是这篇笔记的引言，把它切成独立块会让
    「标题块」在检索里与实际内容块抢排名——2026-09-14 实测：
    `it/clusters/enrollment#报名与课程生命周期`
    这类标题块压过了真正有内容的 `#关键结论`，块级命中率只有 25%。
    原件材料内部的 ``#`` 大章不受影响（它们不是文首行，照常切块）。
    """
    if not body.strip():
        return []
    chunks: list[Chunk] = []
    used: dict[str, int] = {}
    heading = ""
    buffer: list[str] = []
    in_fence = False

    lines = body.splitlines()
    title_index: int | None = None
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        title_index = index if TITLE.match(line.strip()) else None
        break

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            chunks.append(Chunk(source_id=source_id, heading=heading, text=text, order=len(chunks)))

    for index, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue
        match = None if in_fence else HEADING.match(line)
        if match and index != title_index:
            flush()
            raw = match.group(1).strip().rstrip("#").strip() or "未命名区块"
            used[raw] = used.get(raw, 0) + 1
            heading = raw if used[raw] == 1 else f"{raw} {used[raw]}"
            buffer = [line]
            continue
        buffer.append(line)
    flush()
    return chunks
