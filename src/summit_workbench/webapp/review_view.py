"""审批页读取与计划文本渲染（LEGACY-APP-SPLIT-PLAN Step 9 / B3）。

从 ``legacy_app`` 抽出两个无副作用 helper：

- ``_load``：把 ``review.md`` 解析为 ``ReviewEntry`` 列表与解析错误列表；
- ``_plan_text``：把 ``ApplyReport`` 渲染为审批预演/应用结果的可读文本。

``routers/review.py``（Step 9）与 ``routers/review_apply.py``（Step 10）共用本模块，
以满足 ``LEGACY-APP-SPLIT-PLAN`` §4.1-5「路由之间不得互相 import」。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.domain.review import ReviewEntry
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.workflows.review_apply import ApplyReport


def _load(vault_dir: Path) -> tuple[list[ReviewEntry], list[str]]:
    path = review_path(vault_dir)
    if not path.is_file():
        return [], []
    parsed = parse_review_page(path.read_text(encoding="utf-8"))
    return parsed.entries, parsed.errors


def _plan_text(report: ApplyReport) -> str:
    head = "DRY-RUN（零写入）" if report.dry_run else "已显式应用"
    lines = [head, ""]
    for a in report.actions:
        icon = "✓" if a.executable else "✗"
        reason = f"  原因：{a.reason}" if a.reason else ""
        lines.append(f"{icon} {a.candidate_id}  {a.decision.value} → {a.destination}{reason}")
    lines.append("")
    lines.append(
        f"结果：批准写回={report.applied}  拒绝归档={report.rejected}  失败={report.failed}"
    )
    if report.archive_path is not None:
        lines.append(f"审计：{report.archive_path}")
    return "\n".join(lines)


__all__ = ["_load", "_plan_text"]
