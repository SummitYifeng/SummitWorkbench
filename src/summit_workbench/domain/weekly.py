"""每周复盘的纯领域模型与规则（PRD M2-10 / L27 / L28）。

周复盘覆盖上一自然周（周一 00:00 – 周日 23:59）。幂等键 = ISO 周（``YYYY-Www``）。
**不是 7 份日报的改写**：由采集层从会议笔记 / 项目主笔记 / 工作记录 / git / 任务状态重新汇总；
本模块只定义数据形状与「事实 vs 建议分区」的约束，无 IO、无供应商。

证据分区（L26 沿用）：本周完成 / 关键决策 / 未闭合信号 / 停滞项目属**事实区**，每条附来源；
下周建议属**提议区**，标记 ``proposal``、附依据、不得升级为事实或改写项目笔记（L28）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from summit_workbench.domain.brief import EvidenceLevel


def iso_week(day: date) -> str:
    """ISO 周标签 ``YYYY-Www``（幂等键）。"""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_bounds(day: date) -> tuple[date, date]:
    """包含 ``day`` 的自然周的 (周一, 周日)。"""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def previous_week_bounds(today: date) -> tuple[date, date]:
    """``today`` 所在周的上一周 (周一, 周日)（周一 07:30 复盘取上周，L27）。"""
    this_monday, _ = week_bounds(today)
    last_monday = this_monday - timedelta(days=7)
    return last_monday, last_monday + timedelta(days=6)


@dataclass(frozen=True)
class WeeklyItem:
    """周复盘的一条目。事实项 ``source_ref`` 必填；``project`` 可空（跨项目）。"""

    text: str
    source_ref: str
    evidence: EvidenceLevel = EvidenceLevel.E2
    project: str | None = None


@dataclass(frozen=True)
class WeeklyReview:
    """一份跨项目周复盘。各区已去重、事实与建议分区。"""

    week: str  # YYYY-Www
    start: str  # ISO 周一
    end: str  # ISO 周日
    completed: tuple[WeeklyItem, ...] = ()  # 本周完成（E1/E2，附来源）
    decisions: tuple[WeeklyItem, ...] = ()  # 关键决策（附来源）
    unclosed: tuple[WeeklyItem, ...] = ()  # 未闭合信号
    stalled: tuple[WeeklyItem, ...] = ()  # 停滞项目（git 本周零提交 / 线程长期无更新且有未决跟进）
    proposals: tuple[WeeklyItem, ...] = ()  # 下周建议（提议区，E3）
    source_notes: tuple[str, ...] = ()  # 采集降级/缺失说明（可见性）

    def as_snapshot(self) -> dict[str, object]:
        return {
            "week": self.week,
            "completed": len(self.completed),
            "decisions": len(self.decisions),
            "unclosed": len(self.unclosed),
            "stalled": len(self.stalled),
            "proposals": len(self.proposals),
        }


@dataclass
class WeeklySignals:
    """采集层产出，交给去重与分区。"""

    completed: list[WeeklyItem] = field(default_factory=list)
    decisions: list[WeeklyItem] = field(default_factory=list)
    unclosed: list[WeeklyItem] = field(default_factory=list)
    stalled: list[WeeklyItem] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)


def _dedup(items: list[WeeklyItem]) -> tuple[WeeklyItem, ...]:
    """按 (text, project) 去重，保序（周复盘要求去重，PRD 3.4）。"""
    seen: set[tuple[str, str | None]] = set()
    out: list[WeeklyItem] = []
    for item in items:
        key = (item.text.strip(), item.project)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return tuple(out)


def derive_proposals(signals: WeeklySignals) -> tuple[WeeklyItem, ...]:
    """从未闭合信号与停滞项目**确定性地**推导下周建议（E3，附来源）。

    这是启发式建议，不调用模型、不改写任何项目笔记；进下周简报提议候选池（L28）时仍受
    「不得升级为事实」约束。模型化综合留作后续增强。
    """
    proposals: list[WeeklyItem] = []
    for item in signals.stalled:
        proposals.append(
            WeeklyItem(
                text=f"推进停滞项目 {item.project or item.text}",
                source_ref=item.source_ref,
                evidence=EvidenceLevel.E3,
                project=item.project,
            )
        )
    for item in signals.unclosed:
        proposals.append(
            WeeklyItem(
                text=f"清理未闭合：{item.text}",
                source_ref=item.source_ref,
                evidence=EvidenceLevel.E3,
                project=item.project,
            )
        )
    return _dedup(proposals)


def build_review(week: str, start: str, end: str, signals: WeeklySignals) -> WeeklyReview:
    """把采集信号汇总去重、分区，产出一份 :class:`WeeklyReview`。"""
    return WeeklyReview(
        week=week,
        start=start,
        end=end,
        completed=_dedup(signals.completed),
        decisions=_dedup(signals.decisions),
        unclosed=_dedup(signals.unclosed),
        stalled=_dedup(signals.stalled),
        proposals=derive_proposals(signals),
        source_notes=tuple(signals.source_notes),
    )
