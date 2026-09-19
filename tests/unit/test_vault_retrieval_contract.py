"""T1：工作库检索就绪契约 —— 全部状态、代码围栏、固定结构、superseded 与 archived。

契约的价值在于「可执行」：它必须能被 SK 侧同样理解（块边界 = 代码围栏之外的 ``#``/``##``），
也必须把「合法保存」与「可作为事实依据」分开。本文件把这两件事都钉成断言。
"""

from __future__ import annotations

import pytest

from summit_workbench.domain.retrieval_contract import (
    is_derived_low_authority,
    is_fact_retrieval_eligible,
    is_non_fact_status,
    validate_retrieval_readiness,
)
from summit_workbench.domain.vault import (
    NON_RETRIEVED_TYPES,
    STATUS_VOCAB,
    has_unbalanced_fence,
    iter_headings,
    validate_note,
)

_PROJECT_MAIN_BODY = (
    "# P1\n\n## 当前状态\n\n进行中\n\n## 下一步\n\n继续\n\n## 阻塞\n\n无\n\n## 决策记录\n\n无\n"
)

_DECISION_BODY = (
    "# 决策：统一口径\n\n## 背景\n\nb\n\n## 选项\n\no\n\n## 决定\n\nd\n\n"
    "## 理由\n\nr\n\n## 影响\n\ni\n\n## 证据\n\ne\n\n## 关联\n\n- [[projects/P1]]\n"
)


def _meta(note_type: str, status: str, **extra: object) -> dict[str, object]:
    return {"date": "2026-09-14", "type": note_type, "status": status, **extra}


def _codes(meta: dict[str, object], body: str) -> list[str]:
    return [issue.code for issue in validate_retrieval_readiness(meta, body)]


# --------------------------------------------------------------------- 状态语义


@pytest.mark.parametrize("status", sorted(STATUS_VOCAB))
def test_every_status_in_vocabulary_is_legal(status: str) -> None:
    """词表里的每个状态都**合法**——包括 archived 与 generated，不得被当成错误。"""
    assert _codes(_meta("note", status), "# 短笔记\n\n正文。\n") == []


def test_archived_is_legal_history_not_superseded() -> None:
    """``archived`` 表示项目已结束，不代表内容被推翻：仍是合法历史知识。"""
    meta = _meta("project-main", "archived")
    assert _codes(meta, _PROJECT_MAIN_BODY) == []
    assert is_fact_retrieval_eligible(meta) is True
    assert is_non_fact_status(meta) is False
    assert is_derived_low_authority(meta) is False


def test_generated_is_legal_but_low_authority() -> None:
    meta = _meta("work-log", "generated")
    assert _codes(meta, "# 日志\n\n原文。\n") == []
    assert is_fact_retrieval_eligible(meta) is True  # 可参与回答
    assert is_derived_low_authority(meta) is True  # 但不能单独支撑高置信事实


@pytest.mark.parametrize("status", ["draft", "pending-review", "ignored"])
def test_non_fact_statuses_are_saved_but_not_fact_corpus(status: str) -> None:
    meta = _meta("meeting-note", status)
    # 可合法保存（不做事实资格，但也不是结构错误）
    assert "unknown-status" not in _codes(meta, "# 会\n\n## 一分钟摘要\n\nx\n")
    assert is_fact_retrieval_eligible(meta) is False
    assert is_non_fact_status(meta) is True


def test_unknown_status_is_reported() -> None:
    assert "unknown-status" in _codes(_meta("note", "rejected"), "")


# --------------------------------------------------------------------- 结构 / 围栏


def test_short_note_without_h2_is_allowed() -> None:
    """短笔记 / work-log / thread-doc 允许文件级引用，不要求有 ##。"""
    for note_type in ("note", "work-log", "thread-doc"):
        assert _codes(_meta(note_type, "active"), "一句话结论，没有任何 ## 区块。") == []


def test_fixed_block_note_missing_block_is_reported() -> None:
    body = "# P1\n\n## 当前状态\n\n进行中\n"
    codes = _codes(_meta("project-main", "active"), body)
    assert "missing-required-block" in codes
    assert len([c for c in codes if c == "missing-required-block"]) == 3  # 缺 下一步/阻塞/决策记录


def test_fixed_block_note_complete_passes() -> None:
    assert _codes(_meta("decision", "applied"), _DECISION_BODY) == []


def test_duplicate_h2_is_an_error() -> None:
    body = "# 主题\n\n## 关键结论\n\na\n\n## 关键结论\n\nb\n"
    assert "duplicate-heading" in _codes(_meta("note", "active"), body)


def test_duplicate_h1_is_an_error() -> None:
    body = "# 同名标题\n\na\n\n# 同名标题\n\nb\n"
    assert "duplicate-heading" in _codes(_meta("note", "active"), body)


def test_h3_duplicates_are_not_citable_boundaries() -> None:
    """``###`` 保留在父块内，重复不算引用问题。"""
    body = "# 主题\n\n## 区块\n\n### 小节\n\na\n\n### 小节\n\nb\n"
    assert _codes(_meta("note", "active"), body) == []


def test_headings_inside_code_fence_are_not_boundaries() -> None:
    """围栏代码里的 ``#`` 是示例而不是区块：不能因此误报重复标题。"""
    body = "# 主题\n\n## 真实区块\n\n```markdown\n## 真实区块\n# 随便什么\n```\n\n正文。\n"
    assert _codes(_meta("note", "active"), body) == []


def test_unbalanced_fence_is_reported() -> None:
    body = "# 主题\n\n## 区块\n\n```python\nprint(1)\n"
    assert "invalid-fence" in _codes(_meta("note", "active"), body)


def test_non_retrieved_types_skip_retrieval_checks() -> None:
    """只写不检索的类型（导航页/规范页/收件箱/模板）结构自由。"""
    body = "# 索引\n\n## 分节\n\na\n\n## 分节\n\nb\n"
    for note_type in ("index", "conventions", "inbox", "template", "prompt", "workflow"):
        assert _codes(_meta(note_type, "active"), body) == []


def test_source_and_transcript_are_write_only_types() -> None:
    """2026-09-19 契约对齐：原件与逐字稿都不进检索语料（含重复标题也不报检索问题）。"""
    assert {"source", "meeting-transcript"} <= NON_RETRIEVED_TYPES
    body = "# 原件\n\n## 分节\n\na\n\n## 分节\n\nb\n"  # 重复 H2：检索就绪会报
    for note_type in ("source", "meeting-transcript"):
        assert _codes(_meta(note_type, "active"), body) == []
        assert is_fact_retrieval_eligible(_meta(note_type, "active")) is False


def test_source_skips_retrieval_readiness_but_keeps_fixed_block_schema() -> None:
    """两层职责不可互相吞掉：source 不再做检索就绪校验，但固定区块仍由 validate_note 守。"""
    body = "# 原件\n\n## 来源\n\n正文\n"  # 缺 `## 要点` / `## 关联`
    # 检索就绪：source 只写不检索 → 不报（变异验证：把 source 移出 NON_RETRIEVED_TYPES 即红）
    assert _codes(_meta("source", "active"), body) == []
    # 结构校验：固定区块照旧缺失即报（变异验证：删掉 NOTE_TYPES["source"] 的 required_blocks 即红）
    issues = validate_note(_meta("source", "active"), body)
    messages = " ".join(str(issue) for issue in issues)
    assert "要点" in messages and "关联" in messages


def test_daily_and_weekly_review_are_write_only_types() -> None:
    """简报/周复盘已不在库内：SK 检索排除、SWB 名单必须跟上（另一处"两侧名单对不上"）。"""
    assert {"daily", "weekly-review"} <= NON_RETRIEVED_TYPES
    body = "# 简报\n\n## 分节\n\na\n\n## 分节\n\nb\n"  # 重复 H2：检索就绪会报
    for note_type in ("daily", "weekly-review"):
        assert _codes(_meta(note_type, "active"), body) == []
        assert is_fact_retrieval_eligible(_meta(note_type, "active")) is False


# --------------------------------------------------------------------- superseded


def test_superseded_decision_requires_replacement_link() -> None:
    codes = _codes(_meta("decision", "superseded"), _DECISION_BODY)
    assert "superseded-missing-field" in codes
    assert "superseded-missing-link" in codes


def test_superseded_decision_with_link_passes() -> None:
    meta = _meta(
        "decision",
        "superseded",
        decision_status="superseded",
        superseded_by="decisions/0099-new",
    )
    assert _codes(meta, _DECISION_BODY) == []


def test_superseded_flag_on_non_superseded_decision_is_ignored() -> None:
    """只在 status: superseded 时要求替代链接，不误伤普通决策。"""
    assert _codes(_meta("decision", "applied"), _DECISION_BODY) == []


# --------------------------------------------------------------------- 事实资格


@pytest.mark.parametrize(
    ("note_type", "status", "expected"),
    [
        ("note", "active", True),
        ("note", "applied", True),
        ("work-log", "generated", True),
        ("note", "draft", False),
        ("note", "pending-review", False),
        ("note", "ignored", False),
        ("index", "active", False),
        ("conventions", "active", False),
        ("template", "active", False),
        ("unknown-type", "active", False),
    ],
)
def test_fact_retrieval_eligibility(note_type: str, status: str, expected: bool) -> None:
    assert is_fact_retrieval_eligible(_meta(note_type, status)) is expected


# --------------------------------------------------------------------- 纯扫描函数


def test_iter_headings_reports_level_and_text() -> None:
    got = list(iter_headings("# 标题\n\n## 区块一\n\ntext\n\n### 小节\n"))
    assert got == [(1, "标题"), (2, "区块一"), (3, "小节")]


def test_iter_headings_skips_fenced_blocks_with_tilde() -> None:
    got = list(iter_headings("~~~\n## 假的\n~~~\n\n## 真的\n"))
    assert got == [(2, "真的")]


def test_has_unbalanced_fence_flags_open_fence_only() -> None:
    assert has_unbalanced_fence("```\ncode\n") is True
    assert has_unbalanced_fence("```\ncode\n```\n") is False
    assert has_unbalanced_fence("普通正文\n") is False
