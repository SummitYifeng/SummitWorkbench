"""决策台账的结构化读取：``decisions/*.md`` → 可筛选的行。

为什么单独一个模块：``index/decisions.md`` 是**给人看的台账页**（由
``scripts/kb_index_decisions.py`` 从同一批 frontmatter 重生成），而 Workbench 的「决策」页
要按**管线 / 主题 / 状态**筛选、并展示「一条决策推翻了哪一条」的演进关系——那需要结构化行，
不是 Markdown。两者共用同一批 frontmatter 字段，口径必须一致：

- ``decision_status``：``effective`` / ``superseded`` / ``under-review``；
  缺失时按 ``status`` 推导
  （``status: superseded`` ⇒ ``superseded``，
  否则 ``effective``）。
- ``decided_on`` / ``review_on``：决策日期与复核日期
  （YAML 会把它们解析成 ``date`` 而不是 ``str``）。
- ``supersedes`` / ``superseded_by``：互链的决策 ``id``。

⚠️ 这些字段都是**本库约定**，不是 app 强制的固定字段；因此解析必须宽容：
缺字段不报错，只让这一行少一点信息。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from summit_workbench.repositories.vault import load_note

STATUS_EFFECTIVE = "effective"
STATUS_SUPERSEDED = "superseded"
STATUS_UNDER_REVIEW = "under-review"
DECISION_STATUSES: tuple[str, ...] = (STATUS_EFFECTIVE, STATUS_UNDER_REVIEW, STATUS_SUPERSEDED)

# 台账页与界面共用的中文标签（改这里就同时改两处，避免两套说法）。
STATUS_LABELS: dict[str, str] = {
    STATUS_EFFECTIVE: "生效中",
    STATUS_UNDER_REVIEW: "待复核",
    STATUS_SUPERSEDED: "已被替代",
}


@dataclass(frozen=True)
class DecisionRow:
    """一条决策的结构化视图；``path`` 是引用用的稳定标识（vault 相对路径，无 ``.md``）。"""

    path: str
    id: str
    title: str
    summary: str
    status: str
    decided_on: str
    review_on: str | None
    project: str | None
    domain: str | None
    supersedes: tuple[str, ...]
    superseded_by: tuple[str, ...]
    tags: tuple[str, ...]


def _text(value: object) -> str:
    """frontmatter 值 → 字符串。

    ⚠️ 必须处理 ``date`` / ``datetime``：YAML 会把 ``decided_on: 2026-03-24`` 解析成 ``date``。
    2026-09-14 在 ``scripts/kb_index_decisions.py`` 上踩过同一个坑（整列日期变成空）。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _as_list(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(item for item in (_text(entry) for entry in value) if item)
    single = _text(value)
    return (single,) if single else ()


def _status(meta: dict[str, object]) -> str:
    declared = _text(meta.get("decision_status"))
    if declared in DECISION_STATUSES:
        return declared
    return STATUS_SUPERSEDED if _text(meta.get("status")) == "superseded" else STATUS_EFFECTIVE


def _row(path: Path, vault_dir: Path) -> DecisionRow | None:
    note = load_note(path)
    if note.parse_error is not None or str(note.meta.get("type")) != "decision":
        return None
    meta = note.meta
    decided_on = _text(meta.get("decided_on")) or _text(meta.get("date"))
    review_on = _text(meta.get("review_on")) or None
    project = _text(meta.get("project")) or None
    return DecisionRow(
        path=path.relative_to(vault_dir).with_suffix("").as_posix(),
        id=_text(meta.get("id")) or path.stem,
        title=_text(meta.get("title")) or path.stem,
        summary=_text(meta.get("summary")),
        status=_status(meta),
        decided_on=decided_on,
        review_on=review_on,
        project=None if project in (None, "global") else project,
        domain=_text(meta.get("domain")) or None,
        supersedes=_as_list(meta.get("supersedes")),
        superseded_by=_as_list(meta.get("superseded_by")),
        tags=_as_list(meta.get("tags")),
    )


def collect_decisions(vault_dir: Path) -> list[DecisionRow]:
    """读 ``<vault>/decisions/*.md``；按决定日期倒序（同日按路径）。"""
    directory = vault_dir / "decisions"
    if not directory.is_dir():
        return []
    rows = [row for path in sorted(directory.glob("*.md")) if (row := _row(path, vault_dir))]
    rows.sort(key=lambda item: (item.decided_on, item.path), reverse=True)
    return rows


def filter_decisions(
    rows: Iterable[DecisionRow],
    *,
    project: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    query: str | None = None,
) -> list[DecisionRow]:
    """按管线 / 主题 / 状态 / 关键词过滤（全部可选，组合为 AND）。

    关键词只匹配标题与摘要——**不搜正文**：这是台账视图，正文属于笔记本身。
    """
    needle = (query or "").strip().casefold()
    wanted_status = (status or "").strip()
    return [
        row
        for row in rows
        if (not project or row.project == project)
        and (not domain or row.domain == domain)
        and (not wanted_status or row.status == wanted_status)
        and (not needle or needle in row.title.casefold() or needle in row.summary.casefold())
    ]


def decision_facets(rows: Sequence[DecisionRow]) -> dict[str, list[str]]:
    """界面筛选器要用的取值集合（去重后排序）。"""
    return {
        "projects": sorted({row.project for row in rows if row.project}),
        "domains": sorted({row.domain for row in rows if row.domain}),
        "statuses": list(DECISION_STATUSES),
    }


def status_counts(rows: Sequence[DecisionRow]) -> dict[str, int]:
    counts = {status: 0 for status in DECISION_STATUSES}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts
