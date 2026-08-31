"""M1-3：token 分段、层级合并与任务级重试。"""

from __future__ import annotations

import json

import httpx
from pydantic import SecretStr

from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.workflows.meetings import process_transcript, split_transcript

PROCESSOR = Prompt("meeting-processor", 2, "meeting", "extract")
MERGER = Prompt("meeting-merger", 1, "meeting", "merge")


def _valid(summary: str = "ok") -> str:
    return json.dumps(
        {
            "one_minute_summary": summary,
            "facts": [{"text": "进展", "evidence": "张三 00:01"}],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "ai_suggestions": [],
        },
        ensure_ascii=False,
    )


def _response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def test_split_prefers_paragraph_boundaries():
    chunks = split_transcript("第一段 00:01\n\n第二段 00:02\n\n第三段 00:03", 12)
    assert len(chunks) >= 2
    assert chunks[0].startswith("[段落 1]")
    assert any("[段落 3]" in chunk for chunk in chunks)


def test_split_uses_speaker_lines_before_character_fallback():
    transcript = "\n".join(["张三 00:01 " + "甲" * 18, "李四 00:02 " + "乙" * 18])
    chunks = split_transcript(transcript, 26)
    assert len(chunks) == 2
    assert "李四" not in chunks[0]
    assert chunks[1].endswith("乙" * 18)


def test_schema_failure_retries_same_model_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return _response("not-json")
        return _response(_valid())

    cfg = ModelConfig("meeting", "m", "https://example.test", "shared")
    result = process_transcript(
        cfg,
        SecretStr("secret"),
        "张三 00:01 开始",
        prompt=PROCESSOR,
        task_key="task",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    assert calls["count"] == 3
    assert len(result.usage_records) == 3
    assert result.usage.attempts == 3


def test_long_transcript_is_chunked_and_merged():
    systems: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        systems.append(payload["messages"][0]["content"])
        return _response(_valid())

    cfg = ModelConfig(
        "meeting",
        "m",
        "https://example.test",
        "shared",
        max_output_tokens=30,
        context_window_tokens=180,
        context_safety_ratio=0.8,
    )
    transcript = "\n\n".join(f"张三 00:0{i} " + "进展" * 35 for i in range(1, 4))
    result = process_transcript(
        cfg,
        SecretStr("secret"),
        transcript,
        prompt=PROCESSOR,
        merger_prompt=MERGER,
        task_key="long",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    assert result.chunk_count > 1
    assert systems.count("extract") == result.chunk_count
    assert "merge" in systems
    assert len(result.usage_records) > result.chunk_count
