"""Workbench「决策」页的只读 API。

一页看完整个决策台账：按**管线（project）/ 主题（domain）/ 状态**筛选，并给出
「这条决策推翻了哪一条、被哪一条推翻」的演进关系。

与 ``index/decisions.md`` 的分工：那个页面是**库内的台账页**（人读、可 grep、由脚本重生成），
本 API 是**界面视图**（可筛选、带关系解析）。两者都从 ``decisions/*.md`` 的 frontmatter 读，
口径由 :mod:`summit_workbench.repositories.decisions` 统一。
"""

from __future__ import annotations

from summit_workbench.repositories.decisions import (
    DECISION_STATUSES,
    STATUS_LABELS,
    DecisionRow,
    collect_decisions,
    decision_facets,
    filter_decisions,
    status_counts,
)
from summit_workbench.webapp.dependencies import RouteDependencies


def _payload(row: DecisionRow, index: dict[str, DecisionRow]) -> dict[str, object]:
    def link(decision_id: str) -> dict[str, str]:
        target = index.get(decision_id)
        return {
            "id": decision_id,
            "title": target.title if target else decision_id,
            "path": target.path if target else "",
        }

    return {
        "path": row.path,
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "status": row.status,
        "status_label": STATUS_LABELS.get(row.status, row.status),
        "decided_on": row.decided_on,
        "review_on": row.review_on,
        "project": row.project,
        "domain": row.domain,
        "tags": list(row.tags),
        # 关系解析好再给界面：界面不该再自己查 id → 标题。
        "supersedes": [link(item) for item in row.supersedes],
        "superseded_by": [link(item) for item in row.superseded_by],
    }


def register_decision_routes(dependencies: RouteDependencies) -> None:
    """注册决策台账的只读路由（``GET /api/decisions``）。"""
    app = dependencies.app
    context = dependencies.context

    @app.get("/api/decisions")
    def api_decisions(
        project: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, object]:
        """决策台账：全量 + 按条件筛选后的结果（一次返回，界面切换筛选不必再请求）。"""
        rows = collect_decisions(context.vault_dir)
        warnings: list[str] = []
        wanted_status = status if status in DECISION_STATUSES else None
        if status and wanted_status is None:
            # 不静默返回空列表：拼错状态词是使用者的常见误操作，必须说出来。
            warnings.append(
                f"未知状态 {status!r}，已忽略该筛选（允许值：{'/'.join(DECISION_STATUSES)}）"
            )

        selected = filter_decisions(
            rows, project=project, domain=domain, status=wanted_status, query=q
        )
        index = {row.id: row for row in rows}
        return {
            "ok": True,
            "decisions": [_payload(row, index) for row in selected],
            "counts": status_counts(rows),
            "selected_counts": status_counts(selected),
            "facets": decision_facets(rows),
            "status_labels": STATUS_LABELS,
            "filters": {"project": project, "domain": domain, "status": status, "q": q},
            "warnings": warnings,
        }
