"""周复盘编排（M2-10）：采集 → 汇总去重 → 渲染 → （写入 / 提交）。

幂等：按 ISO 周覆盖写 ``reviews/weekly/YYYY-Www.md``；重跑同周内容确定，不重复。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from summit_workbench.domain.weekly import (
    WeeklyReview,
    build_review,
    iso_week,
    previous_week_bounds,
)
from summit_workbench.repositories.weekly_review import write_weekly
from summit_workbench.workflows.weekly.collect import collect_weekly
from summit_workbench.workflows.weekly.render import render_weekly


@dataclass(frozen=True)
class WeeklyResult:
    review: WeeklyReview
    markdown: str
    note_path: Path | None


def generate_weekly(
    work_root: Path,
    vault_dir: Path,
    *,
    today: date,
    pending_review_count: int = 0,
    write: bool = True,
) -> WeeklyResult:
    """为 ``today`` 所在周的**上一周**生成复盘（L27：周一 07:30 复盘上周）。"""
    start, end = previous_week_bounds(today)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    week = iso_week(start)

    signals = collect_weekly(
        work_root,
        vault_dir,
        start_iso=start_iso,
        end_iso=end_iso,
        pending_review_count=pending_review_count,
    )
    review = build_review(week, start_iso, end_iso, signals)
    markdown = render_weekly(review)

    note_path = write_weekly(vault_dir, week, start_iso, end_iso, markdown) if write else None
    return WeeklyResult(review=review, markdown=markdown, note_path=note_path)
