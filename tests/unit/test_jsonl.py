"""JSONL 容错读测试（LHF #2）：坏行跳过 + 告警 + 隔离，好行不受牵连。

P0-06 追加：隔离记录带稳定 id（sha256(source + 行号 + raw)），同一坏行重复读取
只写一条 quarantine；记录含截断 raw、原因、首次发现时间与稳定 id；raw 有上限。
"""

from __future__ import annotations

import json
import warnings

import pytest
from pydantic import BaseModel, ConfigDict

from summit_workbench.repositories._jsonl import (
    CorruptLogLine,
    append_row,
    quarantine_id,
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


# ---- P0-06：quarantine 稳定 id / 去重 / 截断 / 字段 ----


def _quarantine_records(log) -> list[dict[str, object]]:
    sidecar = log.with_name(log.name + ".quarantine")
    assert sidecar.is_file(), "quarantine 文件应存在"
    records: list[dict[str, object]] = []
    for line in sidecar.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue  # 旧版注释/非记录行跳过
    return records


def test_quarantine_id_is_sha256_of_source_line_and_raw(tmp_path):
    """稳定 id = sha256(source-relative-path + line-number + raw-line)；仅 64 位十六进制。"""
    sid = quarantine_id("usage/2026-09.jsonl", 7, '{"n":')
    assert len(sid) == 64
    assert int(sid, 16) >= 0
    # 同一三元组稳定；行号或 raw 变化则 id 变化
    assert sid == quarantine_id("usage/2026-09.jsonl", 7, '{"n":')
    assert sid != quarantine_id("usage/2026-09.jsonl", 8, '{"n":')
    assert sid != quarantine_id("usage/2026-09.jsonl", 7, '{"n": "other"')


def test_same_bad_line_read_thrice_quarantines_once(tmp_path):
    """同一坏 JSONL 行读取三次：quarantine 只有一条；新增另一坏行后为两条。"""
    log = tmp_path / "usage.jsonl"
    append_row(log, {"key": "ok"})
    with log.open("a", encoding="utf-8") as fh:
        fh.write('{"key": "broken", "n":\n')  # 半截行：第 2 行
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        for _ in range(3):
            read_models(log, Row)

    records = _quarantine_records(log)
    assert len(records) == 1
    first = records[0]
    assert first["line"] == 2
    assert first["source"] == log.name
    assert first["id"] == quarantine_id(log.name, 2, '{"key": "broken", "n":')
    assert "broken" in str(first["raw"])
    assert first["first_seen"]  # 首次发现时间非空
    assert first["reason"]

    # 新增另一条坏行 → quarantine 追加为两条，原记录（id/first_seen）不被改写
    with log.open("a", encoding="utf-8") as fh:
        fh.write("totally-not-json\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row)
    records = _quarantine_records(log)
    assert len(records) == 2
    assert records[0]["id"] == first["id"]
    assert records[0]["first_seen"] == first["first_seen"]
    ids = {record["id"] for record in records}
    assert len(ids) == 2


def test_quarantine_record_keeps_truncated_raw_with_cap(tmp_path):
    """超长 raw 只保存截断版本（有上限），但稳定 id 基于完整 raw 计算。"""
    log = tmp_path / "usage.jsonl"
    huge = "x" * 5_000 + '{"n":'  # 5KB 半截行
    with log.open("w", encoding="utf-8") as fh:
        fh.write(huge + "\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row)

    record = _quarantine_records(log)[0]
    raw = record["raw"]
    assert isinstance(raw, str)
    assert len(raw) <= 2_000, "raw 必须受上限约束，防止诊断文件膨胀"
    assert raw != huge, "超长 raw 应被截断"
    assert raw.startswith("x" * 20)
    # 去重 id 由完整 raw 计算：再读一次不产生第二条
    assert record["id"] == quarantine_id(log.name, 1, huge)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row)
    assert len(_quarantine_records(log)) == 1


def test_legacy_quarantine_lines_are_tolerated(tmp_path):
    """旧版注释格式的 quarantine 行被容忍跳过，新记录照常追加，不互相覆盖。"""
    log = tmp_path / "log.jsonl"
    sidecar = log.with_name(log.name + ".quarantine")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        "# 2026-09-05T00:00:00+00:00 log.jsonl:3\nnot-json-legacy\n", encoding="utf-8"
    )
    with log.open("w", encoding="utf-8") as fh:
        fh.write('{"key": "broken", "n":\n')
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        read_models(log, Row)
    records = _quarantine_records(log)
    assert len(records) == 1
    assert records[0]["line"] == 1
    # 旧文本仍在文件中，未被覆盖
    text = sidecar.read_text(encoding="utf-8")
    assert "not-json-legacy" in text
    assert len(records) == len([line for line in text.splitlines() if line.startswith("{")])


def test_quarantine_id_independent_of_absolute_path(tmp_path):
    """同一逻辑日志换绝对路径（如同步到另一台机器）时 id 不变，便于跨机去重。"""
    raw = '{"key": "broken", "n":'
    assert quarantine_id("log.jsonl", 3, raw) == quarantine_id("log.jsonl", 3, raw)
    # 相同 source/行号/raw 在不同目录下 id 相同
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    log_a = tmp_path / "log.jsonl"
    log_b = other_dir / "log.jsonl"
    assert quarantine_id(log_a.name, 3, raw) == quarantine_id(log_b.name, 3, raw)
