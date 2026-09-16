"""会议处理工作流契约测试：结构化成功 + schema 违规显式报错。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig, ModelPricing
from summit_workbench.workflows.meetings import ProcessingFailure, process_transcript

CFG = ModelConfig(
    capability="meeting",
    model_id="test-model",
    base_url="https://api.example.com/v1",
    credential_account="shared",
    pricing=ModelPricing(input_per_mtok=1.0, output_per_mtok=2.0),
)
PROMPT = Prompt(name="meeting-processor", version=1, capability="meeting", body="提取为 JSON")


def _client(content: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 5000, "completion_tokens": 800},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_process_valid_json():
    import json

    good = json.dumps(
        {
            "one_minute_summary": "ok",
            "facts": [{"text": "a", "evidence": "张三 00:01"}],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "ai_suggestions": [],
        }
    )
    processed = process_transcript(
        CFG,
        SecretStr("sk"),
        "张三 00:01 大家好",
        prompt=PROMPT,
        task_key="t1",
        client=_client(good),
        sleep=lambda _: None,
    )
    assert processed.extraction.one_minute_summary == "ok"
    assert processed.extraction.facts[0].text == "a"
    assert processed.usage.input_tokens == 5000
    assert processed.usage.output_tokens == 800
    # 费用：5000*1 + 800*2 = 6600 → /1e6
    assert processed.usage.estimated_cost == round(6600 / 1_000_000, 6)
    assert processed.prompt_version == "meeting-processor@v1"


def test_process_invalid_json_raises_schema_error():
    with pytest.raises(ProcessingFailure) as error:
        process_transcript(
            CFG,
            SecretStr("sk"),
            "t",
            prompt=PROMPT,
            task_key="t2",
            client=_client("not json at all"),
            sleep=lambda _: None,
        )
    assert error.value.attempts == 2


def test_process_missing_required_field_raises():
    with pytest.raises(ProcessingFailure) as error:
        process_transcript(
            CFG,
            SecretStr("sk"),
            "t",
            prompt=PROMPT,
            task_key="t3",
            client=_client('{"facts": []}'),  # 缺 one_minute_summary
            sleep=lambda _: None,
        )
    assert error.value.attempts == 2
