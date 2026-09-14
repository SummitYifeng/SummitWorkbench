"""`repositories/decisions.py`：决策台账的结构化读取、筛选与分面。

为什么值得单独测：这是 Workbench「决策」页的唯一数据源，而它的字段全是**本库约定**
（`decision_status` / `decided_on` / `review_on` / `supersedes`），不是 app 强制的固定字段——
解析必须宽容、但**不能默默解析错**。其中 `decided_on` 尤其危险：YAML 会把
`decided_on: 2026-03-24` 解析成 `date` 对象，2026-09-14 在
`scripts/kb_index_decisions.py` 上已经因此把整列日期变成空值。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.repositories.decisions import (
    STATUS_EFFECTIVE,
    STATUS_SUPERSEDED,
    STATUS_UNDER_REVIEW,
    collect_decisions,
    decision_facets,
    filter_decisions,
    status_counts,
)


def _decision(vault: Path, stem: str, front: str, *, body: str = "## 背景\n") -> None:
    path = vault / "decisions" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n\n# 决定\n\n{body}", encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _decision(
        vault,
        "20260623-registration-entity",
        "id: 2026-09-14-a103\ntitle: 登记主体统一为 HII\narea: work\nworkstream: hii\n"
        "project: hii-affairs\ntype: decision\ndomain: ip-trademark\nstatus: active\n"
        "decision_status: effective\ndecided_on: 2026-06-23\ncreated: 2026-09-14\n"
        "updated: 2026-09-14\ndate: 2026-06-23\nsummary: registrations 一律登记在 HII 名下。",
    )
    _decision(
        vault,
        "20260101-old-entity",
        "id: 2026-01-01-old\ntitle: 旧口径 <&>\narea: work\nworkstream: hii\n"
        "project: hii-affairs\ntype: decision\ndomain: ip-trademark\nstatus: superseded\n"
        "decided_on: 2026-01-01\nreview_on: 2026-10-01\ncreated: 2026-09-14\n"
        "updated: 2026-09-14\ndate: 2026-01-01\nsummary: 已被替代。\n"
        "superseded_by: [2026-09-14-a103]",
    )
    _decision(
        vault,
        "20260912-permission-model",
        "id: 2026-09-14-a404\ntitle: 权限模型 Level 1–5\narea: work\nworkstream: it\n"
        "project: it-development\ntype: decision\ndomain: portal-cms\nstatus: active\n"
        "decision_status: under-review\ndecided_on: 2026-09-12\ncreated: 2026-09-14\n"
        "updated: 2026-09-14\ndate: 2026-09-12\nsummary: 按五级分层。\n"
        "supersedes: [2026-01-01-old]",
    )
    # 非决策笔记：目录里的 note 不该进台账
    _decision(
        vault,
        "20260901-not-a-decision",
        "id: 2026-09-14-a999\ntitle: 不是决策\nproject: hii-affairs\ntype: note\n"
        "status: active\ndate: 2026-09-01\nsummary: x。",
    )
    # 缺失 decision_status：按 status 推导
    _decision(
        vault,
        "20260801-derived",
        "id: 2026-09-14-a998\ntitle: 推导状态\ntype: decision\nproject: global\n"
        "status: superseded\ndate: 2026-08-01\nsummary: 缺失 decision_status。",
    )
    return vault


def test_collect_reads_rows_sorted_by_decided_on_desc(tmp_path: Path) -> None:
    rows = collect_decisions(_vault(tmp_path))
    assert [row.path for row in rows] == [
        "decisions/20260912-permission-model",
        "decisions/20260801-derived",
        "decisions/20260623-registration-entity",
        "decisions/20260101-old-entity",
    ]
    assert all(row.decided_on for row in rows), "decided_on 不得为空（YAML date 陷阱）"


def test_collect_skips_non_decision_notes(tmp_path: Path) -> None:
    rows = collect_decisions(_vault(tmp_path))
    assert all("not-a-decision" not in row.path for row in rows)


def test_decision_status_is_declared_or_derived(tmp_path: Path) -> None:
    rows = {row.path: row for row in collect_decisions(_vault(tmp_path))}
    assert rows["decisions/20260912-permission-model"].status == STATUS_UNDER_REVIEW
    assert rows["decisions/20260623-registration-entity"].status == STATUS_EFFECTIVE
    # 缺失 decision_status、但 status: superseded → 推导为已被替代
    assert rows["decisions/20260801-derived"].status == STATUS_SUPERSEDED


def test_project_global_becomes_none(tmp_path: Path) -> None:
    rows = {row.path: row for row in collect_decisions(_vault(tmp_path))}
    assert rows["decisions/20260801-derived"].project is None
    assert rows["decisions/20260623-registration-entity"].project == "hii-affairs"


def test_supersedes_and_superseded_by_are_parsed(tmp_path: Path) -> None:
    rows = {row.path: row for row in collect_decisions(_vault(tmp_path))}
    assert rows["decisions/20260912-permission-model"].supersedes == ("2026-01-01-old",)
    assert rows["decisions/20260101-old-entity"].superseded_by == ("2026-09-14-a103",)


def test_filters_combine_as_and(tmp_path: Path) -> None:
    rows = collect_decisions(_vault(tmp_path))
    assert {row.project for row in filter_decisions(rows, project="hii-affairs")} == {"hii-affairs"}
    assert [row.path for row in filter_decisions(rows, domain="portal-cms")] == [
        "decisions/20260912-permission-model"
    ]
    assert [row.path for row in filter_decisions(rows, status=STATUS_UNDER_REVIEW)] == [
        "decisions/20260912-permission-model"
    ]
    # 关键词只匹配标题与摘要
    assert [row.path for row in filter_decisions(rows, query="五级")] == [
        "decisions/20260912-permission-model"
    ]
    assert filter_decisions(rows, query="正文里才有的词") == []
    # 组合是 AND：管线对、主题不对 → 空
    assert filter_decisions(rows, project="hii-affairs", domain="portal-cms") == []


def test_facets_and_counts(tmp_path: Path) -> None:
    rows = collect_decisions(_vault(tmp_path))
    facets = decision_facets(rows)
    assert facets["projects"] == ["hii-affairs", "it-development"]
    assert facets["domains"] == ["ip-trademark", "portal-cms"]
    assert facets["statuses"] == [STATUS_EFFECTIVE, STATUS_UNDER_REVIEW, STATUS_SUPERSEDED]
    assert status_counts(rows) == {
        STATUS_EFFECTIVE: 1,
        STATUS_UNDER_REVIEW: 1,
        STATUS_SUPERSEDED: 2,
    }


def test_missing_directory_yields_no_rows(tmp_path: Path) -> None:
    assert collect_decisions(tmp_path / "empty") == []
