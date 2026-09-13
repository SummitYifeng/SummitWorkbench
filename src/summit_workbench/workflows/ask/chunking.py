"""按 ``##`` 区块切分笔记正文，产出「路径#区块」级锚点。

引用粒度就是这里定的：**块**，不是整篇。锚点形如 ``hii/notes/foo#逐项商标归属与状态``，
与 Obsidian 的 ``[[文件#标题]]`` 语法一致，因此同一个引用在 Workbench 来源面板与
Obsidian 里都能直接跳转。

约定：

- 首个 ``##`` 之前的正文是「前言块」，锚点不带 ``#``（就是笔记本身）；
- ``` 围栏代码块里的 ``##`` 不算标题（避免把示例文本切碎）；
- 同名标题重复出现时，第 2 次起在锚点追加 `` 2``、`` 3``（Obsidian 对同名标题只解析到第一个，
  所以我们显式区分，并在 conventions.md 里写明）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING = re.compile(r"^##\s+(.*?)\s*$")
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
    """把 ``body`` 切成 ``##`` 区块；空正文返回空列表。"""
    if not body.strip():
        return []
    chunks: list[Chunk] = []
    used: dict[str, int] = {}
    heading = ""
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            chunks.append(Chunk(source_id=source_id, heading=heading, text=text, order=len(chunks)))

    for line in body.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue
        match = None if in_fence else HEADING.match(line)
        if match:
            flush()
            raw = match.group(1).strip().rstrip("#").strip() or "未命名区块"
            used[raw] = used.get(raw, 0) + 1
            heading = raw if used[raw] == 1 else f"{raw} {used[raw]}"
            buffer = [line]
            continue
        buffer.append(line)
    flush()
    return chunks
