"""会议逐字稿 → 结构化提取的编排。

串起：加载 prompt → 调用会议模型（严格 JSON）→ 校验 schema → 生成用量记录。
不写 vault、不写飞书；仅返回结果对象，落盘由调用方（CLI/上层）决定。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from pydantic import SecretStr, ValidationError

from summit_workbench.domain.meeting import MeetingExtraction
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMSchemaError
from summit_workbench.providers.llm.usage import UsageRecord, record_from_result


@dataclass(frozen=True)
class ProcessedMeeting:
    extraction: MeetingExtraction
    usage: UsageRecord
    prompt_version: str


def process_transcript(
    cfg: ModelConfig,
    api_key: SecretStr,
    transcript: str,
    *,
    prompt: Prompt,
    task_key: str,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] | None = None,
) -> ProcessedMeeting:
    """用会议模型把 ``transcript`` 结构化为 :class:`MeetingExtraction`。

    模型输出必须是符合 schema 的 JSON；不符合即抛 :class:`LLMSchemaError`，
    绝不返回半成品（L41/NFR-6）。同时产出可审计的用量记录。
    """
    if sleep is None:
        model = ModelClient(cfg, api_key, client=client)
    else:
        model = ModelClient(cfg, api_key, client=client, sleep=sleep)

    result = model.complete(prompt.body, transcript, json_mode=True)

    try:
        extraction = MeetingExtraction.model_validate_json(result.text)
    except ValidationError as exc:
        raise LLMSchemaError(f"模型输出不符合会议 schema：{exc.error_count()} 处校验错误") from exc

    usage = record_from_result(cfg, result, task_key=task_key)
    return ProcessedMeeting(extraction=extraction, usage=usage, prompt_version=prompt.version_label)
