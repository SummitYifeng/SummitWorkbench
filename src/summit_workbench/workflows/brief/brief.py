"""晨间简报编排（M2-6 / M2-8）：采集 → 排序 → 组装 → 渲染 →（落快照 / 写笔记 / 通知）。

依赖以注入方式传入（``facts_source`` / ``rank`` / ``notifier``），使编排层不认识具体供应商与
配置细节，便于离线测试。写盘幂等：快照按日覆盖、笔记按锚点替换（见对应 repository）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from summit_workbench.domain.brief import (
    ActionSignal,
    Brief,
    HealthState,
    evaluate_health,
    select_actions,
)
from summit_workbench.observability.notifier import send_notification
from summit_workbench.repositories.daily_note import write_brief
from summit_workbench.repositories.signal_snapshot import write_snapshot
from summit_workbench.workflows.brief.collect import FactsSource, collect_signals
from summit_workbench.workflows.brief.ranking import RankingResult
from summit_workbench.workflows.brief.render import render_brief

RankFn = Callable[[list[ActionSignal]], RankingResult]
Notifier = Callable[[str, str], bool]


@dataclass(frozen=True)
class BriefResult:
    brief: Brief
    markdown: str
    ranking: RankingResult
    snapshot_path: Path | None
    note_path: Path | None
    notified: bool


def assemble_brief(
    work_root: Path,
    vault_dir: Path,
    *,
    day: str,
    timezone: str,
    facts_source: FactsSource | None,
    rank: RankFn,
    pending_review_count: int = 0,
) -> tuple[Brief, RankingResult]:
    """采集 + 排序 + 配额挑选，组装出一份 :class:`Brief`（不写盘）。"""
    collected = collect_signals(
        work_root,
        vault_dir,
        timezone=timezone,
        facts_source=facts_source,
        pending_review_count=pending_review_count,
    )
    ranking = rank(collected.candidates)
    actions = select_actions(collected.candidates, ranking.order)

    health: HealthState = evaluate_health(
        signal_count=collected.signal_count,
        ranking_degraded=ranking.degraded,
        source_failures=tuple(collected.source_failures),
    )

    brief = Brief(
        date=day,
        health=health,
        meetings=tuple(collected.meetings),
        tasks=tuple(collected.tasks),
        actions=tuple(actions),
        proposals=tuple(collected.proposals),
        completions=tuple(collected.completions),
        pending_review_count=collected.pending_review_count,
        ranking_model=ranking.model_id,
    )
    return brief, ranking


def generate_brief(
    work_root: Path,
    vault_dir: Path,
    *,
    day: str,
    timezone: str,
    facts_source: FactsSource | None,
    rank: RankFn,
    pending_review_count: int = 0,
    write: bool = True,
    notify: bool = False,
    notifier: Notifier = send_notification,
    now: datetime | None = None,
) -> BriefResult:
    """生成简报并（默认）幂等写入快照与当日笔记；``write=False`` 为 dry-run。"""
    brief, ranking = assemble_brief(
        work_root,
        vault_dir,
        day=day,
        timezone=timezone,
        facts_source=facts_source,
        rank=rank,
        pending_review_count=pending_review_count,
    )
    markdown = render_brief(brief, ranking.groups)

    snapshot_path: Path | None = None
    note_path: Path | None = None
    if write:
        snapshot_path = write_snapshot(vault_dir, day, brief.as_snapshot())
        note_path = write_brief(vault_dir, day, markdown)

    notified = False
    if notify and not brief.health.ok:
        notified = notifier("SummitWorkbench 简报", brief.health.line())

    return BriefResult(
        brief=brief,
        markdown=markdown,
        ranking=ranking,
        snapshot_path=snapshot_path,
        note_path=note_path,
        notified=notified,
    )
