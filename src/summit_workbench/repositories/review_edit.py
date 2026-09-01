"""审批页的单条变更（供本地 Web 面板与测试共用，等价于用户手改 Markdown）。

复用 :func:`parse_review_page` / :func:`render_review_page`：解析 → 定位 candidate_id →
`dataclasses.replace` 改裁决/字段 → 原子重写。**meetings.md 始终是唯一事实源**，因此这些变更
与 ``wb review apply`` 完全兼容；仅改页面不触发任何写回（写回仍由 apply 显式执行）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    RouteTarget,
)
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.review_page import (
    parse_review_page,
    render_review_page,
    review_path,
)


class ReviewEditError(RuntimeError):
    """审批页不可编辑（存在语法错误 / 找不到候选）。"""


def _rewrite(
    vault_dir: Path, candidate_id: str, mutate: Callable[[ApprovalCandidate], ApprovalCandidate]
) -> None:
    path = review_path(vault_dir)
    if not path.is_file():
        raise ReviewEditError("审批页不存在，先运行 wb review refresh")
    parsed = parse_review_page(path.read_text(encoding="utf-8"))
    if parsed.errors:
        raise ReviewEditError("审批页存在语法错误，拒绝改写：" + "; ".join(parsed.errors))
    found = False
    new_entries = []
    for entry in parsed.entries:
        if entry.candidate.candidate_id == candidate_id:
            new_entries.append(replace(entry, candidate=mutate(entry.candidate)))
            found = True
        else:
            new_entries.append(entry)
    if not found:
        raise ReviewEditError(f"找不到候选：{candidate_id}")
    atomic_write_text(path, render_review_page(new_entries))


def set_decision(vault_dir: Path, candidate_id: str, decision: CandidateDecision) -> None:
    """把一条候选置为 批准/拒绝/待确认（等价于勾选/删除线/取消）。"""
    _rewrite(vault_dir, candidate_id, lambda c: replace(c, decision=decision))


def update_fields(
    vault_dir: Path,
    candidate_id: str,
    *,
    description: str | None = None,
    target_project: str | None = None,
    route: RouteTarget | None = None,
    due_date: str | None = None,
) -> None:
    """原地修改候选正文 / 目标项目 / route / 截止日期（None 表示保持不变）。"""

    def mutate(c: ApprovalCandidate) -> ApprovalCandidate:
        return replace(
            c,
            description=description if description is not None else c.description,
            target_project=target_project if target_project is not None else c.target_project,
            route=route if route is not None else c.route,
            due_date=due_date if due_date is not None else c.due_date,
        )

    _rewrite(vault_dir, candidate_id, mutate)
