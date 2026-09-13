"""融合排序、检索轨迹与「索引 → ask」端到端的测试。

重点是让**每个信号都可判定地起作用**：改变权重或删掉某个信号，排序必须随之变化
（否则那个信号就是装饰品）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import SecretStr

from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import CompletionResult, Usage
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.repositories.kb_index import KnowledgeIndex
from summit_workbench.workflows.ask.ask import answer_question
from summit_workbench.workflows.ask.fusion import RankedChunk, Weights, fuse
from summit_workbench.workflows.ask.retrieval import retrieve_via_index
from summit_workbench.workflows.ask.router import QueryKind, RoutingPlan, route_query

CFG = ModelConfig(capability="qa", model_id="m", base_url="http://x", credential_account="shared")
PROMPT = Prompt(name="qa-answer", version=2, capability="qa", body="系统提示")
QUESTION = "根据之前和 HII 的沟通，请告诉我当前我们达成的商标共识规范是什么？"


def _note(vault: Path, rel: str, body: str, **front: object) -> Path:
    meta: dict[str, object] = {
        "date": "2026-09-12",
        "type": "note",
        "status": "active",
        "workstream": "hii",
    }
    meta.update(front)
    lines = "\n".join(f"{key}: {value}" for key, value in meta.items())
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{lines}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    _note(
        root,
        "hii/notes/20260912-trademark-consensus.md",
        "# HII–HIC 商标共识规范\n\n## 登记主体\n\n"
        "登记主体统一为 Hoffman Institute International。\n\n"
        "## 逐项商标归属与状态\n\n活满归 HIC（已注册）；和夫曼之旅归 HII（正在注册）。\n\n"
        "## 关联\n\n<!-- 双链候选待确认 -->\n\n- 商标共识规范相关的原文在 hii/sources/。",
        aliases="[商标共识规范]",
        type="note",
    )
    # 证据层：原文，内容与派生笔记重叠
    _note(
        root,
        "hii/sources/20260912-hii-hic-ip-overview.md",
        "# 原文：全景总结\n\n## 商标体系与当前状态\n\n"
        "活满归 HIC（已注册）；和夫曼之旅归 HII（正在注册）。商标共识规范的原文在此。",
        type="source",
    )
    # 引用了原文的派生笔记（同源去重的对象）
    _note(
        root,
        "hii/notes/20260912-hii-registration-entity-name.md",
        "# HII 正式登记主体名称\n\n## 来源\n\n"
        "[[20260912-hii-hic-ip-overview|原文：全景总结]] "
        "登记主体统一为 Hoffman Institute International。",
        type="note",
    )
    # 会议笔记（含证据索引）→ 逐字稿：构成 笔记→会议笔记→逐字稿 的链路
    _note(
        root,
        "meetings/notes/20260907-portal-permission-alignment.md",
        "# 门户权限与网课老师绑定 2026-09-07\n\n## 一分钟摘要\n\n商标共识规范相关讨论。\n\n"
        "## 证据索引\n\n[[2026-09-07-luo-yifeng-video-meeting-2-transcript|逐字稿]]",
        type="meeting-note",
        projects="[hic-enrollment]",
    )
    _note(
        root,
        "meetings/transcripts/2026-09-07-luo-yifeng-video-meeting-2-transcript.md",
        "# 2026-09-07 逐字稿\n\n罗艺峰 00:02\n就那个首先是那门户。\n",
        type="meeting-transcript",
        status="archived",
        projects="[hic-enrollment]",
    )
    _note(
        root,
        "index/decisions.md",
        "# 决策台账\n\n## 生效中\n\n商标共识规范与登记主体口径。",
        type="index",
        project="global",
    )
    return root


def _search(
    vault: Path,
    tmp_path: Path,
    question: str = QUESTION,
    *,
    weights: Weights | None = None,
):
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as index:
        index.build()
        hits = index.search(question) or []
        return fuse(
            hits,
            index=index,
            query=question,
            plan=route_query(question),
            weights=weights,
        )


def _search_with_plan(
    vault: Path,
    tmp_path: Path,
    plan: RoutingPlan,
    question: str = QUESTION,
    weights: Weights | None = None,
):
    """用显式路由计划检索：用于把某个信号从「路由优先类型」这个独立加分项里隔离出来。"""
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as index:
        index.build()
        hits = index.search(question) or []
        return fuse(hits, index=index, query=question, plan=plan, weights=weights)


def test_index_and_source_both_reachable_and_note_outranks_source(tmp_path: Path) -> None:
    """`source` 降权 + 同源去重：派生笔记必须排在原件之前（但原件仍在召回池里）。"""
    ranked, _trace = _search(_vault(tmp_path), tmp_path)
    by_anchor = {chunk.source_id: chunk for chunk in ranked}
    note = by_anchor.get("hii/notes/20260912-hii-registration-entity-name")
    source = by_anchor.get("hii/sources/20260912-hii-hic-ip-overview")
    assert note is not None and source is not None, "原件与派生笔记都应留在召回池"
    assert note.score > source.score, "同源时派生结论应排在证据层之前"
    assert "证据层降权（source）" in source.why


def test_same_origin_dedupe_is_recorded_in_the_trace(tmp_path: Path) -> None:
    _ranked, trace = _search(_vault(tmp_path), tmp_path)
    assert any("同源去重" in reason for _anchor, reason in trace.dropped)


SOURCE = "hii/sources/20260912-hii-hic-ip-overview"


def _score(ranked: Sequence[RankedChunk], source_id: str) -> float:
    return float(next(chunk.score for chunk in ranked if chunk.source_id == source_id))


def test_source_penalty_is_a_real_penalty(tmp_path: Path) -> None:
    """变异验证：把 `source_penalty` 改成 1.0（=不降权），本用例必须变红。"""
    vault = _vault(tmp_path)
    penalised, _ = _search(vault, tmp_path, weights=Weights(source_penalty=0.5))
    plain, _ = _search(vault, tmp_path, weights=Weights(source_penalty=1.0))
    assert _score(penalised, SOURCE) < _score(plain, SOURCE)


def test_same_origin_dedupe_is_a_real_penalty(tmp_path: Path) -> None:
    """变异验证：把 `same_origin_penalty` 改成 1.0（=不去重），本用例必须变红。"""
    vault = _vault(tmp_path)
    deduped, _ = _search(vault, tmp_path, weights=Weights(same_origin_penalty=0.5))
    plain, _ = _search(vault, tmp_path, weights=Weights(same_origin_penalty=1.0))
    assert _score(deduped, SOURCE) < _score(plain, SOURCE)


def test_authority_weight_decides_whether_moc_wins(tmp_path: Path) -> None:
    """变异验证：删掉类型权威加权（或把 authority 权重清零），本用例必须变红。

    用 `authority_types` 为空的 POINT 计划，把「路由优先类型」这个独立加分项排除掉，
    于是两次运行的唯一差别就是类型权威加权本身。
    """
    plan = RoutingPlan(kind=QueryKind.POINT, reason="测试用", limit=20, hops=0)
    vault = _vault(tmp_path)
    index_note = "index/decisions"
    default_run, _ = _search_with_plan(vault, tmp_path, plan)
    zeroed, _ = _search_with_plan(vault, tmp_path, plan, weights=Weights(authority=0.0))
    assert _score(default_run, index_note) > _score(zeroed, index_note)


def test_link_expansion_reaches_transcript(tmp_path: Path) -> None:
    """`笔记 → 会议笔记 → 逐字稿` 必须能被检索轨迹走出来。"""
    _ranked, trace = _search(_vault(tmp_path), tmp_path, "IT 门户权限的来龙去脉")
    reached = {anchor for anchor, _seed in trace.expanded}
    assert any("meeting" in anchor for anchor in reached), trace.expanded


def test_trace_records_route_terms_and_exclusions(tmp_path: Path) -> None:
    _ranked, trace = _search(_vault(tmp_path), tmp_path)
    assert trace.route == "decision"
    assert trace.terms
    assert trace.fused
    assert all(chunk.why for chunk in trace.fused), "每条命中都要能解释为什么"


def test_retrieve_via_index_returns_block_level_citations(tmp_path: Path) -> None:
    candidates, trace = retrieve_via_index(
        _vault(tmp_path), "商标共识规范", index_path=tmp_path / "kb.sqlite"
    )
    assert candidates, trace.summary()
    assert all(candidate.source_id for candidate in candidates)
    assert any("#" in candidate.source_id for candidate in candidates), "应能给出区块级锚点"


class _FixedCompleter:
    """始终返回一条指向指定 source_id 的事实——用于验证越界引用会被剔除。"""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        text = json.dumps(
            {"summary": "s", "facts": [{"text": "编的", "source_id": self.source_id}]},
            ensure_ascii=False,
        )
        return CompletionResult(text=text, usage=Usage(10, 5), model_id="m", attempts=1)


class _EchoCompleter:
    """把「第三个来源」当成一条事实引用，用于验证引用链路与越界剔除。"""

    def __init__(self, pick: int = 0) -> None:
        self.pick = pick
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        self.system, self.user = system, user
        ids = re.findall(r"source_id: (.+)", user)
        text = json.dumps(
            {
                "summary": "商标共识规范如下。",
                "facts": [{"text": "f", "source_id": ids[self.pick]}],
            },
            ensure_ascii=False,
        )
        return CompletionResult(text=text, usage=Usage(10, 5), model_id="m", attempts=1)


def test_answer_question_grounds_block_citations(tmp_path: Path) -> None:
    """端到端：使用索引时，引用必须是 `路径#区块` 形式，且越界引用被剔除。"""
    completer = _EchoCompleter(pick=0)
    result = answer_question(
        _vault(tmp_path),
        QUESTION,
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        index_path=tmp_path / "kb.sqlite",
    )
    assert result.trace is not None and result.trace.route == "decision"
    assert result.answer.facts and result.dropped_sources == ()
    assert result.answer.facts[0].source_id in {c.source_id for c in result.sources}

    # 越界引用（模型自己编一个没进上下文的锚点）必须被剔除
    grounded = answer_question(
        _vault(tmp_path),
        QUESTION,
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=_FixedCompleter("hii/notes/不存在#某区块"),
        index_path=tmp_path / "kb.sqlite",
    )
    assert grounded.answer.facts == []
    assert grounded.dropped_sources == ("hii/notes/不存在#某区块",)


def test_without_index_the_legacy_path_is_used(tmp_path: Path) -> None:
    """不传 index_path 时走旧版子串召回，且不产生检索轨迹（保证向后兼容）。"""
    completer = _EchoCompleter(pick=0)
    result = answer_question(
        _vault(tmp_path), "商标共识规范", CFG, SecretStr("k"), prompt=PROMPT, completer=completer
    )
    assert result.trace is None
    assert result.sources
    assert all("#" not in candidate.source_id for candidate in result.sources)


def test_navigation_blocks_are_penalised(tmp_path: Path) -> None:
    """`## 关联` 这类脚手架区块命中时必须降权，不能被当成事实来源。

    变异验证：把 `NAV_HEADINGS` 判空，本用例必须变红。
    """
    vault = _vault(tmp_path)
    ranked, _ = _search(vault, tmp_path, "商标共识规范 关联")
    nav = [chunk for chunk in ranked if chunk.heading == "关联"]
    assert nav, "应至少命中一个导航型区块"
    assert all("导航型区块降权" in chunk.why for chunk in nav)


def test_per_note_chunk_cap_keeps_one_note_from_monopolising(tmp_path: Path) -> None:
    """单篇笔记最多贡献 3 个块；被截掉的块要在轨迹里说明原因。"""
    vault = _vault(tmp_path)
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as index:
        index.build()
        hits = index.search(QUESTION) or []
        ranked, trace = fuse(
            hits,
            index=index,
            query=QUESTION,
            plan=RoutingPlan(kind=QueryKind.POINT, reason="t", limit=30, hops=0),
            weights=Weights(max_chunks_per_note=1),
        )
    counts: dict[str, int] = {}
    for chunk in ranked:
        counts[chunk.source_id] = counts.get(chunk.source_id, 0) + 1
    assert counts and max(counts.values()) == 1
    assert any("单篇块数上限" in reason for _anchor, reason in trace.dropped)


# ---- R1 / R3 / 召回补足：2026-09-14 在真实库上踩到的两类 bug 的回归 ----


def _anchor_score(ranked: Sequence[RankedChunk], anchor: str) -> float | None:
    for chunk in ranked:
        if chunk.anchor == anchor:
            return chunk.score
    return None


def _link_vault(tmp_path: Path, *, extra_hub: bool = False) -> Path:
    """枢纽页 + 被它链接的邻居。查询用 6 字短语（FTS trigram 能命中），各块词频不同。"""
    root = tmp_path / "vault"
    body = (
        "# 枢纽\n\n## 关键结论\n\n商标共识规范 商标共识规范 商标共识规范\n\n"
        "## 关联\n\n[[d1|邻居一]]\n"
    )
    _note(root, "projects/hub.md", body, type="project-main", project="hub")
    if extra_hub:
        _note(
            root,
            "projects/hub2.md",
            "# 枢纽二\n\n## 关键结论\n\n商标共识规范 商标共识规范\n\n## 关联\n\n[[d1|邻居一]]\n",
            type="project-main",
            project="hub2",
        )
    _note(
        root,
        "decisions/d1.md",
        "# 邻居一\n\n## 决定\n\n商标共识规范 商标共识规范 商标共识规范\n\n"
        "## 理由\n\n商标共识规范\n\n## 关联\n\n[[hub|枢纽]]\n",
        type="decision",
    )
    # 第二个邻居：**不同的笔记**，正文相关度更低。旧 bug 会把 d1 与 d2 抹成同一个分数。
    _note(
        root,
        "decisions/d2.md",
        "# 邻居二\n\n## 决定\n\n商标共识规范\n\n## 关联\n\n[[hub|枢纽]]\n",
        type="decision",
    )
    _note(
        root,
        "index/global-nav.md",
        "# 全局导航\n\n## 生效中\n\n商标共识规范\n\n## 关联\n\n[[hub|枢纽]]\n",
        type="index",
        project="global",
    )
    return root


LINK_QUERY = "商标共识规范"


def test_link_bonus_is_multiplicative_not_a_replacement(tmp_path: Path) -> None:
    """回归：链接信号必须是**乘性加成**，不能覆盖邻居自己的分。

    旧实现把邻居的分整体替换成 `promoted = max(base, seed.score * ratio)`——它只由种子分决定、
    与邻居自身内容无关，于是**不同邻居**被抹成完全相同的分数、顺序退化为任意。
    2026-09-14 在真实库实测：Q1 排名 2–10 的分数全是 25.03，`## 理由` 因此压过 `## 决定`。

    做法：同一批命中分别在不扩展（hops=0）与扩展（hops=1）下跑，断言「扩展后的分 =
    扩展前的分 × 加成系数」——这一条在「覆盖式」实现下必然不成立。

    变异验证：把 `new_score = existing_score * link_factor` 换回
    `new_score = seed.score * weights.link_seed_ratio`，本用例必须变红。
    """
    vault = _link_vault(tmp_path)
    weights = Weights()
    factor = 1.0 + weights.link * weights.link_seed_ratio
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as index:
        index.build()
        hits = index.search(LINK_QUERY) or []
        plan = lambda hops: RoutingPlan(  # noqa: E731 - 两行内构造两个计划更易读
            kind=QueryKind.POINT, reason="t", limit=30, hops=hops
        )
        without, _ = fuse(hits, index=index, query=LINK_QUERY, plan=plan(0), weights=weights)
        with_link, _ = fuse(hits, index=index, query=LINK_QUERY, plan=plan(1), weights=weights)

    baseline = {chunk.anchor: chunk.score for chunk in without}
    linked = [
        chunk
        for chunk in with_link
        if any(why.startswith("双链扩展") for why in chunk.why) and chunk.anchor in baseline
    ]
    assert linked, "本 fixture 应至少有一个直接命中同时被双链扩展加成"
    for chunk in linked:
        assert chunk.score == pytest.approx(baseline[chunk.anchor] * factor), (
            f"{chunk.anchor} 的链接信号不是乘性加成（分数被覆盖了）"
        )


def test_link_expansion_is_applied_once_per_neighbour(tmp_path: Path) -> None:
    """回归：同一个邻居被多个种子链接时，链接加成只能算一次。

    旧实现按种子逐个累加，邻居可被加成 2–4 次（实测把正文相关度 0.29 的块顶到 41.05），
    链接信号彻底盖过正文相关度。

    变异验证：把应用循环改成遍历两遍（`list(best_seed.items()) * 2`），本用例必须变红。
    """
    vault = _link_vault(tmp_path, extra_hub=True)
    ranked, _ = _search(vault, tmp_path, LINK_QUERY)
    target = next((chunk for chunk in ranked if chunk.anchor == "decisions/d1#决定"), None)
    assert target is not None
    link_notes = [why for why in target.why if why.startswith("双链扩展")]
    assert len(link_notes) <= 1, f"链接加成被重复应用：{link_notes}"


def test_link_expansion_obeys_project_filter(tmp_path: Path) -> None:
    """R3：双链扩展必须重复应用与初始召回相同的 project 过滤，否则过滤结果不纯净。

    实测：按 `project=hii-affairs` 过滤后，`project: global` 的导航页仍会从双链扩展里混进来。
    """
    vault = _link_vault(tmp_path)
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as index:
        index.build()
        hits = index.search(LINK_QUERY) or []
        ranked, trace = fuse(
            hits,
            index=index,
            query=LINK_QUERY,
            plan=RoutingPlan(kind=QueryKind.POINT, reason="t", limit=30, hops=1),
            project="hub",
        )
    assert not any(chunk.source_id.startswith("index/") for chunk in ranked), (
        "project 过滤后仍混入了 global 导航页"
    )
    assert any("双链扩展" in reason for _anchor, reason in trace.dropped)


def test_recall_supplement_merges_bm25_only_candidates(tmp_path: Path) -> None:
    """召回补足：FTS 的 trigram 匹配不到两字词，命中过少时必须用 BM25 补足候选池。

    实测（2026-09-14）：Q3 这类查询在 FTS 层只命中 10 个块，候选池一被饿死，
    后面再怎么调权重都只是在几个候选里排序。
    """
    from summit_workbench.workflows.ask.retrieval import _supplement_with_bm25

    root = tmp_path / "vault"
    _note(root, "n/with-phrase.md", "# A\n\n## 区块一\n\n商标共识规范的原文。\n", type="note")
    _note(root, "n/bigram-only.md", "# B\n\n## 区块二\n\n商标 一词单独出现。\n", type="note")

    query = "商标共识规范 商标"
    with KnowledgeIndex(root, tmp_path / "kb.sqlite") as index:
        index.build()
        fts_hits = index.search(query) or []
        merged = _supplement_with_bm25(fts_hits, index, query)

    fts_anchors = {hit.anchor for hit in fts_hits}
    merged_anchors = {hit.anchor for hit in merged}
    assert "n/bigram-only#区块二" not in fts_anchors, "两字词不该被 FTS trigram 命中"
    assert "n/bigram-only#区块二" in merged_anchors, "BM25 独有命中必须被补进召回池"
    assert len(merged) > len(fts_hits)
