"""M1-3 结构化会议笔记渲染、证据回链与幂等写入。"""

from __future__ import annotations

from summit_workbench.domain.meeting import (
    ActionItem,
    Decision,
    MeetingExtraction,
    SourcedStatement,
)
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.meeting_note import (
    MeetingNoteInput,
    archive_meeting_note,
    render_meeting_note,
)
from summit_workbench.repositories.vault import parse_frontmatter


def _input() -> MeetingNoteInput:
    extraction = MeetingExtraction(
        one_minute_summary="确定交付方案。",
        facts=[SourcedStatement(text="样章完成", evidence="李四 00:03")],
        decisions=[
            Decision(description="采用 A", target_project="ProjectA", evidence="张三 00:05")
        ],
        action_items=[
            ActionItem(
                description="提交样章",
                target_project="ProjectA",
                due_date="2026-09-03",
                evidence="王五 00:08",
            )
        ],
        open_questions=[SourcedStatement(text="封面待定", evidence="段落 9")],
        ai_suggestions=["建议复核排版"],
    )
    return MeetingNoteInput(
        date="2026-08-31",
        title="项目会",
        idem_key="m:n",
        extraction=extraction,
        source=SourceKind.FEISHU_NOTE,
        transcript_stem="2026-08-31-项目会-transcript",
        model_id="test-model",
        prompt_version="meeting-processor@v2",
        meeting_id="m",
        note_id="n",
    )


def test_render_note_passes_schema_and_links_evidence():
    text = render_meeting_note(_input())
    meta, body, error = parse_frontmatter(text)
    assert error is None
    assert validate_note(meta, body) == []
    assert meta["status"] == "pending-review"
    assert meta["projects"] == ["ProjectA"]
    assert "[[2026-08-31-项目会-transcript]]" in text
    assert "王五 00:08" in text


def test_archive_note_is_idempotent_and_does_not_overwrite(tmp_path):
    first = archive_meeting_note(tmp_path, _input())
    assert first.written is True
    first.path.write_text(first.path.read_text(encoding="utf-8") + "\n人工修改\n", encoding="utf-8")
    second = archive_meeting_note(tmp_path, _input())
    assert second.written is False
    assert "人工修改" in second.path.read_text(encoding="utf-8")


def test_rendered_note_omits_ai_suggestions_block():
    """2026-09-18 起会议笔记不再生成 `## AI 建议`（使用者要求只留会议事实）。

    注意区分两件事：
    - **不再生成**：渲染器不输出该区块；
    - **仍兼容**：区块标题保留在 `optional_blocks` 里，历史笔记不会被判非法。
    """
    inp = _input()
    text = render_meeting_note(inp)
    assert "## AI 建议" not in text, "渲染器不应再输出 AI 建议区块"
    assert "## 关联项目" in text and "## 证据索引" in text
    # 八区块版本仍必须通过 schema
    meta, body, error = parse_frontmatter(text)
    assert error is None
    assert validate_note(meta, body) == []


def test_historical_note_with_ai_suggestions_still_valid():
    """兼容面：历史笔记里的 `## AI 建议` 必须仍然合法（区块标题只增不减）。"""
    inp = _input()
    text = render_meeting_note(inp)
    legacy = text.replace(
        "## 关联项目",
        "## AI 建议\n\n- 历史条目\n\n## 关联项目",
        1,
    )
    meta, body, error = parse_frontmatter(legacy)
    assert error is None
    assert validate_note(meta, body) == []
