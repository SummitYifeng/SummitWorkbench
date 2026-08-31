"""M1-6：qa-insight 落盘、schema 合规与幂等。"""

from __future__ import annotations

from summit_workbench.domain.qa import QaAnswer
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.qa_insight import (
    QaInsightInput,
    save_qa_insight,
)
from summit_workbench.repositories.vault import load_note


def _input() -> QaInsightInput:
    answer = QaAnswer.model_validate(
        {
            "summary": "价格设为免费。",
            "facts": [{"text": "免费由后台设置", "source_id": "projects/P1"}],
            "suggestions": ["关注白名单"],
            "conflicts": [
                {
                    "topic": "涨价与否",
                    "sides": [
                        {"position": "涨价", "source_id": "projects/P1"},
                        {"position": "不涨", "source_id": "meetings/notes/m1"},
                    ],
                }
            ],
        }
    )
    return QaInsightInput(
        question="价格怎么定？",
        answer=answer,
        source_ids=["projects/P1", "meetings/notes/m1"],
        model_id="m",
        prompt_version="qa-answer@v1",
        date="2026-08-31",
    )


def test_save_writes_schema_valid_note(tmp_path):
    outcome = save_qa_insight(tmp_path, _input())
    assert outcome.written is True
    note = load_note(outcome.path)
    assert note.parse_error is None
    assert note.meta.get("type") == "qa-insight"
    assert note.meta.get("project") == "global"
    assert validate_note(note.meta, note.body) == []
    assert "[[projects/P1]]" in note.body
    assert "涨价与否" in note.body


def test_save_is_idempotent(tmp_path):
    first = save_qa_insight(tmp_path, _input())
    second = save_qa_insight(tmp_path, _input())
    assert first.path == second.path
    assert second.written is False
