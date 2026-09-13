"""多信号融合：把块级命中、元数据、权威度、双链与时间合成一个可解释的排序。

信号（权重可配、可测）：

1. **正文/标题命中**（FTS5 BM25 或纯 Python BM25，标题与区块标题分权）
2. **元数据过滤与命中**（workstream / project / type / status / date / people / org / tags，
   以及查询里点名了某篇笔记的 title/aliases）
3. **索引 / MOC 与类型权威加权**（`index`、线索主页、`decision` 高于散记）
4. **双链扩展 1–2 跳**（出链 + 入链，`aliases` 可解析）——也是「笔记→会议笔记→逐字稿」走通的机制
5. **时间加权**（越新越靠前）
6. **去重**（同块只留一次；**同源去重**：`source` 原件与其派生笔记同时命中时优先派生笔记）

每条结果都带 `why`（为什么命中），直接进「检索轨迹」，让使用者能核对排序依据。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date

from summit_workbench.repositories.kb_index import Hit, KnowledgeIndex, NoteMeta
from summit_workbench.workflows.ask.router import RoutingPlan, query_mentions
from summit_workbench.workflows.ask.terms import query_terms


@dataclass(frozen=True)
class Weights:
    """融合权重。默认值是产品口径；测试通过替换它来验证「哪个信号真的在起作用」。"""

    body: float = 1.0
    heading: float = 1.2
    title: float = 1.6
    authority: float = 1.4
    recency: float = 0.6
    link: float = 0.5
    # 双链扩展的「种子继承」比例：顺着最相关的那篇走一跳得到的笔记，
    # 应当继承种子分数的一部分——否则扩展只是装饰，排在所有直接命中之后
    link_seed_ratio: float = 0.6
    meta: float = 0.9
    # `source` 是证据层而不是结论层：降权但**保留在召回池**（使用者 2026-09-13 的选择）
    source_penalty: float = 0.55
    # 同源去重：同源的派生笔记命中时，原件命中按此系数再降权
    same_origin_penalty: float = 0.35
    # 导航型区块（`## 关联` / `## 维护规则` / `## 证据索引`）只是脚手架，
    # 命中了也不该被当成事实引用（实测会被模型写成「事实」）
    nav_block_penalty: float = 0.4
    # 结论型区块（`## 关键结论` / `## 决定` / `## 选项` / `## 一句话回答…`）：命中即加权。
    # 2026-09-14 实测：不加权时同一篇里 `## 理由` / `## 影响` / `## 背景` 会压过
    # `## 决定` / `## 选项`
    # （支持型段落的正文命中分本来就高，乘子小了跨不过去），块级命中率只有 25%。
    conclusion_boost: float = 2.8
    # 支持型区块（`## 背景` / `## 理由` / `## 影响` / `## 证据`）：是答案的上下文，不是答案本身。
    # 只轻降权——「为什么这么做」这类问题仍需要 `## 理由`。
    support_penalty: float = 0.8
    # 笔记引言块（heading 为空 = 文首标题+引言那段）：它是「这篇讲什么」，不是答案，降权。
    preamble_penalty: float = 0.45
    # 单篇笔记最多贡献几个块进上下文：防止一篇长文独占预算
    max_chunks_per_note: int = 3


# 支持型区块标题：答案的上下文（降权但不排除）
SUPPORT_HEADINGS = frozenset({"背景", "理由", "影响", "证据", "要点"})


# 结论型区块的标题前缀（区块标题常带后缀，如 `决定：「活满」与…`，故用前缀匹配）。
CONCLUSION_HEADING_PREFIXES: tuple[str, ...] = (
    "关键结论",
    "决定",
    "选项",
    "一句话回答",
    "结论",
    "现在在哪",
    "未决问题",
    "下一步",
    "阻塞",
    "已形成决策",
    "事实与进展",
    "明确行动项",
)

# 只承担导航/脚手架作用的区块标题：命中即降权
# （它们几乎总会因为「原文/关联/索引」这类词而命中，且不该被当成事实引用）。
NAV_HEADINGS = frozenset(
    {
        "关联",
        "维护规则",
        "证据索引",
        "主题簇",
        "决策记录",
        "时间线",
        "来源",
        "规范",
        "列表",
        "索引",
        "摘要",
        # README / SOP / people 等导航页的区块
        "怎么用",
        "目录速览",
        "三条铁律",
        "一图流",
        "人物",
        "组织",
        "生效中",
        "待复核",
        "已被替代",
    }
)

# 类型权威度：项目入口页与决策最高（它们是被蒸馏过的答案），索引页只是导航，证据/流水最低。
TYPE_AUTHORITY: dict[str, float] = {
    "project-main": 0.95,
    "decision": 0.95,
    "workstream": 0.9,
    # 索引页是**导航**不是内容：早先给 1.0 会让 `index/people`、`README#怎么用` 挤掉答案块
    "index": 0.45,
    "note": 0.7,
    "meeting-note": 0.7,
    "weekly-review": 0.6,
    "thread-doc": 0.55,
    "long-form-thought": 0.5,
    "work-log": 0.45,
    "source": 0.4,
    "meeting-transcript": 0.3,
    "daily": 0.3,
    "project-inbox": 0.3,
    "qa-insight": 0.2,
}


def _block_role(heading: str) -> str:
    """块的语义角色：``conclusion`` / ``nav`` / ``preamble`` / ``plain``。

    R1 的核心：把「同一篇笔记里哪个块更可能是答案」变成可测的加权信号。
    空 heading 是「笔记引言块」（文首标题 + 引言），只是「这篇讲什么」，不是答案。
    """
    if not heading:
        return "preamble"
    if heading in NAV_HEADINGS:
        return "nav"
    if heading in SUPPORT_HEADINGS:
        return "support"
    if heading.startswith(CONCLUSION_HEADING_PREFIXES):
        return "conclusion"
    return "plain"


@dataclass(frozen=True)
class RankedChunk:
    """融合后的一条结果（可直接作为候选进入问答上下文或来源面板）。"""

    anchor: str
    source_id: str
    heading: str
    text: str
    score: float
    note_type: str
    title: str
    why: tuple[str, ...] = ()
    via_link: str | None = None  # 来自双链扩展时，记录从哪篇扩展过来


@dataclass
class Trace:
    """检索轨迹：命中了哪些块、走了哪些双链、排除了什么、为什么。"""

    route: str
    route_reason: str
    terms: tuple[str, ...]
    hits: int = 0
    fused: tuple[RankedChunk, ...] = ()
    dropped: tuple[tuple[str, str], ...] = field(default=())  # (anchor, 原因)
    expanded: tuple[tuple[str, str], ...] = field(default=())  # (anchor, 来源)
    # 索引层不可用而退回纯 Markdown 扫描时，写明原因——否则使用者会以为这就是块级检索的结果
    degraded: str = ""

    def summary(self) -> str:
        terms = "、".join(self.terms) or "—"
        lines = [f"路由：{self.route}（{self.route_reason}）", f"检索词：{terms}"]
        if self.degraded:
            lines.append(f"⚠ 索引不可用，已降级：{self.degraded}")
        if self.expanded:
            lines.append("双链扩展：" + "；".join(f"{a} ← {b}" for a, b in self.expanded))
        if self.dropped:
            lines.append("已排除：" + "；".join(f"{a}（{r}）" for a, r in self.dropped))
        return "\n".join(lines)


_YEAR_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _note_date(info: NoteMeta) -> date | None:
    for raw in (info.updated, info.date):
        match = _YEAR_RE.match(raw or "")
        if match:
            try:
                return date(*(int(part) for part in match.groups()))
            except ValueError:
                return None
    return None


def _recency(info: NoteMeta, *, today: date | None) -> float:
    """0–1 的新近度：今天为 1，超过 2 年衰减到 0。"""
    stamp = _note_date(info)
    if stamp is None:
        return 0.0
    days = max(0, ((today or date.today()) - stamp).days)
    return max(0.0, 1.0 - days / 730)


def _term_hits(terms: list[str], text: str) -> int:
    lowered = text.casefold()
    return sum(1 for term in terms if term.casefold() in lowered)


def fuse(
    hits: list[Hit],
    *,
    index: KnowledgeIndex,
    query: str,
    plan: RoutingPlan,
    weights: Weights | None = None,
    today: date | None = None,
    project: str | None = None,
    workstream: str | None = None,
) -> tuple[list[RankedChunk], Trace]:
    """融合排序。返回 ``(排序后的结果, 检索轨迹)``。"""
    weights = weights or Weights()
    notes = index.notes()
    aliases = index.aliases()
    terms = query_terms(query)
    mentioned = query_mentions(query, index)

    scored: list[tuple[float, RankedChunk]] = []
    dropped: list[tuple[str, str]] = []
    best_by_anchor: dict[str, RankedChunk] = {}

    for hit in hits:
        info = notes.get(hit.source_id)
        if info is None:
            dropped.append((hit.anchor, "笔记已不在索引中"))
            continue
        if info.type in plan.exclude_types:
            dropped.append((hit.anchor, f"类型 {info.type} 不进初始召回"))
            continue
        if project and project not in info.projects:
            dropped.append((hit.anchor, f"项目过滤：不属于 {project}"))
            continue
        if workstream and info.workstream != workstream:
            dropped.append((hit.anchor, f"工作线过滤：不属于 {workstream}"))
            continue

        why: list[str] = []
        score = weights.body * max(0.0, hit.score)
        if hit.score:
            why.append(f"正文命中（{hit.score:.2f}）")

        heading_hits = _term_hits(terms, hit.heading)
        if heading_hits:
            score += weights.heading * heading_hits
            why.append(f"区块标题命中 {heading_hits}")
        title_hits = _term_hits(terms, info.title)
        if title_hits:
            score += weights.title * title_hits
            why.append(f"标题命中 {title_hits}")

        authority = TYPE_AUTHORITY.get(info.type, 0.4)
        score += weights.authority * authority
        why.append(f"类型权威 {info.type or '—'}={authority:.2f}")
        if plan.authority_types and info.type in plan.authority_types:
            score += weights.authority * 0.5
            why.append("路由优先类型")

        if info.source_id in mentioned:
            score += weights.meta * 2
            why.append("查询点名了这篇笔记")
        meta_blob = " ".join((*info.projects, *info.people, *info.org, *info.tags))
        meta_hits = _term_hits(terms, meta_blob)
        if meta_hits:
            score += weights.meta * meta_hits
            why.append(f"元数据命中 {meta_hits}")

        newness = _recency(info, today=today)
        if plan.time_desc:
            score += weights.recency * 2 * newness
            why.append(f"时间倒序加权 {newness:.2f}")
        else:
            score += weights.recency * newness

        if info.type == "source":
            score *= weights.source_penalty
            why.append("证据层降权（source）")
        role = _block_role(hit.heading)
        if role == "conclusion":
            score *= weights.conclusion_boost
            why.append("结论型区块加权")
        elif role == "support":
            score *= weights.support_penalty
            why.append("支持型区块降权")
        elif role == "preamble":
            score *= weights.preamble_penalty
            why.append("笔记引言块降权")
        elif role == "nav":
            score *= weights.nav_block_penalty
            why.append("导航型区块降权")

        candidate = RankedChunk(
            anchor=hit.anchor,
            source_id=hit.source_id,
            heading=hit.heading,
            text=hit.text,
            score=score,
            note_type=info.type,
            title=info.title,
            why=tuple(why),
        )
        current = best_by_anchor.get(hit.anchor)
        if current is None or candidate.score > current.score:
            best_by_anchor[hit.anchor] = candidate

    scored = [(chunk.score, chunk) for chunk in best_by_anchor.values()]

    # ---- 双链扩展：把 top 命中相邻的笔记（含会议笔记与逐字稿）带进轨迹 ----
    # 关键点：目标可能**同时**是弱的直接命中。此时必须取「直接命中分」与「种子继承分」的较大者——
    # 否则一个低分的直接命中会把「线索主页链接了它」这个强信号挡掉。
    # （2026-09-13 实测踩到：分月 Roadmap 明明被线索主页链接，却排在 16 名之外。）
    expanded: list[tuple[str, str]] = []
    if plan.hops > 0:
        position = {chunk.source_id: i for i, (_, chunk) in enumerate(scored)}
        seeds = [chunk for _, chunk in sorted(scored, key=lambda item: -item[0])[:5]]
        # `[[文件#区块]]` 形式的出链要定位到**那一块**，而不是目标笔记的首块
        # （C-lite 粒度下一节就是一个结论，定位错了等于引错结论）。
        hints: dict[str, str] = {}
        for seed in seeds:
            for target, heading in index.anchor_hints(seed.source_id).items():
                hints.setdefault(target, heading)
        # 邻居 → 最强种子（避免同一邻居被多个种子重复加成）
        best_seed: dict[str, RankedChunk] = {}
        for seed in seeds:
            if seed.note_type == "source":
                continue
            for neighbour in sorted(index.neighbours(seed.source_id, hops=plan.hops)):
                info = notes.get(neighbour)
                if info is None:
                    continue
                # R3：双链扩展必须重复应用与初始召回**相同**的过滤，否则按项目过滤得不到
                # 纯净视图（实测：过滤后仍混进 `project: global` 的导航页）。
                if project and project not in info.projects:
                    dropped.append((neighbour, f"项目过滤（双链扩展）：不属于 {project}"))
                    continue
                if workstream and info.workstream != workstream:
                    dropped.append((neighbour, f"工作线过滤（双链扩展）：不属于 {workstream}"))
                    continue
                # 每个邻居只记**最强**的那个种子，后面只应用一次加成。
                # 2026-09-14 实测：按种子逐个累加会让同一个邻居被加成 2–4 次
                # （`## 选项` 正文相关度 0.29，却被顶到 41.05），链接信号彻底盖过正文相关度。
                strongest = best_seed.get(neighbour)
                if strongest is None or seed.score > strongest.score:
                    best_seed[neighbour] = seed

        # 链接信号是**小的乘性加成**，而且永远不能盖过正文相关度：
        # 「A 链接了 B」只说明 B 值得看一眼，不说明 B 就是答案（答案由正文命中与区块角色决定）。
        link_factor = 1.0 + weights.link * weights.link_seed_ratio
        for neighbour, seed in sorted(best_seed.items()):
            info = notes.get(neighbour)
            if info is None:  # pragma: no cover - best_seed 来自同一 notes 表
                continue
            previous = position.get(neighbour)
            if previous is not None:
                existing_score, existing = scored[previous]
                new_score = existing_score * link_factor
                scored[previous] = (
                    new_score,
                    replace(
                        existing,
                        score=new_score,
                        why=(*existing.why, f"双链扩展（来自 {seed.source_id}）"),
                        via_link=seed.source_id,
                    ),
                )
            else:
                # 纯链接邻居（正文完全没命中）：只给很小的基础分，
                # 并用 `[[文件#区块]]` 提示定位到具体块。
                hinted = index.chunk_at(neighbour, hints.get(neighbour, ""))
                chunk = hinted or index.representative_chunk(neighbour)
                if chunk is None:
                    continue
                base = weights.link * TYPE_AUTHORITY.get(info.type, 0.3) + weights.authority * 0.2
                if info.type == "source":
                    base *= weights.source_penalty
                position[neighbour] = len(scored)
                scored.append(
                    (
                        base,
                        RankedChunk(
                            anchor=chunk.anchor,
                            source_id=chunk.source_id,
                            heading=chunk.heading,
                            text=chunk.text,
                            score=base,
                            note_type=info.type,
                            title=info.title,
                            why=("双链扩展", f"来自 {seed.source_id}"),
                            via_link=seed.source_id,
                        ),
                    )
                )
            expanded.append((neighbour, seed.source_id))

    scored.sort(key=lambda item: (-item[0], item[1].anchor))
    ranked = _dedupe_same_origin(
        [chunk for _, chunk in scored], _derivatives(index, notes, aliases), weights, dropped
    )
    ranked = _cap_per_note(ranked, weights.max_chunks_per_note, dropped)
    trace = Trace(
        route=plan.kind.value,
        route_reason=plan.reason,
        terms=tuple(terms),
        hits=len(hits),
        fused=tuple(ranked[: plan.limit]),
        dropped=tuple(dropped[:12]),
        expanded=tuple(expanded[:12]),
    )
    return ranked[: plan.limit], trace


def _derivatives(
    index: KnowledgeIndex, notes: dict[str, NoteMeta], aliases: dict[str, str]
) -> dict[str, list[str]]:
    """``source_id`` → 引用它的派生笔记列表（用于同源去重）。"""
    mapping: dict[str, list[str]] = {}
    for source_id, info in notes.items():
        if info.type == "source":
            continue
        for link in info.links:
            resolved = index.resolve_link(link, aliases=aliases)
            if resolved and notes.get(resolved) is not None and notes[resolved].type == "source":
                mapping.setdefault(resolved, []).append(source_id)
    return mapping


def _dedupe_same_origin(
    ranked: list[RankedChunk],
    derivatives: dict[str, list[str]],
    weights: Weights,
    dropped: list[tuple[str, str]],
) -> list[RankedChunk]:
    """同源去重：`source` 原件与引用它的派生笔记同时命中时，优先派生笔记。

    原件**不会消失**（仍在召回池里，只是排序在派生笔记之后），符合使用者「降权保留」的选择；
    被压到后面的那条会在轨迹里记一句原因。
    """
    if not derivatives:
        return ranked
    present = {chunk.source_id for chunk in ranked}
    out: list[RankedChunk] = []
    for chunk in ranked:
        derived = [note for note in derivatives.get(chunk.source_id, []) if note in present]
        if chunk.note_type == "source" and derived:
            out.append(
                replace(
                    chunk,
                    score=chunk.score * weights.same_origin_penalty,
                    why=(*chunk.why, f"同源去重：已有派生笔记命中（{derived[0]}）"),
                )
            )
            dropped.append((chunk.anchor, "同源去重（派生笔记优先，原件降权保留）"))
            continue
        out.append(chunk)
    out.sort(key=lambda item: (-item.score, item.anchor))
    return out


def _cap_per_note(
    ranked: list[RankedChunk], limit: int, dropped: list[tuple[str, str]]
) -> list[RankedChunk]:
    """单篇笔记最多贡献 ``limit`` 个块：块级引用要精确，但不该让一篇长文独占上下文。"""
    if limit <= 0:
        return ranked
    counts: dict[str, int] = {}
    out: list[RankedChunk] = []
    for chunk in ranked:
        used = counts.get(chunk.source_id, 0)
        if used >= limit:
            dropped.append((chunk.anchor, f"单篇块数上限（{limit}）"))
            continue
        counts[chunk.source_id] = used + 1
        out.append(chunk)
    return out
