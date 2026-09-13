"""融合排序、检索轨迹与「索引 → ask」端到端的测试。

重点是让**每个信号都可判定地起作用**：改变权重或删掉某个信号，排序必须随之变化
（否则那个信号就是装饰品）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

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
