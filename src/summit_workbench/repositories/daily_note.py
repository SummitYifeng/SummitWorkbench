"""晨间简报（晨间指挥台）写入：``profile_dir(workspace_id)/briefs/YYYY-MM-DD.md``。

**不在 vault 内**（2026-09-19 起，契约 §1/§3 明说简报不在库内）：由工作台写在本机
程序目录，随 Git 同步的是"知识内容"而不是每日机器产物。落点统一由
:mod:`summit_workbench.config.app_support` 的 ``briefs_dir`` 派生。

**幂等**：简报正文写在一对锚点之间（``BRIEF:START`` / ``BRIEF:END``）。同一天重跑只替换锚点
区块，不重复追加，也不动用户在锚点之外手写的内容。文件不存在时按统一 frontmatter 新建
（``type: daily`` / ``project: global``，PRD 3.1.5）。

``workspace_id`` 省略时按 vault marker 派生（``workspace_id_for_vault``）——这与 CLI 的
``resolve_active_workspace()``、Web 的 ``WebContext.workspace_id`` 是同一个 workspace 身份；
三者都指向 ``profile_dir(<同一 id>)``，不会读写分裂。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.app_support import briefs_dir
from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.workspace_manifest import workspace_id_for_vault

BRIEF_START = "<!-- BRIEF:START 由 wb brief 生成，勿手改此区块 -->"
BRIEF_END = "<!-- BRIEF:END -->"


def brief_workspace_key(vault_dir: Path, workspace_id: str | None) -> str:
    """本机简报落点的 workspace 键：显式 workspace_id 优先，缺失时由 vault marker 派生。"""
    return workspace_id or workspace_id_for_vault(vault_dir)


def daily_note_path(
    vault_dir: Path,
    day: str,
    *,
    workspace_id: str | None = None,
    home: Path | None = None,
) -> Path:
    return briefs_dir(brief_workspace_key(vault_dir, workspace_id), home) / f"{day}.md"


def _frontmatter(day: str) -> str:
    # `area: work` 是工作库的既有约定（16 个模板全都带它）。简报虽不在库内，但正文格式
    # 与字段保持不变（契约要求：落点变，内容不变）。`title` 与渲染的 H1 一致。
    return (
        f"---\ndate: {day}\narea: work\ntitle: 晨间简报 {day}\n"
        f"type: daily\nstatus: active\nproject: global\nupdated: {day}\n---\n"
    )


def _brief_block(brief_markdown: str) -> str:
    return f"{BRIEF_START}\n{brief_markdown.rstrip()}\n{BRIEF_END}\n"


def read_brief_block(
    vault_dir: Path,
    day: str,
    *,
    workspace_id: str | None = None,
    home: Path | None = None,
) -> str | None:
    """读回当日简报锚点区块内的正文；文件或区块不存在时返回 None。"""
    path = daily_note_path(vault_dir, day, workspace_id=workspace_id, home=home)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    start = text.find(BRIEF_START)
    end = text.find(BRIEF_END)
    if start == -1 or end == -1 or end <= start:
        return None
    inner = text[start + len(BRIEF_START) : end]
    return inner.strip() or None


def write_brief(
    vault_dir: Path,
    day: str,
    brief_markdown: str,
    *,
    workspace_id: str | None = None,
    home: Path | None = None,
) -> Path:
    """把简报正文幂等写入当日简报的锚点区块，返回文件路径。

    当日简报可能含用户锚点外手写内容：整体 read -> 锚点替换 -> 原子落盘 放在
    工作区锁内（launchd brief 与面板「生成简报」经同一把 .wb.lock 互斥），并
    全程用原子写，断电/被 kill 不留半截文件（P0-1 / P0-2）。
    """
    path = daily_note_path(vault_dir, day, workspace_id=workspace_id, home=home)
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
