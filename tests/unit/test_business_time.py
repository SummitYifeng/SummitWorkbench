"""业务日期必须按北京时间计算，且拒绝无时区时间。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from summit_workbench.domain.time import business_date
from summit_workbench.repositories.project_registry import create_project_note
from summit_workbench.repositories.thread_notes import _day


def test_business_day_uses_shanghai() -> None:
    assert business_date(datetime(2026, 9, 15, 16, 30, tzinfo=UTC)) == "2026-09-16"


def test_business_day_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="时区"):
        business_date(datetime(2026, 9, 16, 0, 30))


def test_generated_note_dates_use_business_day() -> None:
    moment = datetime(2026, 9, 15, 16, 30, tzinfo=UTC)
    assert _day(moment) == "2026-09-16"


def test_project_note_uses_business_day(tmp_path) -> None:
    path = create_project_note(tmp_path, "P1", now=datetime(2026, 9, 15, 16, 30, tzinfo=UTC))
    assert "date: 2026-09-16" in path.read_text(encoding="utf-8")
