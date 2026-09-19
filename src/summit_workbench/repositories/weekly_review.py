"""周复盘笔记读写：``profile_dir(workspace_id)/weekly/YYYY-Www.md``。

**不在 vault 内**（2026-09-19 起，契约 §1/§3 明说周报不在库内）：与晨间简报一样写在本机
程序目录，落点由 :mod:`summit_workbench.config.app_support` 的 ``weekly_dir`` 派生。

幂等键 = ISO 周（``YYYY-Www``）：同一周重跑覆盖同一文件，不产生重复（PRD 3.4 / L27）。
统一 frontmatter：``type: weekly-review`` / ``project: global``（scope=global）。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.app_support import weekly_dir
from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.workspace_manifest import workspace_id_for_vault


def weekly_path(
    vault_dir: Path,
    week: str,
    *,
    workspace_id: str | None = None,
    home: Path | None = None,
) -> Path:
    key = workspace_id or workspace_id_for_vault(vault_dir)
    return weekly_dir(key, home) / f"{week}.md"


def _frontmatter(week: str, start: str, end: str) -> str:
    return (
        f"---\ndate: {start}\ntype: weekly-review\nstatus: active\nproject: global\n"
        f"week: {week}\nrange: {start}~{end}\nupdated: {end}\n---\n"
    )


def write_weekly(
    vault_dir: Path,
    week: str,
    start: str,
    end: str,
    body_markdown: str,
    *,
    workspace_id: str | None = None,
    home: Path | None = None,
) -> Path:
    """覆盖写周复盘笔记，返回路径（工作区锁内原子落盘，P0-1/P0-2）。"""
    path = weekly_path(vault_dir, week, workspace_id=workspace_id, home=home)
    text = _frontmatter(week, start, end) + "\n" + body_markdown.rstrip() + "\n"
    with workspace_lock(vault_dir.parent):
        atomic_write_text(path, text, ensure_parents=True)
    return path
