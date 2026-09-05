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
