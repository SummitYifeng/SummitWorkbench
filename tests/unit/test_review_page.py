"""M1-4 审批页语法：roundtrip、编辑保留、拒绝与错误保护。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_page import (
    parse_review_page,
    refresh_review_page,
    render_review_page,
)


def _entry(stable_id: str = "m:n#action-item-0") -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=CandidateKind.ACTION_ITEM,
        description="提交样章",
        target_project="P1",
        route=RouteTarget.FEISHU_TASK,
        evidence=EvidenceRef(anchor="张三 00:03"),
        due_date="2026-09-04",
        is_next_step=True,
    )
    return ReviewEntry(
        candidate,
        "提交样章",
        "2026-08-31",
        "评审会",
        "[[meetings/notes/2026-08-31-评审会]]",
        "[[2026-08-31-评审会-transcript]]",
    )


def test_render_parse_roundtrip_and_approval_edit():
    text = render_review_page([_entry()], today=date(2026, 8, 31))
    edited = text.replace("- [ ] `id:", "- [x] `id:").replace("提交样章", "提交终稿", 1)
    parsed = parse_review_page(edited)
    assert parsed.errors == []
    item = parsed.entries[0]
    assert item.candidate.decision == CandidateDecision.APPROVED
    assert item.candidate.description == "提交终稿"
    assert item.ai_original == "提交样章"


def test_rejected_syntax_roundtrips():
    entry = replace(
        _entry(),
        candidate=replace(_entry().candidate, decision=CandidateDecision.REJECTED),
    )
    parsed = parse_review_page(render_review_page([entry]))
    assert parsed.errors == []
    assert parsed.entries[0].candidate.decision == CandidateDecision.REJECTED


def test_plain_strikethrough_is_also_rejected():
    text = render_review_page([_entry()]).replace(
        "- [ ] `id: m:n#action-item-0` [action-item] 提交样章",
        "- [ ] ~~`id: m:n#action-item-0` [action-item] 提交样章~~",
    )
    parsed = parse_review_page(text)
    assert parsed.errors == []
    assert parsed.entries[0].candidate.decision == CandidateDecision.REJECTED


def test_refresh_preserves_user_edit_and_only_adds_new(tmp_path):
    first = refresh_review_page(tmp_path, [_entry()], today=date(2026, 8, 31))
    text = first.path.read_text(encoding="utf-8").replace("提交样章", "人工改写", 1)
    first.path.write_text(text, encoding="utf-8")
    second = refresh_review_page(
        tmp_path,
        [_entry(), _entry("m:n#action-item-1")],
        today=date(2026, 8, 31),
    )
    parsed = parse_review_page(second.path.read_text(encoding="utf-8"))
    assert second.added == 1
    assert second.preserved == 1
    assert parsed.entries[0].candidate.description == "人工改写"


def test_refresh_refuses_to_overwrite_invalid_page(tmp_path):
    first = refresh_review_page(tmp_path, [_entry()])
    first.path.write_text(
        first.path.read_text(encoding="utf-8") + "\n- [x] broken\n", encoding="utf-8"
    )
    try:
        refresh_review_page(tmp_path, [_entry("new")])
    except ValueError as exc:
        assert "拒绝覆盖" in str(exc)
    else:
        raise AssertionError("invalid page should not be overwritten")


def test_parser_ignores_template_example_inside_html_comment():
    text = render_review_page([]) + """
<!-- 示例：
## 2026-08-30 示例会
- [ ] `id: example` [行动项] 这不是实际候选
-->
"""
    parsed = parse_review_page(text)
    assert parsed.errors == []
    assert parsed.entries == []
