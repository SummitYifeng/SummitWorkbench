"""块级切分、检索词提取与查询路由的单元测试。"""

from __future__ import annotations

from summit_workbench.workflows.ask.chunking import chunk_markdown
from summit_workbench.workflows.ask.router import QueryKind, heuristic_route, route_query
from summit_workbench.workflows.ask.terms import fts_query, query_terms, short_terms

BODY = """# 标题

前言段落。

## 第一个区块

内容一。

## 第二个区块

内容二。

```
## 代码里的井号不是标题
```

## 第一个区块

重复标题的内容。

### 三级标题不算块边界
"""


def test_chunks_split_on_level_two_headings() -> None:
    chunks = chunk_markdown("hii/notes/foo", BODY)
    headings = [chunk.heading for chunk in chunks]
    assert headings == ["", "第一个区块", "第二个区块", "第一个区块 2"]


def test_preamble_anchor_is_the_note_itself() -> None:
    chunks = chunk_markdown("hii/notes/foo", BODY)
    assert chunks[0].anchor == "hii/notes/foo"
    assert chunks[1].anchor == "hii/notes/foo#第一个区块"


def test_fenced_code_block_does_not_split() -> None:
    """围栏里的 `##` 不该被当成区块标题（否则示例文本会把笔记切碎）。"""
    body = "# t\n\n## 真区块\n\n```\n## 假区块\n```\n\n尾部。\n"
    headings = [chunk.heading for chunk in chunk_markdown("a/b", body)]
    chunks = chunk_markdown("a/b", body)
    assert headings == ["", "真区块"]  # "" 是 `## 真区块` 之前的前言块
    # 代码块里的假标题留在「真区块」的正文里，没有被切出去
    assert "## 假区块" in chunks[1].text


def test_third_level_heading_stays_inside_its_block() -> None:
    chunks = chunk_markdown("hii/notes/foo", BODY)
    duplicate = next(chunk for chunk in chunks if chunk.heading == "第一个区块 2")
    assert "### 三级标题不算块边界" in duplicate.text


def test_empty_body_yields_no_chunks() -> None:
    assert chunk_markdown("a/b", "   \n") == []


# ---- 检索词 ----


def test_terms_short_cjk_run_is_kept_whole() -> None:
    assert query_terms("商标共识规范") == ["商标共识规范"]


def test_terms_long_cjk_run_becomes_trigrams() -> None:
    terms = query_terms("请告诉我当前我们达成的商标共识规范是什么")
    assert "商标共" in terms and "识规范" in terms
    assert all(len(term) == 3 for term in terms)


def test_terms_keep_latin_tokens_and_drop_tiny_ones() -> None:
    terms = query_terms("HII 的 IP 与 a 的关系")
    assert "HII" in terms and "IP" in terms
    assert "a" not in terms


def test_fts_query_drops_terms_below_trigram() -> None:
    expression = fts_query(["进度", "商标共识", "HII"])
    assert '"商标共识"' in expression
    assert "进度" not in expression  # 2 字 < trigram 下限
    assert short_terms(["进度", "商标共识"]) == ["进度"]


def test_fts_query_escapes_quotes() -> None:
    assert fts_query(['a"b']) == '"a""b"'


# ---- 路由 ----


def _kind(question: str) -> QueryKind:
    kind, _reason = heuristic_route(question)
    return kind


def test_routes_retrospect_questions() -> None:
    assert _kind("HII 和我们的 IP 关系的来龙去脉是怎样的？") is QueryKind.RETROSPECT
    assert _kind("这个项目的历史沿革，最早怎么走到今天") is QueryKind.RETROSPECT


def test_routes_decision_questions() -> None:
    assert _kind("商标共识规范是什么") is QueryKind.DECISION
    assert _kind("这件事我们当时是怎么决定的，依据是什么") is QueryKind.DECISION


def test_routes_review_questions() -> None:
    assert _kind("帮我回顾一下这周做了什么") is QueryKind.REVIEW


def test_routes_synthesis_questions() -> None:
    assert _kind("HIC 目前有哪些 IT 系统，分别是什么状态") is QueryKind.SYNTHESIS


def test_route_plan_carries_retrieval_mix() -> None:
    plan = route_query("IT 开发的来龙去脉")
    assert plan.kind is QueryKind.RETROSPECT
    assert plan.hops == 2 and plan.time_desc is True
    assert "meeting-note" in plan.authority_types


def test_classifier_is_optional_and_never_breaks_routing() -> None:
    plan = route_query("随便问问", classifier=lambda _q: QueryKind.REVIEW)
    assert plan.kind is QueryKind.REVIEW
    assert "模型判定" in plan.reason

    def boom(_q: str) -> QueryKind | None:
        raise RuntimeError("模型挂了")

    fallback = route_query("商标共识规范是什么", classifier=boom)
    assert fallback.kind is QueryKind.DECISION  # 回落启发式，而不是抛异常
