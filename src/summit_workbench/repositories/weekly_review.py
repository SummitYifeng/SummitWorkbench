"""周复盘笔记读写（M2-10）：``_vault/reviews/weekly/YYYY-Www.md``。

幂等键 = ISO 周（``YYYY-Www``）：同一周重跑覆盖同一文件，不产生重复（PRD 3.4 / L27）。
统一 frontmatter：``type: weekly-review`` / ``project: global``（scope=global）。
"""

from __future__ import annotations

from pathlib import Path


def weekly_path(vault_dir: Path, week: str) -> Path:
    return vault_dir / "reviews" / "weekly" / f"{week}.md"


def _frontmatter(week: str, start: str, end: str) -> str:
    return (
        f"---\ndate: {start}\ntype: weekly-review\nstatus: active\nproject: global\n"
        f"week: {week}\nrange: {start}~{end}\nupdated: {end}\n---\n"
    )


def write_weekly(vault_dir: Path, week: str, start: str, end: str, body_markdown: str) -> Path:
    """覆盖写周复盘笔记，返回路径。"""
    path = weekly_path(vault_dir, week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _frontmatter(week, start, end) + "\n" + body_markdown.rstrip() + "\n", encoding="utf-8"
    )
    return path
