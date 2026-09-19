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

import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "kb_three_end_gate.py"


def _load_gate() -> Any:
    """按**源码**执行闸门脚本，绕过 `__pycache__`。

    为什么不用 `spec.loader.exec_module`：pyc 头里的源 mtime 只有 1 秒粒度，
    **同秒内等长改动**（如 `fail` ↔ `warn`）会命中过期字节码，让变异验证得出错误结论
    （2026-09-19 实测踩到）。
    """
    module = ModuleType("kb_three_end_gate_under_test")
    module.__file__ = str(_GATE_PATH)
    exec(compile(_GATE_PATH.read_text(encoding="utf-8"), str(_GATE_PATH), "exec"), module.__dict__)
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


# ─────────────── 推送守卫 / 端点解析（第四·五阶段新增） ───────────────


def test_auto_push_state_of_unknown_pid_is_not_enabled(gate: Any) -> None:
    """读不到进程/环境时保守返回 False/None——绝不默认"已启用不推送"。"""
    assert gate.auto_push_state_of_pid(None) is None
    assert gate.auto_push_state_of_pid("999999") is False


def test_origin_main_rev_reads_tracking_ref(gate: Any, tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "vault"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "a.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True, capture_output=True
    )
    assert gate.origin_main_rev(repo) == "(无 origin/main)"
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD"],
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert gate.origin_main_rev(repo) == head


def test_origin_guard_fails_when_not_pushing_but_remote_moved(gate: Any, tmp_path: Path) -> None:
    """未启用推送模式却发生推送 ⇒ 必须 **FAIL**（2026-09-19 事故的机器守卫）。

    只看退出码的 agent 也要能发现"验证意外推送了 vault"；变异验证：改回 WARN 即变红。
    """
    repo = tmp_path / "vault"
    repo.mkdir()
    rep = gate.Report()
    gate.gate_origin_guard(rep, repo, "deadbee", push_enabled=False)
    assert any("origin/main" in item for item in rep.failures)
    assert rep.warnings == []


def test_origin_guard_is_quiet_when_push_mode_may_explain_it(gate: Any, tmp_path: Path) -> None:
    repo = tmp_path / "vault"
    repo.mkdir()
    rep = gate.Report()
    gate.gate_origin_guard(rep, repo, "deadbee", push_enabled=True)
    assert rep.warnings == []
    assert rep.failures == []


# ───────── [1/6] 预检：安全/中性的同步状态不得判 FAIL，保护态必须 FAIL ─────────

# 这些状态对闸门要守的不变量无碍（2026-09-19 逐个核对 domain.sync.SyncState）：
# 判 FAIL 会让"连续第二次跑闸门""离线""未配远端""认证过期"这类正常情形必挂。
_SYNC_WARN_STATES = (
    "error",
    "local-ahead",
    "offline-local-ahead",
    "remote-ahead",
    "unconfigured",
    "syncing",
    "auth-required",
)
# 写库真的不安全的保护态 + 未知状态：必须 FAIL。
_SYNC_FAIL_STATES = (
    "diverged-protected",
    "dirty-protected",
    "remote-scheme-unsupported",
    "totally-unknown",
)


def _preflight_with_state(gate: Any, vault: Path, monkeypatch: Any, state: str) -> Any:
    def fake_http(url: str, **_kwargs: object) -> dict[str, object]:
        if url.endswith("/api/sync/status"):
            return {"state": state, "detail": ""}
        return {
            "ready": True,
            "active_kb_id": "work",
            "profiles": [{"id": "work", "pending_index": 0, "rerank_degraded": False}],
        }

    monkeypatch.setattr(gate, "http_json", fake_http)
    rep = gate.Report()
    gate.gate_preflight(rep, vault, "http://swb", "tok", "http://swb", "http://sk", "tok")
    return rep


@pytest.mark.parametrize("state", _SYNC_WARN_STATES)
def test_preflight_downgrades_safe_sync_states(
    gate: Any, tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    """安全/中性的同步状态只告警（含详细含义），不判 FAIL。"""
    vault = tmp_path / "vault"
    vault.mkdir()
    rep = _preflight_with_state(gate, vault, monkeypatch, state)
    output = capsys.readouterr().out
    assert rep.failures == [], state
    assert any(state in item for item in rep.warnings), state
    if state == "auth-required":
        assert "重新登录" in output  # detail 里说清怎么办


@pytest.mark.parametrize("state", _SYNC_FAIL_STATES)
def test_preflight_still_fails_on_unsafe_or_unknown_states(
    gate: Any, tmp_path: Path, monkeypatch: Any, state: str
) -> None:
    """`diverged*`/`dirty*` 保护态与未知状态仍必须 FAIL（不认识不等于没事）。"""
    vault = tmp_path / "vault"
    vault.mkdir()
    rep = _preflight_with_state(gate, vault, monkeypatch, state)
    assert any("state 健康" in item for item in rep.failures), state
