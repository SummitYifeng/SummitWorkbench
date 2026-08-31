"""M1-3 归档原文到结构化笔记的状态、错误队列与恢复测试。"""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from summit_workbench.domain.pipeline import ProcessingState, SourceKind
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.repositories.meeting_state import latest_task
from summit_workbench.workflows.meetings import (
    DiscoveredMeeting,
    archive_meeting,
    process_archived_transcript,
)

CFG = ModelConfig("meeting", "test-model", "https://example.test", "shared")
PROCESSOR = Prompt("meeting-processor", 2, "meeting", "extract")
MERGER = Prompt("meeting-merger", 1, "meeting", "merge")


def _archived(tmp_path):
    meeting = DiscoveredMeeting(
        title="周会",
        date="2026-08-31",
        source=SourceKind.FEISHU_NOTE,
        meeting_id="m1",
        note_id="n1",
    )
    return archive_meeting(tmp_path, meeting, lambda _: "张三 00:01 项目完成")


def _ok_client() -> httpx.Client:
    content = json.dumps(
        {
            "one_minute_summary": "项目完成",
            "facts": [{"text": "项目完成", "evidence": "张三 00:01"}],
            "decisions": [],
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


def test_success_writes_note_usage_and_advances_pending_review(tmp_path):
    archived = _archived(tmp_path)
    assert archived.path is not None
    report = process_archived_transcript(
        tmp_path,
        archived.path,
        CFG,
        SecretStr("secret"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
    )
    assert report.action == "processed"
    assert report.note_path is not None and report.note_path.is_file()
    assert report.state == ProcessingState.PENDING_REVIEW
    assert latest_task(tmp_path, "m1:n1").state == ProcessingState.PENDING_REVIEW  # type: ignore[union-attr]
    assert list((tmp_path / "_signals" / "model-usage").glob("*.jsonl"))
    rerun = process_archived_transcript(
        tmp_path,
        archived.path,
        CFG,
        SecretStr("secret"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
    )
    assert rerun.action == "skipped-existing"


def test_exhaustion_queues_error_without_note_then_retry_recovers(tmp_path):
    archived = _archived(tmp_path)
    assert archived.path is not None
    calls = {"count": 0}

    def unavailable(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    failed = process_archived_transcript(
        tmp_path,
        archived.path,
        CFG,
        SecretStr("secret"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=httpx.Client(transport=httpx.MockTransport(unavailable)),
        sleep=lambda _: None,
    )
    assert calls["count"] == 4
    assert failed.action == "failed"
    assert failed.error_path is not None and failed.error_path.is_file()
    assert not list((tmp_path / "meetings" / "notes").glob("*.md"))
    assert latest_task(tmp_path, "m1:n1").state == ProcessingState.FAILED  # type: ignore[union-attr]

    recovered = process_archived_transcript(
        tmp_path,
        archived.path,
        CFG,
        SecretStr("secret"),
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        client=_ok_client(),
        sleep=lambda _: None,
    )
    assert recovered.state == ProcessingState.PENDING_REVIEW
    assert failed.error_path.exists() is False
