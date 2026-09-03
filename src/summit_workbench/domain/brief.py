"""晨间简报的纯领域模型与规则（PRD M2 / 环 A / L12 / L26 / L28）。

这里**不做任何 IO、不认识任何供应商、不调用模型**，只定义：

- 证据三级 :class:`EvidenceLevel`（L26）：E1 已完成、E2 正在推进、E3 待确认；
- 行动分类 :class:`ActionCategory` 与混合配额（L12：主线推进 2 + 近期承诺 2 + 防止停摆 1，
  上限 5，无对应信号动态补位）；
- :func:`select_actions` 按排序结果与配额挑选行动；
- :func:`fallback_ranking` 排序模型不可用时的确定性回退；
- :func:`evaluate_health` 首行健康度；
- :class:`Brief` 聚合一份简报的全部区块（事实 / 行动 / 提议 / 最近完成）。

硬约束：事实区（会议 / 任务 / git / inbox）由采集层原文直取，不进本模块的「排序 / 建议」路径；
本模块只对**已采集**的候选排序与配额，绝不新增条目或升级证据等级（模型同样受此约束，见排序层）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

MAX_ACTIONS = 5  # G2：简报「需要行动」条目上限


class EvidenceLevel(StrEnum):
    """工作事实证据等级（L26）。数值越小越「硬」。"""

    E1 = "E1"  # 已完成：机器可验证的闭合信号
    E2 = "E2"  # 正在推进：新 commit / 未提交改动 / 主笔记状态更新
    E3 = "E3"  # 待确认：模型/启发式推断，无 E1/E2 证据

    @property
    def rank(self) -> int:
        return {"E1": 0, "E2": 1, "E3": 2}[self.value]


class ActionCategory(StrEnum):
    """行动分类与其配额语义（L12）。"""

    MAIN_PUSH = "main-push"  # 主线推进
    COMMITMENT = "commitment"  # 近期承诺（多为带截止日期的飞书任务）
    ANTI_STALL = "anti-stall"  # 防止停摆（长期停滞 / dirty 未提交 / inbox 积压）
    PROPOSAL = "proposal"  # 提议（E3，模型/周复盘建议；不占主配额，另区展示）


# 分类的中文展示标签（单一事实源；排序层与渲染层共用）。
CATEGORY_LABELS: dict[ActionCategory, str] = {
    ActionCategory.MAIN_PUSH: "主线推进",
    ActionCategory.COMMITMENT: "近期承诺",
    ActionCategory.ANTI_STALL: "防止停摆",
    ActionCategory.PROPOSAL: "提议",
}


# 默认混合配额（L12）。提议不在此表：它进提议区，不占行动区主配额。
DEFAULT_QUOTA: dict[ActionCategory, int] = {
    ActionCategory.MAIN_PUSH: 2,
    ActionCategory.COMMITMENT: 2,
    ActionCategory.ANTI_STALL: 1,
}

# 回退排序时的分类优先级（越小越靠前）。
_CATEGORY_ORDER: dict[ActionCategory, int] = {
    ActionCategory.COMMITMENT: 0,  # 有截止的承诺最不能丢
    ActionCategory.MAIN_PUSH: 1,
    ActionCategory.ANTI_STALL: 2,
    ActionCategory.PROPOSAL: 3,
}

_FAR_FUTURE = "9999-12-31"  # 无截止日期的排序哨兵


@dataclass(frozen=True)
class ActionSignal:
    """一条候选行动。``source_ref`` 是可核查依据（文件路径 / git 引用 / 任务 URL）。"""

    signal_id: str
    title: str
    category: ActionCategory
    evidence: EvidenceLevel
    source_ref: str
    project: str | None = None
    due_date: str | None = None  # ISO YYYY-MM-DD；无则 None
    detail: str = ""


@dataclass(frozen=True)
class MeetingFact:
    """今日会议事实（飞书日历原文直取）。"""

    title: str
    start_time: str  # 原始时间字符串，不做人类改写
    source_ref: str = "feishu-calendar"


@dataclass(frozen=True)
class TaskFact:
    """待办任务事实（飞书任务原文直取）。

    ``task_id`` 为飞书任务 guid（与行动候选 ``source_ref`` 里的 ``feishu-task:{guid}``
    同源），供 Web 层把「需要行动」精确合并回任务行（清单合一），避免靠标题猜测。
    """

    summary: str
    due_date: str | None
    source_ref: str = "feishu-task"
    task_id: str | None = None


@dataclass(frozen=True)
class CompletionItem:
    """最近完成条目（E1，机器可验证）。"""

    text: str
    source_ref: str
    evidence: EvidenceLevel = EvidenceLevel.E1


@dataclass(frozen=True)
class HealthState:
    """简报首行健康度。``level`` ∈ {ok, degraded, alert}。"""

    level: str
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.level == "ok"

    def line(self) -> str:
        icon = {"ok": "🟢", "degraded": "🟡", "alert": "🔴"}.get(self.level, "⚪️")
        label = {"ok": "正常", "degraded": "降级", "alert": "告警"}.get(self.level, self.level)
        suffix = f"：{'；'.join(self.reasons)}" if self.reasons else ""
        return f"{icon} 健康度 {label}{suffix}"


def evaluate_health(
    *,
    signal_count: int,
    ranking_degraded: bool,
    source_failures: tuple[str, ...],
) -> HealthState:
    """单日健康度评估。

    - 任一采集源失败（如飞书日历不可用）→ degraded，并列出失败源（A-6「系统快失效时主动告知」）。
    - 排序模型降级到确定性回退 → degraded（对齐「失败必须可见」）。
    - 当日零信号 → degraded（跨日「连续 7 天零信号」的 alert 判定依赖快照历史，随 launchd 补齐）。
    - 否则 ok。
    """
    reasons: list[str] = []
    if source_failures:
        reasons.append("采集源失败：" + "、".join(source_failures))
    if ranking_degraded:
        reasons.append("排序降级（确定性回退）")
    if signal_count == 0:
        reasons.append("当日无任何会议/任务/项目变更信号")
    level = "degraded" if reasons else "ok"
    return HealthState(level=level, reasons=tuple(reasons))


def fallback_ranking(candidates: list[ActionSignal]) -> list[str]:
    """确定性回退排序：截止日期升序 → 分类优先级 → 证据等级 → signal_id。

    排序模型不可用或返回非法 JSON 时使用；结果稳定可复现（同输入同输出）。
    返回 signal_id 的有序列表。
    """

    def key(sig: ActionSignal) -> tuple[str, int, int, str]:
        return (
            sig.due_date or _FAR_FUTURE,
            _CATEGORY_ORDER.get(sig.category, 99),
            sig.evidence.rank,
            sig.signal_id,
        )

    return [sig.signal_id for sig in sorted(candidates, key=key)]


def select_actions(
    candidates: list[ActionSignal],
    order: list[str],
    *,
    quota: dict[ActionCategory, int] | None = None,
    limit: int = MAX_ACTIONS,
) -> list[ActionSignal]:
    """按排序结果 + 混合配额挑选行动（≤ ``limit``，无对应信号动态补位）。

    - ``order``：signal_id 的目标顺序（模型排序数组或 :func:`fallback_ranking`）。
      不在 ``candidates`` 中的 id 忽略；``candidates`` 中未被 ``order`` 覆盖的按其后稳定补齐。
    - 先按配额分配每类名额（主线 2 / 承诺 2 / 防停 1）；
    - 未占满 ``limit`` 时，用剩余最高排位候选**动态补位**（不分类），凑到 ``limit`` 为止；
    - 提议（PROPOSAL）不参与行动区配额，由调用方另置提议区。
    """
    active_quota = dict(quota or DEFAULT_QUOTA)
    by_id = {sig.signal_id: sig for sig in candidates}

    # 依 order 建立稳定的处理序列：先 order 中存在的，再补 candidates 中遗漏的。
    ordered_ids = [sid for sid in order if sid in by_id]
    ordered_ids += [sig.signal_id for sig in candidates if sig.signal_id not in set(order)]

    chosen: list[ActionSignal] = []
    chosen_ids: set[str] = set()

    # 第一轮：按配额分配（提议不占配额）。
    remaining = dict(active_quota)
    for sid in ordered_ids:
        if len(chosen) >= limit:
            break
        sig = by_id[sid]
        if sig.category is ActionCategory.PROPOSAL:
            continue
        if remaining.get(sig.category, 0) > 0:
            chosen.append(sig)
            chosen_ids.add(sid)
            remaining[sig.category] -= 1

    # 第二轮：动态补位，凑满 limit（仍排除提议）。
    for sid in ordered_ids:
        if len(chosen) >= limit:
            break
        if sid in chosen_ids:
            continue
        sig = by_id[sid]
        if sig.category is ActionCategory.PROPOSAL:
            continue
        chosen.append(sig)
        chosen_ids.add(sid)

    return chosen


@dataclass(frozen=True)
class Brief:
    """一份晨间简报的完整内容（渲染层据此产出 Markdown）。"""

    date: str  # ISO YYYY-MM-DD
    health: HealthState
    meetings: tuple[MeetingFact, ...] = ()
    tasks: tuple[TaskFact, ...] = ()
    actions: tuple[ActionSignal, ...] = ()
    proposals: tuple[ActionSignal, ...] = ()
    completions: tuple[CompletionItem, ...] = ()
    pending_review_count: int = 0  # 待确认会议积压（M1-5 数字同步进简报，L43）
    ranking_model: str | None = None  # 实际参与排序的模型 ID；回退时为 None

    def as_snapshot(self) -> dict[str, object]:
        """信号快照的可序列化视图（供北极星指标基线与幂等核对）。

        **附加演进**：既有计数键（``meetings`` / ``tasks`` / ``completions`` /
        ``proposals`` 为 id 列表）保持不变；Web 工作台需要完整明细，故另附
        ``*_list`` 与行动条目的 ``title``/``due_date``/``detail`` 等字段。
        老读者忽略新键即可；新读者读到缺键的旧快照时按「无结构化明细」降级。
        """
        action_items = [
            {
                "signal_id": a.signal_id,
                "title": a.title,
                "category": a.category.value,
                "evidence": a.evidence.value,
                "source_ref": a.source_ref,
                "project": a.project,
                "due_date": a.due_date,
                "detail": a.detail,
            }
            for a in self.actions
        ]
        return {
            "date": self.date,
            "health": self.health.level,
            "health_reasons": list(self.health.reasons),
            "meetings": len(self.meetings),
            "tasks": len(self.tasks),
            "actions": action_items,
            "proposals": [a.signal_id for a in self.proposals],
            "completions": len(self.completions),
            "pending_review": self.pending_review_count,
            "ranking_model": self.ranking_model,
            # —— Web 工作台结构化明细（附加键）——
            "meeting_list": [{"title": m.title, "start_time": m.start_time} for m in self.meetings],
            "task_list": [
                {
                    "summary": t.summary,
                    "due_date": t.due_date,
                    "task_id": t.task_id,
                }
                for t in self.tasks
            ],
            "proposal_list": [
                {
                    "signal_id": p.signal_id,
                    "title": p.title,
                    "category": p.category.value,
                    "evidence": p.evidence.value,
                    "source_ref": p.source_ref,
                    "project": p.project,
                    "due_date": p.due_date,
                    "detail": p.detail,
                }
                for p in self.proposals
            ],
            "completion_list": [
                {"text": c.text, "source_ref": c.source_ref} for c in self.completions
            ],
        }


@dataclass
class CollectedSignals:
    """采集层的产出汇总（供编排层排序 + 渲染）。逐源隔离后在此聚合。"""

    meetings: list[MeetingFact] = field(default_factory=list)
    tasks: list[TaskFact] = field(default_factory=list)
    candidates: list[ActionSignal] = field(default_factory=list)
    proposals: list[ActionSignal] = field(default_factory=list)
    completions: list[CompletionItem] = field(default_factory=list)
    source_failures: list[str] = field(default_factory=list)
    pending_review_count: int = 0

    @property
    def signal_count(self) -> int:
        """当日「有无实质信号」的度量（健康度用）。"""
        return len(self.meetings) + len(self.tasks) + len(self.candidates) + len(self.completions)
