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


def test_leading_h1_is_the_note_title_not_a_block() -> None:
    """文首 H1 是「笔记标题」，不切块——它下面的正文只是引言。

    2026-09-14 实测：把文首 H1 也当块边界，会让「标题块」在检索里与实际内容块抢排名
    （`it/clusters/enrollment#报名与课程生命周期` 压过 `#关键结论`），块级命中率只有 25%。
    """
    chunks = chunk_markdown("hii/notes/foo", BODY)
    assert [chunk.heading for chunk in chunks] == ["", "第一个区块", "第二个区块", "第一个区块 2"]
    assert chunks[0].anchor == "hii/notes/foo"  # 前言块：锚点＝笔记本身
    assert "# 标题" in chunks[0].text


def test_level_one_heading_is_a_block_boundary() -> None:
    """R2：**非文首**的一级标题切块——原始材料常用 `#` 分大章，
    只切 `##` 会让这些章节并进相邻块、无法被 `路径#区块` 定点引用。"""
    body = (
        "# 原文：全景总结\n"  # 文首 H1 = 笔记标题，不切块
        "\n## 原文（逐字，未改写）\n"
        "\n# 六、正式名称\n\n正文甲。\n"
        "\n## 6.1 登记主体\n\n正文乙。\n"
        "\n# 七、落地事项\n\n正文丙。\n"
    )
    chunks = chunk_markdown("hii/sources/overview", body)
    assert [chunk.heading for chunk in chunks] == [
        "",
        "原文（逐字，未改写）",
        "六、正式名称",
        "6.1 登记主体",
        "七、落地事项",
    ]
    assert chunks[2].anchor == "hii/sources/overview#六、正式名称"
    assert chunks[4].anchor == "hii/sources/overview#七、落地事项"
    assert "正文丙" in chunks[4].text


def test_text_before_first_heading_is_a_preamble_chunk() -> None:
    """首个块边界之前的正文是「前言块」，锚点＝笔记本身。"""
    body = "前言段落。\n\n## 第一个区块\n\n内容。\n"
    chunks = chunk_markdown("a/b", body)
    assert [chunk.heading for chunk in chunks] == ["", "第一个区块"]
    assert chunks[0].anchor == "a/b"
    assert chunks[1].anchor == "a/b#第一个区块"


def test_fenced_code_block_does_not_split() -> None:
    """围栏里的 `#` / `##` 不该被当成区块标题（否则示例文本会把笔记切碎）。"""
    body = "# t\n\n## 真区块\n\n```\n## 假区块\n```\n\n```\n# 假一级标题\n```\n\n尾部。\n"
    chunks = chunk_markdown("a/b", body)
    assert [chunk.heading for chunk in chunks] == ["", "真区块"]
    # 代码块里的假标题留在「真区块」的正文里，没有被切出去
    assert "## 假区块" in chunks[1].text
    assert "# 假一级标题" in chunks[1].text


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


def test_unmatched_questions_fall_back_to_question_form_not_length() -> None:
    """R4：一个关键词都没命中时，按**问句形态**判，而不是按长度瞎猜。

    2026-09-14 实测：不判形态时「HII 与 HIF 是同一个主体吗？内部编辑时怎么处理？」
    落到 synthesis（理由「无关键词：按长度兜底」），而它其实是个是否类点查；
    「…为什么分开管理？」落到 point，而它其实该走决策。
    """
    assert _kind("HII 与 HIF 是同一个主体吗？内部编辑时怎么处理？") is QueryKind.POINT
    assert _kind("这两份材料是一致吗") is QueryKind.POINT
    assert _kind("「活满」与「和夫曼之旅」为什么分开管理？") is QueryKind.DECISION
    assert _kind("这个口径不一致的话该怎么处理") is QueryKind.DECISION
    assert _kind("这两套材料有什么不同？") is QueryKind.SYNTHESIS
    # 兜底理由必须可读（不能只说「按长度」）
    _kind_hit, reason = heuristic_route("「活满」与「和夫曼之旅」为什么分开管理？")
    assert "问句形态" in reason, reason


def test_form_fallback_never_overrides_a_keyword_hit() -> None:
    """形态兜底只在无关键词时生效：有关键词时仍以关键词为准（不改变既有路由）。"""
    assert _kind("根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？") is QueryKind.DECISION
    assert _kind("Danny 来华目前还差哪些必须收口？下一步谁做什么？") is QueryKind.POINT
    assert _kind("IT 当前的开发进度是什么，下一个阶段该怎么做？") is QueryKind.POINT


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
