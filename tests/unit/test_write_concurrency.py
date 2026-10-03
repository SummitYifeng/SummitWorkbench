"""P0 写路径并发加固验收（HANDOFF_HARDENING P0）。

T1 两个线程并发 set_decision（不同候选）→ 两个裁决都保留（此前必丢一个）。
T2 apply_meeting_review（apply=True）进行中并发 set_decision → 收尾后并发裁决保留（P0-5）。
T3 两个线程并发 append_global_inbox（不同 candidate_id）→ 两条都在。
T4 并发 append_work_log 同日多条 → 不同文件名、均完整（P0-4）。
T5 write_brief 与 mark_task_completed 并发 → 快照与当日笔记都完整（P0-6 语义）。
T6 review_audit 日志含一条半截行 → 幂等判定不崩、坏行进 quarantine（P0-3）。
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories._jsonl import CorruptLogLine
from summit_workbench.repositories.daily_note import (
    BRIEF_END,
    BRIEF_START,
    daily_note_path,
    write_brief,
)
from summit_workbench.repositories.review_audit import (
    ExecutionRecord,
    append_execution,
    completed_decisions,
    completed_ids,
)
from summit_workbench.repositories.review_edit import set_decision
from summit_workbench.repositories.review_page import (
    parse_review_page,
    render_review_page,
    review_path,
)
from summit_workbench.repositories.signal_snapshot import (
    mark_task_completed,
    read_snapshot,
    write_snapshot,
)
from summit_workbench.repositories.thread_notes import append_work_log
from summit_workbench.repositories.writeback import append_global_inbox
from summit_workbench.workflows.review_apply import apply_meeting_review


def _entry(
    cid: str,
    *,
    decision: CandidateDecision = CandidateDecision.PENDING,
    route: RouteTarget = RouteTarget.PROJECT_MAIN,
    project: str = "P1",
    due: str | None = None,
) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=cid,
        kind=CandidateKind.ACTION_ITEM,
        description=f"做 {cid}",
        target_project=project,
        route=route,
        evidence=EvidenceRef(anchor="木子 00:03"),
        due_date=due,
        is_next_step=True,
        decision=decision,
    )
    return ReviewEntry(
        candidate,
        f"original-{cid}",
        "2026-09-02",
        "沟通会",
        "[[meetings/notes/note]]",
        "[[transcript]]",
    )


def _seed_page(vault: Path, entries: list[ReviewEntry]) -> Path:
    path = review_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_review_page(entries), encoding="utf-8")
    return path


def _run_threads(jobs: list[tuple[threading.Thread, list[BaseException]]]) -> None:
    for thread, _errors in jobs:
        thread.start()
    for thread, errors in jobs:
        thread.join(timeout=30)
        assert not thread.is_alive(), "工作线程超时未结束"
        if errors:
            raise errors[0]


# ---- T1：并发单条裁决不互丢 ----


def test_t1_concurrent_set_decision_keeps_both(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _seed_page(vault, [_entry("m1#decision-0"), _entry("m1#decision-1")])
    errors_a: list[BaseException] = []
    errors_b: list[BaseException] = []

    def decide_a() -> None:
        try:
            set_decision(vault, "m1#decision-0", CandidateDecision.APPROVED)
        except BaseException as exc:  # noqa: BLE001 - 测试线程内收集后主线程重抛
            errors_a.append(exc)

    def decide_b() -> None:
        try:
            set_decision(vault, "m1#decision-1", CandidateDecision.APPROVED)
        except BaseException as exc:  # noqa: BLE001
            errors_b.append(exc)

    _run_threads(
        [
            (threading.Thread(target=decide_a), errors_a),
            (threading.Thread(target=decide_b), errors_b),
        ]
    )
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    by_id = {e.candidate.candidate_id: e.candidate.decision for e in parsed.entries}
    assert by_id["m1#decision-0"] is CandidateDecision.APPROVED
    assert by_id["m1#decision-1"] is CandidateDecision.APPROVED


# ---- T3：并发 append_global_inbox ----


def test_t3_concurrent_append_global_inbox_keeps_both(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    errors_a: list[BaseException] = []
    errors_b: list[BaseException] = []

    def append_a() -> None:
        try:
            append_global_inbox(vault, "想法 A", "web-a", markers=["wb-capture-kind: idea"])
        except BaseException as exc:  # noqa: BLE001
            errors_a.append(exc)

    def append_b() -> None:
        try:
            append_global_inbox(vault, "想法 B", "web-b", markers=["wb-capture-kind: task"])
        except BaseException as exc:  # noqa: BLE001
            errors_b.append(exc)

    _run_threads(
        [
            (threading.Thread(target=append_a), errors_a),
            (threading.Thread(target=append_b), errors_b),
        ]
    )
    text = (vault / "inbox.md").read_text(encoding="utf-8")
    assert "- [ ] 想法 A" in text
    assert "- [ ] 想法 B" in text
    assert "<!-- wb-candidate: web-a -->" in text
    assert "<!-- wb-candidate: web-b -->" in text


# ---- T4：并发推进日志序号不撞 ----


def _mk_project(vault: Path, project: str) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nproject: " + project + "\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "updated: '2026-09-01'\n---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n"
        "## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )


def test_t4_concurrent_work_logs_distinct_filenames(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    day = datetime(2026, 9, 3, 12, tzinfo=UTC)
    errors: list[BaseException] = []

    def write_log(text: str) -> None:
        try:
            append_work_log(vault, projects=["FinanceOps"], text=text, now=day)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write_log, args=(f"并发日志甲{i}",)) for i in range(6)]
    _run_threads([(t, errors) for t in threads])
    logs = sorted((vault / "logs").glob("2026-09-03-*.md"))
    assert len(logs) == 6  # 每个线程一条，互不覆盖
    assert len({p.name for p in logs}) == 6
    for path in logs:
        assert "## 原文" in path.read_text(encoding="utf-8")  # 完整落盘
    # 关联档案 activity_at 被并发刷到同日不丢；updated（实质更新语义）不被日志写入
    archive = (vault / "projects" / "FinanceOps.md").read_text(encoding="utf-8")
    assert "updated: '2026-09-01'" in archive
    assert "activity_at: '2026-09-03'" in archive


# ---- T2：apply 收尾乐观合并（P0-5） ----


def _feishu_page(vault: Path, entries: list[ReviewEntry]) -> None:
    _seed_page(vault, entries)


def test_t2_apply_preserves_concurrent_decision_interleaved(tmp_path: Path) -> None:
    """apply 执行期间用户并发批准另一候选 → 收尾后并发裁决保留、本次执行候选被移除。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _seed_page(
        vault,
        [
            _entry(
                "m1#task-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.FEISHU_TASK,
                due="2026-09-04",
            ),
            _entry(
                "m1#task-1",
                decision=CandidateDecision.PENDING,
                route=RouteTarget.FEISHU_TASK,
                due="2026-09-04",
            ),
        ],
    )
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    errors: list[BaseException] = []

    def creator(summary: str, due_date: str | None, candidate_id: str) -> str:
        calls.append(candidate_id)
        started.set()
        assert release.wait(timeout=15)
        return f"guid-{candidate_id}"

    def run_apply() -> None:
        try:
            apply_meeting_review(
                vault,
                work,
                apply=True,
                task_creator=creator,
                now=datetime(2026, 9, 2, tzinfo=UTC),
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=run_apply)
    worker.start()
    try:
        assert started.wait(timeout=15), "apply 未进入 task_creator（外部写回阶段）"
        # apply 被外部写回阻塞时，用户并发批准另一条候选（不同 id）
        set_decision(vault, "m1#task-1", CandidateDecision.APPROVED)
    finally:
        release.set()
    worker.join(timeout=30)
    assert not worker.is_alive(), "apply 线程超时未结束"
    if errors:
        raise errors[0]

    assert calls == ["m1#task-0"]  # 不重复执行
    page = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    by_id = {e.candidate.candidate_id: e for e in page.entries}
    # 本次 handled 且未变 → 已从页上移除；并发裁决保留
    assert "m1#task-0" not in by_id
    assert by_id["m1#task-1"].candidate.decision is CandidateDecision.APPROVED
    # 账本只记了 task-0 一次
    ledger = vault / "_signals" / "review-actions" / "log.jsonl"
    applied = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(applied) == 1


def test_t2_apply_keeps_concurrently_edited_candidate(tmp_path: Path) -> None:
    """apply 执行中同一条候选被用户改回 pending → 留在页上，不被整页重写吞掉。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _seed_page(
        vault,
        [
            _entry(
                "m1#task-0",
                decision=CandidateDecision.APPROVED,
                route=RouteTarget.FEISHU_TASK,
                due="2026-09-04",
            )
        ],
    )
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def creator(summary: str, due_date: str | None, candidate_id: str) -> str:
        started.set()
        assert release.wait(timeout=15)
        return f"guid-{candidate_id}"

    def run_apply() -> None:
        try:
            apply_meeting_review(
                vault,
                work,
                apply=True,
                task_creator=creator,
                now=datetime(2026, 9, 2, tzinfo=UTC),
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=run_apply)
    worker.start()
    try:
        assert started.wait(timeout=15)
        set_decision(vault, "m1#task-0", CandidateDecision.PENDING)  # 用户反悔
    finally:
        release.set()
    worker.join(timeout=30)
    assert not worker.is_alive()
    if errors:
        raise errors[0]
    page = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    by_id = {e.candidate.candidate_id: e for e in page.entries}
    assert by_id["m1#task-0"].candidate.decision is CandidateDecision.PENDING


# ---- T5：write_brief 与 mark_task_completed 并发（P0-6 语义） ----


def test_t5_brief_and_task_completion_files_intact(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    day = "2026-09-03"
    guid = "task-guid-1"
    write_snapshot(
        vault,
        day,
        {"date": day, "task_list": [{"task_id": guid, "summary": "任务一"}], "actions": []},
    )
    errors: list[BaseException] = []

    def brief_writer() -> None:
        try:
            for i in range(40):
                write_brief(vault, day, f"简报正文 第{i}次\n内容完整")
                write_snapshot(
                    vault,
                    day,
                    {
                        "date": day,
                        "task_list": [{"task_id": guid, "summary": "任务一"}],
                        "actions": [],
                    },
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def completer() -> None:
        try:
            for _ in range(30):
                mark_task_completed(vault, day, guid)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=brief_writer)
    t2 = threading.Thread(target=completer)
    _run_threads([(t1, errors), (t2, errors)])
    # 当日简报：锚点区块完整（BRIEF:START/END 各出现一次 = 无交错半截）；
    # 简报自 2026-09-19 起写在本机程序目录（不在 vault 内）。
    note_text = daily_note_path(vault, day).read_text(encoding="utf-8")
    assert note_text.count(BRIEF_START) == 1
    assert note_text.count(BRIEF_END) == 1
    assert "---" in note_text  # frontmatter 完整
    # 快照：可解析、带 schema_version、结构完整
    snapshot = read_snapshot(vault, day)
    assert snapshot is not None
    assert snapshot.get("schema_version") == 1
    assert "task_list" in snapshot


# ---- T6：幂等账本容错读 ----


def test_t6_corrupt_ledger_line_does_not_break_idempotence(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "P1")
    record = ExecutionRecord(
        timestamp="2026-09-02T00:00:00+00:00",
        candidate_id="m1#decision-0",
        decision="approved",
        ai_original="原文",
        final_description="原文",
        target_project="P1",
        route="project-main",
        due_date=None,
        destination=str(vault / "projects" / "P1.md"),
        result="applied",
    )
    append_execution(vault, record)
    # 手动追加一条半截行（模拟被 kill 留下的坏行）
    ledger = vault / "_signals" / "review-actions" / "log.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(
            '{"timestamp": "2026-09-02T00:00:01+00:00", "candidate_id": "m1#decision-1", "deci'
        )
    with pytest.warns(CorruptLogLine):
        ids = completed_ids(vault)
    assert "m1#decision-0" in ids
    # 坏行被隔离、原日志未被改动（非破坏性）
    quarantine = vault / "_signals" / "review-actions" / "log.jsonl.quarantine"
    assert quarantine.is_file()
    assert "deci" in quarantine.read_text(encoding="utf-8")
    # completed_decisions 同样容错
    with pytest.warns(CorruptLogLine):
        decisions = completed_decisions(vault, "m1")
    assert CandidateDecision.APPROVED in decisions
    # apply 幂等判定不崩：第二次 apply 把已执行候选当 already-completed，不重复写回
    # （内部 completed_ids 再读坏行 → 仍只告警不崩，测试内吞掉告警避免污染汇总）
    _seed_page(vault, [_entry("m1#decision-0", decision=CandidateDecision.APPROVED)])
    with pytest.warns(CorruptLogLine):
        report = apply_meeting_review(vault, tmp_path / "work", apply=True)
    assert report.applied == 0
    assert report.failed == 0
    assert report.actions[0].reason == "already-completed"
