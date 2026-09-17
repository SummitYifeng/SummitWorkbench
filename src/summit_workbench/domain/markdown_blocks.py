"""按 Markdown 标题切分可检索、可引用的正文块。

This module is deliberately neutral: both retrieval and approval source
readers use the same block semantics without depending on the ask workflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ``# 标题`` 与 ``## 标题`` 都是块边界；``### 标题`` 不匹配。
HEADING = re.compile(r"^#{1,2}\s+(.*?)\s*$")
# 仅一级标题：用来识别「文首的笔记标题」。
TITLE = re.compile(r"^#\s+\S")
FENCE = re.compile(r"^\s*(?:```|~~~)")


@dataclass(frozen=True)
class Chunk:
    """一个可被检索、可被引用的正文块。"""

    source_id: str
    heading: str
    text: str
    order: int

    @property
    def anchor(self) -> str:
        return f"{self.source_id}#{self.heading}" if self.heading else self.source_id


def chunk_markdown(source_id: str, body: str) -> list[Chunk]:
    """把 ``body`` 切成 ``#`` / ``##`` 区块；空正文返回空列表。

    正文第一个非空行若是 H1，则视为笔记标题而不是章节标题；H3 及更深标题
    留在所属块内，围栏代码中的标题不切块。同名标题从第二次起追加序号。
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
