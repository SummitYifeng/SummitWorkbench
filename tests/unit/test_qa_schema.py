"""M1-6：问答回答 schema。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from summit_workbench.domain.qa import QaAnswer


def test_parses_and_collects_cited_sources():
    answer = QaAnswer.model_validate(
        {
            "summary": "结论",
            "facts": [
                {"text": "A", "source_id": "projects/P1"},
                {"text": "B", "source_id": "meetings/notes/m1"},
            ],
            "suggestions": ["建议一"],
            "conflicts": [
                {
                    "topic": "价格",
                    "sides": [
                        {"position": "涨价", "source_id": "projects/P1"},
                        {"position": "不涨", "source_id": "insights/x"},
                    ],
                }
            ],
        }
    )
    assert answer.cited_source_ids() == {
        "projects/P1",
        "meetings/notes/m1",
        "insights/x",
    }
    assert answer.unanswerable is False


def test_conflict_requires_two_sides():
    with pytest.raises(ValidationError):
        QaAnswer.model_validate(
            {
                "summary": "x",
                "conflicts": [{"topic": "t", "sides": [{"position": "p", "source_id": "s"}]}],
            }
        )


def test_unanswerable_defaults_and_empty_lists():
    answer = QaAnswer.model_validate({"summary": "无法回答", "unanswerable": True})
    assert answer.facts == []
    assert answer.cited_source_ids() == set()
