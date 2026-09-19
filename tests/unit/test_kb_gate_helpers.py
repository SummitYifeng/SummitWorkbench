"""跨端闸门新增断言的**纯逻辑**单测（不联网、不花钱、不写 vault）。

闸门本体需要真实三端（SWB + `_vault` + SK）并触发一次付费检索，跑一次成本高；但它的
**判定**可以脱机钉住：语料边界计数、检索结果禁用类型、来源白名单覆盖。把这些判定抽成
`scripts/kb_three_end_gate.py` 里的纯函数后，本文件就能在 CI 里守住它们，也便于变异验证。

变异验证（把对应名单弄坏，本文件必须立刻红）：

- 从 `FORBIDDEN_CORPUS_TYPES` 拿掉 `source` / `daily` / `weekly-review` / `meeting-transcript`
  → ``test_forbidden_corpus_types_match_contract`` 或 ``test_forbidden_types_in_flags_*`` 变红；
- 把原件/简报的 SQL 判据改宽或改漏 → ``test_corpus_boundary_counts_*`` 变红；
- 从 `KNOWLEDGE_SOURCE_ROOTS` 拿掉一个主线项目或 `thinking` → ``test_whitelist_*`` 变红。
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from typing import Any

import pytest

_GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "kb_three_end_gate.py"


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("kb_three_end_gate_under_test", _GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_gate()


_CANONICAL_PROJECT_IDS = (
    "hii-royalty",
    "hii-ip-license",
    "hii-china-visit",
    "it-development",
    "finance-budget",
    "huoman-community",
    "huoman-logistics",
    "course-material-production",
)


def _chunks_db(tmp_path: Path, rows: list[tuple[str, str, str]]) -> sqlite3.Connection:
    """建一个只含闸门用到的那几列的合成 `chunks` 表。"""
    con = sqlite3.connect(tmp_path / "gate-synthetic.db")
    con.execute("CREATE TABLE chunks (source_file TEXT, content TEXT, type TEXT)")
    con.executemany("INSERT INTO chunks (source_file, content, type) VALUES (?, ?, ?)", rows)
    con.commit()
    return con


def test_forbidden_corpus_types_match_contract(gate: Any) -> None:
    """禁用类型名单必须与契约 §5.2 一致（漏一个 = 该类可能污染检索结果）。"""
    assert gate.FORBIDDEN_CORPUS_TYPES == frozenset(
        {"meeting-transcript", "source", "daily", "weekly-review"}
    )


@pytest.mark.parametrize("note_type", ["meeting-transcript", "source", "daily", "weekly-review"])
def test_forbidden_types_in_flags_every_boundary_type(gate: Any, note_type: str) -> None:
    assert gate.forbidden_types_in([{"type": note_type}]) == [note_type]
    # 正常语料类型不得被误报
    assert gate.forbidden_types_in([{"type": "note"}, {"type": "decision"}]) == []


def test_corpus_boundary_counts_detects_sources_and_daily(gate: Any, tmp_path: Path) -> None:
    """原件与简报/周报的任何片段都必须被数出来（闸门据此判 FAIL）。"""
    con = _chunks_db(
        tmp_path,
        [
            ("hii-royalty/sources/20260911-rules.md", "原件正文", "source"),
            ("hii-royalty/sources/attachments/x.md", "附件正文", "source"),
            ("daily/2026-09-18.md", "旧简报", "daily"),
            ("reviews/weekly/2026-W38.md", "旧周报", "weekly-review"),
            ("meetings/transcripts/2026-09-01.md", "逐字稿", "meeting-transcript"),
            ("inbox.md", "收件箱", "inbox"),
            ("projects/hii-royalty.md", "项目页", "project-main"),
        ],
    )
    try:
        counts = gate.corpus_boundary_counts(con)
    finally:
        con.close()
    assert counts["sources"] == 2
    assert counts["daily_weekly"] == 2
    assert counts["transcripts"] == 1
    assert counts["inbox"] == 1


def test_corpus_boundary_counts_clean_db_is_zero(gate: Any, tmp_path: Path) -> None:
    con = _chunks_db(tmp_path, [("projects/hii-royalty.md", "结论", "project-main")])
    try:
        counts = gate.corpus_boundary_counts(con)
    finally:
        con.close()
    assert counts == {"transcripts": 0, "sources": 0, "daily_weekly": 0, "inbox": 0}


def test_whitelist_covers_canonical_projects_and_thinking(gate: Any) -> None:
    """闸门这条守卫的判据：真实库全部主线项目可达、`thinking` 在内。"""
    assert gate.whitelist_missing(_CANONICAL_PROJECT_IDS) == []
    assert "thinking" in gate.KNOWLEDGE_SOURCE_ROOTS
    # 反例护栏：库外目录仍必须被拒（白名单不得被顺手放宽）
    assert gate.whitelist_missing(["notes"]) == ["notes"]
