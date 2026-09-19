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
import sys
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

    必须先把模块登记进 `sys.modules` 再 exec：脚本里的 `@dataclass` 会按 `cls.__module__`
    回查 `sys.modules` 建类，查不到就会 `AttributeError: 'NoneType' object has no attribute
    '__dict__'`（加 `JournalProbe` 时实测踩到）。
    """
    module = ModuleType("kb_three_end_gate_under_test")
    module.__file__ = str(_GATE_PATH)
    sys.modules[module.__name__] = module
    try:
        exec(
            compile(_GATE_PATH.read_text(encoding="utf-8"), str(_GATE_PATH), "exec"),
            module.__dict__,
        )
    finally:
        sys.modules.pop(module.__name__, None)
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


# ───────── [1/7] 预检：安全/中性的同步状态不得判 FAIL，保护态必须 FAIL ─────────

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


# ─────────────── [3/7] 日志写入步骤：用真实 router 脱机验证（第七阶段新增） ───────────────


def _seed_gate_vault(tmp_path: Path) -> Path:
    """建一个已提交的 git vault：一个项目页 + 一行 capture 验证件的 inbox.md。"""
    import subprocess

    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "FinanceOps.md").write_text(
        "---\nproject: FinanceOps\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    (vault / "inbox.md").write_text(
        f"# inbox\n\n- [ ] {_GATE_MARKER} 跨端回归闸门\n", encoding="utf-8"
    )
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@e.com"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-q", "-m", "chore: seed"],
    ):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    return vault


_GATE_MARKER = "【回归闸门验证件】deadbeef"


def _route_backed_http(vault: Path, tmp_path: Path) -> Any:
    """把闸门的 `http_json_tolerant` 接到**真实 router**（临时库），不联网、不碰真实库。"""
    import urllib.parse

    from fastapi.testclient import TestClient

    from summit_workbench.webapp.app import WebContext, create_app

    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    client = TestClient(create_app(ctx, static_dir=tmp_path / "no-static"))

    def fake_tolerant(url: str, *, payload: dict[str, object] | None = None, **_kwargs: object):
        resp = client.post(urllib.parse.urlparse(url).path, json=payload)
        return resp.status_code, resp.json()

    return fake_tolerant


def test_gate_journal_write_passes_against_real_route(
    gate: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    """[3/7] 在真实写入路径上必须全绿，并返回可清理的验证件信息。"""
    vault = _seed_gate_vault(tmp_path)
    monkeypatch.setattr(gate, "http_json_tolerant", _route_backed_http(vault, tmp_path))
    rep = gate.Report()

    probe = gate.gate_journal_write(rep, vault, "http://swb", "tok", "http://swb")

    assert rep.failures == []
    assert probe is not None
    assert probe.project == "FinanceOps"
    assert probe.path.startswith("logs/")
    assert (vault / probe.path).is_file()
    # 项目页本次确实变了（fixture 里它没有 activity_at）⇒ 判据要求它在同一个提交里
    # （缺陷 1 的精确判据）。
    assert f"projects/{probe.project}.md" in probe.files
    assert probe.path in probe.files
    assert gate.worktree_dirty(vault) == []


def test_gate_journal_write_tolerates_idempotent_project_page(
    gate: Any,
    tmp_path: Path,
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """同一天**第二次**写日志：项目页幂等不变 ⇒ 不得因此判 FAIL。

    这是 2026-09-19 真机实跑发现的**假阴性**：`_touch_projects_activity` 只刷 `activity_at`，
    而 `update_note_status` 的重写是幂等的 ⇒ 第二次写日志时项目页不再变化，"提交里没有项目页"
    是正确行为，老断言（恒要求它在提交里）却判 FAIL：
    `❌ 日志提交一并包含关联项目页 — HEAD 触及：['logs/2026-09-19-002.md']`。

    修法后：只有"内容确实变了"才要求它进提交。本用例走**真实 router** 连写两次，并断言
    ① 第二次项目页字节级不变（前提校验，否则测试会假绿）；② 走的是"未变化"分支；
    ③ 没有任何 FAIL，且 S-1(a) 的工作树干净是**真的**干净（不是靠放宽判据换来的）。
    """
    vault = _seed_gate_vault(tmp_path)
    monkeypatch.setattr(gate, "http_json_tolerant", _route_backed_http(vault, tmp_path))
    project_page = vault / "projects" / "FinanceOps.md"

    first = gate.Report()
    first_probe = gate.gate_journal_write(first, vault, "http://swb", "tok", "http://swb")
    assert first.failures == [], first.failures
    assert first_probe is not None
    assert f"projects/{first_probe.project}.md" in first_probe.files  # 第一次：页变了、进了提交
    after_first = project_page.read_bytes()
    capsys.readouterr()

    second = gate.Report()
    second_probe = gate.gate_journal_write(second, vault, "http://swb", "tok", "http://swb")
    output = capsys.readouterr().out

    assert project_page.read_bytes() == after_first, "前提：同一天第二次写入必须幂等"
    assert second_probe is not None and second_probe.path != first_probe.path  # 是**另一条**日志
    assert f"projects/{second_probe.project}.md" not in second_probe.files  # 没变 ⇒ 不进提交
    assert second.failures == [], second.failures
    assert "关联项目页本次未变化" in output  # 确实走了新分支
    assert gate.worktree_dirty(vault) == []


def test_gate_journal_write_fails_when_changed_paths_loses_the_project_page(
    gate: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    """反向护栏（变异靶）：漏列 changed_paths 的真实后果必须判 FAIL，且**不得**中断闸门。

    精确复刻缺陷的 git 现场：日志页已提交、项目页（activity_at）留在未提交状态，端点返回
    HTTP 500 `mutation_invariant` **且响应里没有 path**。要求：
    ① 不抛异常（`http_json` 会在 500 上 SystemExit，日志步骤必须用容错版，否则收尾会被跳过、
       验证件与脏改动留在使用者库里 —— 那正是最坏的结局）；
    ② "工作树仍然干净"判 FAIL；
    ③ 日志页路径能从 HEAD 反推出来，好让收尾仍能清理它。
    """
    import subprocess

    vault = _seed_gate_vault(tmp_path)
    project_page = vault / "projects" / "FinanceOps.md"

    def fake_tolerant(_url: str, **_kwargs: object) -> tuple[int, dict[str, object]]:
        # 复刻缺陷现场：日志页提交，项目页改脏但没进 changed_paths。
        log = vault / "logs" / "2026-09-19-001.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("# 日志\n\n## 关联\n\n- （无）\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(vault), "add", "logs"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(vault), "commit", "-q", "-m", "wb: journal/log [x]"],
            check=True,
            capture_output=True,
        )
        project_page.write_text(
            project_page.read_text(encoding="utf-8") + "<!-- 未提交的项目页改动 -->\n",
            encoding="utf-8",
        )
        return 500, {"ok": False, "code": "mutation_invariant", "message": "…未提交路径…"}

    monkeypatch.setattr(gate, "http_json_tolerant", fake_tolerant)
    rep = gate.Report()
    probe = gate.gate_journal_write(rep, vault, "http://swb", "tok", "http://swb")

    assert any("工作树仍然干净" in item for item in rep.failures), rep.failures
    assert any("journal/log 成功" in item for item in rep.failures), rep.failures
    assert any("关联项目页" in item for item in rep.failures), rep.failures
    assert probe is not None
    assert probe.path == "logs/2026-09-19-001.md"  # 从 HEAD 反推，收尾仍能清理
    # 收尾必须把项目页还原、清掉日志页，最终工作树干净。
    gate.gate_cleanup(rep, vault, _GATE_MARKER, True, push=False, journal=probe)
    assert gate.worktree_dirty(vault) == []
    assert not (vault / "logs" / "2026-09-19-001.md").exists()


def test_http_json_tolerant_returns_status_instead_of_exiting(gate: Any, monkeypatch: Any) -> None:
    """500 时容错版返回 ``(status, body)``；`http_json` 仍保持"醒目 SystemExit"不变。"""
    import email.message
    import io
    import urllib.error
    import urllib.request

    class _FailingOpener:
        def open(self, _req: object, timeout: int | None = None) -> object:
            raise urllib.error.HTTPError(
                "http://swb/api/journal/log",
                500,
                "Internal Server Error",
                email.message.Message(),
                io.BytesIO(b'{"ok": false, "code": "mutation_invariant"}'),
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _FailingOpener())
    status, body = gate.http_json_tolerant(
        "http://swb/api/journal/log", token="t", payload={"did": "x"}, header="X-WB-Session-Token"
    )
    assert status == 500
    assert body["code"] == "mutation_invariant"
    # 反向护栏：其它步骤仍依赖 http_json 的"非 2xx 就醒目退出"。
    with pytest.raises(SystemExit):
        gate.http_json(
            "http://swb/api/journal/log",
            token="t",
            payload={"did": "x"},
            header="X-WB-Session-Token",
        )


def test_gate_cleanup_removes_journal_artifact_and_restores_project_page(
    gate: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    """[8/8] 收尾：日志页删除、项目页还原成写入前内容、工作树干净。"""
    vault = _seed_gate_vault(tmp_path)
    project_page = vault / "projects" / "FinanceOps.md"
    before = project_page.read_text(encoding="utf-8")
    monkeypatch.setattr(gate, "http_json_tolerant", _route_backed_http(vault, tmp_path))

    rep = gate.Report()
    probe = gate.gate_journal_write(rep, vault, "http://swb", "tok", "http://swb")
    assert probe is not None and rep.failures == []
    assert (vault / probe.path).is_file()
    assert "activity_at" in project_page.read_text(encoding="utf-8")

    gate.gate_cleanup(rep, vault, _GATE_MARKER, True, push=False, journal=probe)

    assert rep.failures == []
    assert not (vault / probe.path).exists()
    assert project_page.read_text(encoding="utf-8") == before
    assert gate.worktree_dirty(vault) == []


# ─────── [4/8] 收件箱提升：纯判据 + 真实 router 脱机验证（第九阶段新增） ───────

_PROMOTE_MARKER = "【回归闸门验证件】feedface"
_PROMOTE_ENTRY_ID = "web-20260919120000000000"
_PROMOTE_COMMENT = "<!-- 在此追加，一行一条，形如：- [ ] 想法内容 #项目名 -->"


def _promote_inbox(*entries: str) -> str:
    """一个最小但形态正确的 `inbox.md`；`entries` 是「待处理条目」区里的正文块。"""
    lines = [
        "---",
        "date: 2026-09-01",
        "type: inbox",
        "status: active",
        "project: global",
        "---",
        "",
        "# 全局收件箱（inbox）",
        "",
        "## 待处理条目",
        "",
        _PROMOTE_COMMENT,
    ]
    for entry in entries:
        lines.append("")
        lines.append(entry.rstrip("\n"))
    # 结尾保留一个空行：真实 inbox.md 就是这样，也是收尾「逐字还原」要回到的形状。
    return "\n".join(lines) + "\n\n"


def _promote_entry_block() -> str:
    return (
        f"- [ ] #FinanceOps {_PROMOTE_MARKER} 跨端回归闸门\n"
        f"  <!-- wb-candidate: {_PROMOTE_ENTRY_ID} -->\n"
        "  <!-- wb-capture-kind: idea -->\n"
        "  <!-- wb-capture-project: FinanceOps -->\n"
    )


def test_target_page_problems_accepts_single_blank_and_single_marker(gate: Any) -> None:
    page = (
        f"# P\n\n## 下一步\n\n- 一件工作\n  <!-- wb-candidate: {_PROMOTE_ENTRY_ID} -->\n\n## 阻塞\n"
    )
    assert gate.target_page_problems(page, _PROMOTE_ENTRY_ID) == []


def test_target_page_problems_flags_double_blank(gate: Any) -> None:
    """⑦ 的判据：新增段与下一个 `##` 区块之间只允许一个空行（第七阶段真机事故）。"""
    page = (
        f"# P\n\n## 下一步\n\n- 一件工作\n"
        f"  <!-- wb-candidate: {_PROMOTE_ENTRY_ID} -->\n\n\n## 阻塞\n"
    )
    problems = gate.target_page_problems(page, _PROMOTE_ENTRY_ID)
    assert any("双空行" in item for item in problems)


@pytest.mark.parametrize("count", [0, 2])
def test_target_page_problems_flags_marker_count_not_one(gate: Any, count: int) -> None:
    """幂等键必须出现且只出现一次（重复批准不得重复追加 / 写丢了要能发现）。"""
    marker = f"  <!-- wb-candidate: {_PROMOTE_ENTRY_ID} -->\n"
    page = "# P\n\n## 下一步\n\n" + (marker * count) + "\n## 阻塞\n"
    problems = gate.target_page_problems(page, _PROMOTE_ENTRY_ID)
    assert any(f"出现 {count} 次" in item for item in problems)


def test_inbox_after_promotion_problems_accepts_removed_entry(gate: Any) -> None:
    """条目移出后：正文标记消失、解析不到、无双空行、无占位行。"""
    inbox = _promote_inbox()
    assert gate.inbox_after_promotion_problems(inbox, _PROMOTE_ENTRY_ID, _PROMOTE_MARKER) == []


def test_inbox_after_promotion_problems_flags_stale_entry(gate: Any) -> None:
    """仍能解析到条目 / 正文标记还在 ⇒ 必须报出来（条目没被移出）。"""
    inbox = _promote_inbox(_promote_entry_block())
    problems = gate.inbox_after_promotion_problems(inbox, _PROMOTE_ENTRY_ID, _PROMOTE_MARKER)
    assert any("仍在 inbox.md" in item for item in problems)
    assert any("仍能被解析到" in item for item in problems)


def test_inbox_after_promotion_problems_flags_double_blank(gate: Any) -> None:
    inbox = _promote_inbox().replace("## 待处理条目\n\n", "## 待处理条目\n\n\n\n")
    problems = gate.inbox_after_promotion_problems(inbox, _PROMOTE_ENTRY_ID, _PROMOTE_MARKER)
    assert any("双空行" in item for item in problems)


def test_inbox_after_promotion_problems_flags_empty_checkbox_placeholder(gate: Any) -> None:
    """「不留占位行」：空的 `- [ ] ` 行必须被抓住。"""
    inbox = _promote_inbox("- [ ]")
    problems = gate.inbox_after_promotion_problems(inbox, _PROMOTE_ENTRY_ID, _PROMOTE_MARKER)
    assert any("占位行" in item for item in problems)


def test_missing_from_commit_reports_only_absent_paths(gate: Any) -> None:
    assert gate.missing_from_commit(["a.md", "b.md"], ["a.md", "b.md"]) == []
    assert gate.missing_from_commit(["a.md"], ["a.md", "b.md"]) == ["b.md"]


def _seed_promote_vault(tmp_path: Path) -> tuple[Path, str, str]:
    """建一个已提交的 git vault：capture 验证件在 `## 待处理条目` 区里 + 一个项目页。

    返回 ``(vault, 无条目的 inbox 基线, 项目页基线)``——收尾后必须逐字回到这两个基线。
    """
    import subprocess

    from summit_workbench.repositories.writeback import append_global_inbox

    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    page = (
        "---\nproject: FinanceOps\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n\n## 跟进事项\n"
    )
    (vault / "projects" / "FinanceOps.md").write_text(page, encoding="utf-8")
    base_inbox = _promote_inbox()
    (vault / "inbox.md").write_text(base_inbox, encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@e.com"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-q", "-m", "chore: seed"],
    ):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    # 用真实写入口追加 capture 验证件并提交（与 [2/8] 的落盘形态一致）。
    append_global_inbox(
        vault,
        f"#FinanceOps {_PROMOTE_MARKER} 跨端回归闸门",
        _PROMOTE_ENTRY_ID,
        markers=["wb-capture-kind: idea", "wb-capture-project: FinanceOps"],
    )
    for args in (["add", "-A"], ["commit", "-q", "-m", "wb: capture"]):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    return vault, base_inbox, page


def test_gate_promote_to_project_passes_against_real_route(
    gate: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    """[4/8] 在真实提升路径上必须全绿，并能在 [8/8] 逐字还原项目页与 inbox.md。"""
    vault, base_inbox, base_page = _seed_promote_vault(tmp_path)
    monkeypatch.setattr(gate, "http_json_tolerant", _route_backed_http(vault, tmp_path))
    rep = gate.Report()

    probe = gate.gate_promote(rep, vault, "http://swb", "tok", "http://swb", _PROMOTE_MARKER)

    assert rep.failures == [], rep.failures
    assert probe is not None
    assert probe.project == "FinanceOps"
    assert probe.entry_id == _PROMOTE_ENTRY_ID
    assert "inbox.md" in probe.files and "projects/FinanceOps.md" in probe.files
    assert gate.worktree_dirty(vault) == []
    page_after = (vault / "projects" / "FinanceOps.md").read_text(encoding="utf-8")
    assert page_after.count(f"<!-- wb-candidate: {_PROMOTE_ENTRY_ID} -->") == 1
    assert "\n\n\n" not in page_after
    assert _PROMOTE_MARKER not in (vault / "inbox.md").read_text(encoding="utf-8")

    gate.gate_cleanup(rep, vault, _PROMOTE_MARKER, True, push=False, promote=probe)

    assert rep.failures == []
    assert (vault / "projects" / "FinanceOps.md").read_text(encoding="utf-8") == base_page
    assert (vault / "inbox.md").read_text(encoding="utf-8") == base_inbox
    assert gate.worktree_dirty(vault) == []
