"""每日笔记（晨间指挥台）写入（M2-6）：``_vault/daily/YYYY-MM-DD.md``。

**幂等**：简报正文写在一对锚点之间（``BRIEF:START`` / ``BRIEF:END``）。同一天重跑只替换锚点区块，
不重复追加，也不动用户在锚点之外手写的内容。文件不存在时按统一 frontmatter 新建
（``type: daily`` / ``project: global``，PRD 3.1.5）。
"""

from __future__ import annotations

from pathlib import Path

BRIEF_START = "<!-- BRIEF:START 由 wb brief 生成，勿手改此区块 -->"
BRIEF_END = "<!-- BRIEF:END -->"


def daily_note_path(vault_dir: Path, day: str) -> Path:
    return vault_dir / "daily" / f"{day}.md"


def _frontmatter(day: str) -> str:
    return (
        f"---\ndate: {day}\ntype: daily\nstatus: active\nproject: global\n"
        f"updated: {day}\n---\n"
    )


def _brief_block(brief_markdown: str) -> str:
    return f"{BRIEF_START}\n{brief_markdown.rstrip()}\n{BRIEF_END}\n"


def write_brief(vault_dir: Path, day: str, brief_markdown: str) -> Path:
    """把简报正文幂等写入当日笔记的锚点区块，返回文件路径。"""
    path = daily_note_path(vault_dir, day)
    block = _brief_block(brief_markdown)

    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_frontmatter(day) + "\n" + block, encoding="utf-8")
        return path

    text = path.read_text(encoding="utf-8")
    start = text.find(BRIEF_START)
    end = text.find(BRIEF_END)
    if start != -1 and end != -1 and end > start:
        # 替换既有锚点区块（含结束锚点自身）。
        new_text = text[:start] + block.rstrip("\n") + text[end + len(BRIEF_END) :]
    else:
        # 无锚点：在文末追加区块，保留用户既有内容。
        sep = "" if text.endswith("\n") else "\n"
        new_text = text + sep + "\n" + block
    path.write_text(new_text, encoding="utf-8")
    return path
