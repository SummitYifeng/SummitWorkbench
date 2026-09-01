"""JSONL 容错读测试（LHF #2）：坏行跳过 + 告警 + 隔离，好行不受牵连。"""

from __future__ import annotations

import warnings

import pytest
from pydantic import BaseModel, ConfigDict

from summit_workbench.repositories._jsonl import (
    CorruptLogLine,
    append_row,
    read_models,
)


class Row(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    n: int = 0


def test_missing_file_returns_empty(tmp_path):
    assert read_models(tmp_path / "nope.jsonl", Row) == []


def test_reads_valid_rows_in_order(tmp_path):
    log = tmp_path / "log.jsonl"
    append_row(log, {"key": "a", "n": 1})
    append_row(log, {"key": "b", "n": 2})
    rows = read_models(log, Row)
    assert [(r.key, r.n) for r in rows] == [("a", 1), ("b", 2)]


def test_truncated_last_line_does_not_crash_whole_log(tmp_path):
    """断电/被 kill 留下的半截末行只丢自己，前面的好行照常读出。"""
    log = tmp_path / "log.jsonl"
    append_row(log, {"key": "a", "n": 1})
    append_row(log, {"key": "b", "n": 2})
    with log.open("a", encoding="utf-8") as fh:
        fh.write('{"key": "c", "n":')  # 半截行，无换行、无闭合
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        rows = read_models(log, Row)
    assert [r.key for r in rows] == ["a", "b"]


def test_missing_key_row_skipped_not_keyerror(tmp_path):
    log = tmp_path / "log.jsonl"
    append_row(log, {"n": 5})  # 缺必填 key
    append_row(log, {"key": "ok", "n": 6})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        rows = read_models(log, Row)
    assert [r.key for r in rows] == ["ok"]


def test_bad_line_warns(tmp_path):
    log = tmp_path / "log.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        fh.write("not json at all\n")
    with pytest.warns(CorruptLogLine):
        read_models(log, Row)


def test_bad_line_quarantined_and_original_untouched(tmp_path):
    log = tmp_path / "log.jsonl"
    append_row(log, {"key": "a"})
    with log.open("a", encoding="utf-8") as fh:
        fh.write("broken}\n")
    before = log.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row)
    # 原日志一字未改（非破坏性）
    assert log.read_text(encoding="utf-8") == before
    quarantine = log.with_name(log.name + ".quarantine")
    assert quarantine.is_file()
    assert "broken}" in quarantine.read_text(encoding="utf-8")


def test_quarantine_disabled(tmp_path):
    log = tmp_path / "log.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        fh.write("broken}\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row, quarantine=False)
    assert not log.with_name(log.name + ".quarantine").exists()


def test_extra_fields_ignored_schema_drift(tmp_path):
    log = tmp_path / "log.jsonl"
    append_row(log, {"key": "a", "n": 1, "future_field": "x"})
    rows = read_models(log, Row)
    assert rows[0].key == "a"


def test_blank_lines_ignored(tmp_path):
    log = tmp_path / "log.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        fh.write('{"key": "a"}\n\n   \n{"key": "b"}\n')
    rows = read_models(log, Row)
    assert [r.key for r in rows] == ["a", "b"]
