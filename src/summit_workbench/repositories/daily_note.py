"""每日笔记（晨间指挥台）写入（M2-6）：``_vault/daily/YYYY-MM-DD.md``。

**幂等**：简报正文写在一对锚点之间（``BRIEF:START`` / ``BRIEF:END``）。同一天重跑只替换锚点区块，
不重复追加，也不动用户在锚点之外手写的内容。文件不存在时按统一 frontmatter 新建
（``type: daily`` / ``project: global``，PRD 3.1.5）。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories._atomic import atomic_write_text

BRIEF_START = "<!-- BRIEF:START 由 wb brief 生成，勿手改此区块 -->"
BRIEF_END = "<!-- BRIEF:END -->"


def daily_note_path(vault_dir: Path, day: str) -> Path:
    return vault_dir / "daily" / f"{day}.md"


def _frontmatter(day: str) -> str:
    # `area: work` 是工作库的既有约定（16 个模板全都带它）。SK 侧的综合类问题按 `area`
    # 过滤「笔记总览」，缺这一行会让当日简报从总览清单里静默消失（2026-09-15 实测：
    # 全库 62 篇里只有当日简报与推进日志两篇没有 area，因而看不见）。
    # `title` 同理：库规范 §5 要求中文标题进 frontmatter；缺它时 SK 回退成文件名
    # （`2026-09-14`），总览里只剩日期。这里与简报渲染的 H1「# 晨间简报 <日期>」一致。
    return (
        f"---\ndate: {day}\narea: work\ntitle: 晨间简报 {day}\n"
        f"type: daily\nstatus: active\nproject: global\nupdated: {day}\n---\n"
    )


def _brief_block(brief_markdown: str) -> str:
    return f"{BRIEF_START}\n{brief_markdown.rstrip()}\n{BRIEF_END}\n"


def read_brief_block(vault_dir: Path, day: str) -> str | None:
    """读回当日笔记锚点区块内的简报正文；文件或区块不存在时返回 None。"""
    path = daily_note_path(vault_dir, day)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    start = text.find(BRIEF_START)
    end = text.find(BRIEF_END)
    if start == -1 or end == -1 or end <= start:
        return None
    inner = text[start + len(BRIEF_START) : end]
    return inner.strip() or None


def write_brief(vault_dir: Path, day: str, brief_markdown: str) -> Path:
    """把简报正文幂等写入当日笔记的锚点区块，返回文件路径。

    当日笔记可能含用户锚点外手写内容：整体 read -> 锚点替换 -> 原子落盘 放在
    工作区锁内（launchd brief 与面板「生成简报」经同一把 .wb.lock 互斥），并
    全程用原子写，断电/被 kill 不留半截文件（P0-1 / P0-2）。
    """
    path = daily_note_path(vault_dir, day)
    block = _brief_block(brief_markdown)

    with workspace_lock(vault_dir.parent):
        if not path.is_file():
            atomic_write_text(path, _frontmatter(day) + "\n" + block, ensure_parents=True)
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
        atomic_write_text(path, new_text)
        return path
