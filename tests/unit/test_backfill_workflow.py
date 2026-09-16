"""M1-7：本地逐字稿补导——扫描/日期过滤/续跑、处理与 historical 候选。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import SecretStr

from summit_workbench.domain.pipeline import (
    MeetingTask,
    ProcessingState,
    SourceKind,
    local_idempotency_key,
)
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.repositories.meeting_state import record_task
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.workflows.local_mutation import run_local_mutation
from summit_workbench.workflows.meetings.backfill import (
    MAX_TRANSCRIPT_BYTES,
    oversized_transcripts,
    run_backfill,
    scan_for_import,
    scan_local_transcripts,
)

CFG = ModelConfig("meeting", "test-model", "https://example.test", "shared")
PROCESSOR = Prompt("meeting-processor", 2, "meeting", "extract")
MERGER = Prompt("meeting-merger", 1, "meeting", "merge")


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "transcripts"
    src.mkdir()
    (src / "2026-08-20-会议A.md").write_text("张三 00:01 讨论了网课账户。", encoding="utf-8")
    (src / "2026-09-05-会议B.md").write_text("李四 00:02 讨论了后勤。", encoding="utf-8")
    return src


def test_scan_for_import_accepts_txt_and_no_date_range(tmp_path):
    src = tmp_path / "drop"
    src.mkdir()
    # .txt、无 frontmatter、文件名带日期前缀
    (src / "2026-08-31-财务对齐.txt").write_text("张三 00:01 讨论预算。", encoding="utf-8")
    # .txt、文件名无日期 → 回退文件 mtime，仍应被收录
    (src / "随手记.txt").write_text("李四 00:02 讨论排期。", encoding="utf-8")
    items = scan_for_import(tmp_path / "vault", src)
    assert len(items) == 2
    by_title = {item.title: item for item in items}
    assert by_title["财务对齐"].date == "2026-08-31"
    assert "随手记" in by_title  # 无日期名也不丢
    assert all(len(item.date) == 10 for item in items)  # 都得到了 YYYY-MM-DD


def test_oversized_transcript_is_skipped_by_both_scanners_and_listed(tmp_path):
    """体积上限必须由 workflow 层执行。

    此前只有 web 上传路径检查 10 MiB，CLI 完全没有，能把任意大文件直接送进模型
    （实测一个 12 MiB 文件预估 419 万 input token）。这里锁住「两个扫描函数都跳过」
    以及「能被显式列出」，避免退回静默放行或静默丢弃。
    """
    src = tmp_path / "drop"
    src.mkdir()
    (src / "2026-08-20-正常.md").write_text("张三 00:01 讨论网课。", encoding="utf-8")
    huge = src / "2026-08-21-超大.md"
    huge.write_bytes(b"x" * (MAX_TRANSCRIPT_BYTES + 1))

    imported = scan_for_import(tmp_path / "vault", src)
    assert [item.path.name for item in imported] == ["2026-08-20-正常.md"]

    ranged = scan_local_transcripts(tmp_path / "vault", src, since="2026-01-01", until="2026-12-31")
    assert [item.path.name for item in ranged] == ["2026-08-20-正常.md"]

    assert [p.name for p in oversized_transcripts(src)] == ["2026-08-21-超大.md"]


def test_transcript_exactly_at_the_limit_is_accepted(tmp_path):
    """边界：等于上限应放行，只有「超过」才拦。"""
    src = tmp_path / "drop"
    src.mkdir()
    exact = src / "2026-08-22-边界.md"
    exact.write_bytes(b"y" * MAX_TRANSCRIPT_BYTES)

    assert [p.name for p in oversized_transcripts(src)] == []
    assert [item.path.name for item in scan_for_import(tmp_path / "vault", src)] == [
        "2026-08-22-边界.md"
    ]


def _ok_client(*, with_decision: bool = False) -> httpx.Client:
    decisions = (
        [{"description": "采用方案A", "target_project": None, "evidence": "张三 00:01"}]
        if with_decision
        else []
    )
    content = json.dumps(
        {
            "one_minute_summary": "摘要",
            "facts": [{"text": "讨论", "evidence": "张三 00:01"}],
            "decisions": decisions,
            "action_items": [],
            "open_questions": [],
            "ai_suggestions": [],
        },
        ensure_ascii=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _bad_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_scan_filters_by_date_range(tmp_path):
    vault = tmp_path / "vault"
    items = scan_local_transcripts(vault, _src(tmp_path), since="2026-08-01", until="2026-08-31")
    assert [i.date for i in items] == ["2026-08-20"]
    assert items[0].title == "会议A"
    assert items[0].done is False
    assert items[0].input_tokens > 0


def test_scan_marks_done_from_state_ledger(tmp_path):
    vault = tmp_path / "vault"
    src = _src(tmp_path)
    text = (src / "2026-08-20-会议A.md").read_text(encoding="utf-8")
    key = local_idempotency_key(text)
    record_task(
        vault,
        MeetingTask(idem_key=key, source=SourceKind.LOCAL_FILE, state=ProcessingState.PROCESSED),
    )
    items = scan_local_transcripts(vault, src, since="2026-08-01", until="2026-08-31")
    assert items[0].done is True


def test_run_processes_pending_and_skips_done(tmp_path):
    vault = tmp_path / "vault"
    src = _src(tmp_path)
    items = scan_local_transcripts(vault, src, since="2026-01-01", until="2026-12-31")
    report = run_backfill(
        vault,
        items,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
    )
    assert report.processed == 2
    assert report.failed == 0
    assert report.candidates == 0  # 默认不生成候选
    # 续跑：再次运行全部跳过
    items2 = scan_local_transcripts(vault, src, since="2026-01-01", until="2026-12-31")
    assert all(i.done for i in items2)
    report2 = run_backfill(
        vault,
        items2,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
    )
    assert report2.processed == 0
    assert report2.skipped == 2


def test_include_actions_generates_historical_candidates(tmp_path):
    vault = tmp_path / "vault"
    items = scan_local_transcripts(vault, _src(tmp_path), since="2026-08-01", until="2026-08-31")
    report = run_backfill(
        vault,
        items,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        include_actions=True,
        client=_ok_client(with_decision=True),
        sleep=lambda _: None,
    )
    assert report.processed == 1
    assert report.candidates == 1
    parsed = parse_review_page(review_path(vault).read_text(encoding="utf-8"))
    assert parsed.entries[0].candidate.historical is True


def test_failed_processing_is_reported(tmp_path):
    vault = tmp_path / "vault"
    items = scan_local_transcripts(vault, _src(tmp_path), since="2026-08-01", until="2026-08-31")
    report = run_backfill(
        vault,
        items,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_bad_client(),
        sleep=lambda _: None,
    )
    assert report.failed == 1
    assert report.processed == 0


def test_backfill_reports_local_transaction_ids_and_keeps_model_call_outside_lock(tmp_path):
    vault = tmp_path / "vault"
    src = _src(tmp_path)
    items = scan_local_transcripts(vault, src, since="2026-08-01", until="2026-08-31")

    report = run_backfill(
        vault,
        items,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
        local_mutation=run_local_mutation,
    )

    assert report.processed == 1
    assert len(report.operation_ids) == 2
    assert len(set(report.operation_ids)) == 2


def test_backfill_accepts_mutation_runtime_runner(tmp_path):
    """Web 注入的 MutationRuntime.run 使用二参数契约，也必须跑完整导入链路。"""
    vault = tmp_path / "vault"
    src = _src(tmp_path)
    items = scan_local_transcripts(vault, src, since="2026-08-01", until="2026-08-31")

    def runtime_run(action, mutation):
        return run_local_mutation(vault, action, mutation)

    report = run_backfill(
        vault,
        items,
        CFG,
        SecretStr("k"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
        local_mutation=runtime_run,
    )

    assert report.processed == 1
    assert report.failed == 0
    assert len(report.operation_ids) == 2
