"""查询路由：先判问题类型，再决定检索配比。

对应使用者选定的三个优先场景（① 回溯来龙去脉 ② 决策支持 ⑤ 定期回顾）+ 两个基础形态（点查 / 综合）。

判定**不依赖模型**：默认走启发式（关键词 + 问句形态 + 时间词）。模型判定作为可选增强
（``classifier`` 回调），不可用时自动回落，因此路由永远不会因为模型故障而失效——这也让它可以被
完全确定性地测试。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from summit_workbench.repositories.kb_index import KnowledgeIndex


class QueryKind(StrEnum):
    POINT = "point"  # 点查：一个事实
    SYNTHESIS = "synthesis"  # 综合：有哪些 / 对比 / 罗列
    RETROSPECT = "retrospect"  # 回溯：来龙去脉 / 时间线
    DECISION = "decision"  # 决策支持：规范 / 共识 / 该怎么选
    REVIEW = "review"  # 定期回顾


# 关键词表：命中即加分。刻意写成「具体词」而不是泛化的问句词，便于解释与测试。
# 权重区分强弱：「有哪些 / 分别」是明确的枚举标记，而「当前 / 状态 / 进度」只是弱提示——
# 否则「目前有哪些系统，分别是什么状态」这种典型综合问题会被误判成点查。
_KEYWORDS: dict[QueryKind, dict[str, float]] = {
    QueryKind.RETROSPECT: {
        "来龙去脉": 1.0,
        "历程": 1.0,
        "经过": 1.0,
        "时间线": 1.0,
        "演化": 1.0,
        "变迁": 1.0,
        "原委": 1.0,
        "怎么走到": 1.0,
        "之前": 1.0,
        "后来": 1.0,
        "最早": 1.0,
        "历史": 1.0,
        "沿革": 1.0,
        "发展过程": 1.0,
        "前后": 1.0,
    },
    QueryKind.DECISION: {
        "决策": 1.0,
        "决定": 1.0,
        "共识": 1.0,
        "规范": 1.0,
        "标准": 1.0,
        "规则": 1.0,
        "口径": 1.0,
        "原则": 1.0,
        "该不该": 1.0,
        "该怎么做": 1.0,
        "怎么办": 1.0,
        "为什么选": 1.0,
        "选项": 1.0,
        "依据": 1.0,
    },
    QueryKind.REVIEW: {
        "回顾": 1.0,
        "复盘": 1.0,
        "总结一下": 1.0,
        "这周": 1.0,
        "本周": 1.0,
        "上周": 1.0,
        "本月": 1.0,
        "这个月": 1.0,
        "这段时间": 1.0,
        "阶段总结": 1.0,
        "周报": 1.0,
        "月报": 1.0,
    },
    QueryKind.SYNTHESIS: {
        "有哪些": 1.0,
        "都有什么": 1.0,
        "全部": 1.0,
        "分别": 1.0,
        "比较": 1.0,
        "对比": 1.0,
        "罗列": 1.0,
        "汇总": 1.0,
        "清单": 1.0,
        "一览": 1.0,
        "几个": 0.5,
    },
    QueryKind.POINT: {
        "是什么": 1.0,
        "是多少": 1.0,
        "多少人": 1.0,
        "谁": 1.0,
        "什么时候": 1.0,
        "在哪": 1.0,
        "哪里": 1.0,
        "当前": 0.5,
        "现在": 0.5,
        "进度": 0.5,
        "状态": 0.5,
        "多少": 0.5,
    },
}
_TIME_RE = re.compile(r"\d{4}[-/年]\d{1,2}|前\d+个?月|去?年|上个?月|本季度|Q[1-4]")


@dataclass(frozen=True)
class RoutingPlan:
    """一类问题的检索配比。"""

    kind: QueryKind
    reason: str
    limit: int
    hops: int
    authority_types: tuple[str, ...] = ()
    time_desc: bool = False
    exclude_types: tuple[str, ...] = field(
        default=("qa-insight", "meeting-transcript", "approval-page")
    )


_PLANS: dict[QueryKind, RoutingPlan] = {
    QueryKind.POINT: RoutingPlan(
        # 点查也走 1 跳：问题常常只点名了「工作线/项目」，真正的答案在它链接的那篇笔记里
        kind=QueryKind.POINT,
        reason="点查：找最相关的那一块，并允许顺 1 跳双链取具体笔记",
        limit=16,
        hops=1,
    ),
    QueryKind.SYNTHESIS: RoutingPlan(
        kind=QueryKind.SYNTHESIS, reason="综合：铺开召回并做双链扩展", limit=14, hops=1
    ),
    QueryKind.RETROSPECT: RoutingPlan(
        kind=QueryKind.RETROSPECT,
        reason="回溯：按时间聚合，走 2 跳双链以打通 笔记→会议笔记→逐字稿",
        limit=16,
        hops=2,
        authority_types=("workstream", "decision", "note", "meeting-note"),
        time_desc=True,
    ),
    QueryKind.DECISION: RoutingPlan(
        kind=QueryKind.DECISION,
        reason="决策支持：优先历史决策与线索主页",
        limit=12,
        hops=1,
        authority_types=("decision", "index", "workstream"),
    ),
    QueryKind.REVIEW: RoutingPlan(
        kind=QueryKind.REVIEW,
        reason="定期回顾：优先复盘、索引与线索主页，按时间倒序",
        limit=16,
        hops=1,
        authority_types=("weekly-review", "index", "workstream"),
        time_desc=True,
    ),
}


def heuristic_route(query: str) -> tuple[QueryKind, str]:
    """启发式判定问题类型，返回 ``(类型, 判定理由)``。"""
    lowered = query.casefold()
    scores: dict[QueryKind, float] = {kind: 0.0 for kind in _KEYWORDS}
    hits_by_kind: dict[QueryKind, list[str]] = {kind: [] for kind in _KEYWORDS}
    for kind, keywords in _KEYWORDS.items():
        for keyword, weight in keywords.items():
            if keyword.casefold() in lowered:
                scores[kind] += weight
                hits_by_kind[kind].append(keyword)
    if _TIME_RE.search(query):
        scores[QueryKind.RETROSPECT] += 1.0
        hits_by_kind[QueryKind.RETROSPECT].append("时间词")

    best = max(scores, key=lambda kind: (scores[kind], -_ORDER.index(kind)))
    hits = hits_by_kind[best]
    if not hits:
        # 无关键词：疑问句且很短 → 点查；否则按综合处理（宁可多召回）
        kind = QueryKind.POINT if len(query) <= 20 else QueryKind.SYNTHESIS
        return kind, "无关键词：按长度兜底"
    return best, "命中关键词 " + "、".join(hits[:4])


# 同分时的优先级（越靠前越优先）：点查 > 决策 > 回溯 > 回顾 > 综合
_ORDER = (
    QueryKind.POINT,
    QueryKind.DECISION,
    QueryKind.RETROSPECT,
    QueryKind.REVIEW,
    QueryKind.SYNTHESIS,
)


def route_query(
    query: str, *, classifier: Callable[[str], QueryKind | None] | None = None
) -> RoutingPlan:
    """返回检索配比。``classifier`` 可选（模型判定），失败或返回 None 时回落启发式。"""
    if classifier is not None:
        try:
            kind = classifier(query)
        except Exception:  # noqa: BLE001 - 路由绝不能因模型故障而失败
            kind = None
        if isinstance(kind, QueryKind):
            return replace(_PLANS[kind], reason=f"模型判定：{kind.value}")
    kind, reason = heuristic_route(query)
    return replace(_PLANS[kind], reason=reason)


def query_mentions(query: str, index: KnowledgeIndex) -> set[str]:
    """查询里点名了哪些笔记的 ``aliases`` / 标题（用于元数据命中加权）。"""
    lowered = query.casefold()
    mentioned: set[str] = set()
    for source_id, info in index.notes().items():
        candidates = (info.title, *info.aliases)
        if any(candidate and candidate.casefold() in lowered for candidate in candidates):
            mentioned.add(source_id)
    return mentioned
