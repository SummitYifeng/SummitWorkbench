"""会议逐字稿的可靠结构化处理：token 预算、分段、合并、重试与 schema 校验。"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import httpx
from pydantic import SecretStr, ValidationError

from summit_workbench.domain.meeting import MeetingExtraction
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import MAX_RETRIES, ModelClient, is_retryable
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMError, LLMSchemaError
from summit_workbench.providers.llm.usage import UsageRecord, record_from_result

_BACKOFF_BASE = 0.5


class ProcessingFailure(LLMError):
    """一个处理阶段在同一模型上耗尽重试，且没有可保存的半成品。"""

    def __init__(self, message: str, *, attempts: int, stage: str) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.stage = stage


class OutputTruncated(ProcessingFailure):
    """模型明确因达到输出上限结束；调用方必须缩小输入后再处理。"""


@dataclass(frozen=True)
class ProcessedMeeting:
    extraction: MeetingExtraction
    usage_records: tuple[UsageRecord, ...]
    prompt_version: str
    chunk_count: int = 1

    @property
    def usage(self) -> UsageRecord:
        """兼容单次调用展示；分段时返回本任务的聚合用量。"""
        first = self.usage_records[0]
        attempts_by_stage: dict[str, int] = {}
        for row in self.usage_records:
            attempts_by_stage[row.task_key] = max(
                attempts_by_stage.get(row.task_key, 0), row.attempts
            )
        return replace(
            first,
            input_tokens=sum(row.input_tokens for row in self.usage_records),
            output_tokens=sum(row.output_tokens for row in self.usage_records),
            attempts=sum(attempts_by_stage.values()),
            estimated_cost=round(sum(row.estimated_cost for row in self.usage_records), 6),
            extra={"model_calls": str(len(self.usage_records)), "chunks": str(self.chunk_count)},
        )


UsageSink = Callable[[UsageRecord], None]


def estimate_tokens(text: str) -> int:
    """供应商无关的保守文本 token 估算：UTF-8 每 3 bytes 约一个 token。"""
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def _input_budget(cfg: ModelConfig, prompt: Prompt) -> int:
    safe_total = math.floor(cfg.context_window_tokens * cfg.context_safety_ratio)
    budget = safe_total - cfg.max_output_tokens - estimate_tokens(prompt.body)
    if budget <= 0:
        raise ProcessingFailure(
            "模型上下文配置不足以容纳 prompt 与预留输出", attempts=0, stage="planning"
        )
    return min(budget, 2 * cfg.max_output_tokens)


def _context_input_budget(cfg: ModelConfig, prompt: Prompt) -> int:
    safe_total = math.floor(cfg.context_window_tokens * cfg.context_safety_ratio)
    budget = safe_total - cfg.max_output_tokens - estimate_tokens(prompt.body)
    if budget <= 0:
        raise ProcessingFailure(
            "模型上下文配置不足以容纳 prompt 与预留输出", attempts=0, stage="planning"
        )
    return budget


def _annotated_units(transcript: str) -> list[str]:
    paragraphs = [part.strip() for part in transcript.split("\n\n") if part.strip()]
    if not paragraphs:
        raise ValueError("逐字稿为空，无法结构化处理")
    units: list[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs, start=1):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        for line_index, line in enumerate(lines, start=1):
            suffix = "" if line_index == 1 else f".{line_index}"
            units.append(f"[段落 {paragraph_index}{suffix}] {line}")
    return units


def split_transcript(transcript: str, token_budget: int) -> list[str]:
    """优先在原文段落边界切分；极长单段才按字符上限安全拆开。"""
    if token_budget <= 0:
        raise ValueError("token_budget 必须大于 0")
    units: list[str] = []
    max_chars = max(1, token_budget * 2)
    for unit in _annotated_units(transcript):
        if estimate_tokens(unit) <= token_budget:
            units.append(unit)
            continue
        for offset in range(0, len(unit), max_chars):
            units.append(unit[offset : offset + max_chars])

    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and estimate_tokens(candidate) > token_budget:
            chunks.append("\n\n".join(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _schema_error(exc: ValidationError, result_tokens: int, cfg: ModelConfig) -> LLMSchemaError:
    first = exc.errors()[0] if exc.errors() else None
    detail = "未知校验错误"
    if first is not None:
        loc = ".".join(str(part) for part in first["loc"]) or "<root>"
        detail = f"{loc}: {first['msg']}"
    hint = ""
    if result_tokens >= cfg.max_output_tokens:
        hint = f"（输出达到 max_output_tokens={cfg.max_output_tokens}，疑似被截断）"
    return LLMSchemaError(f"模型输出不符合会议 schema：{detail}{hint}")


def _schema_correction(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else None
    if first is None:
        return "上一份 JSON 未通过本地 schema 校验，请修正后只输出完整 JSON。"
    loc = ".".join(str(part) for part in first["loc"]) or "<root>"
    return f"上一份 JSON 的本地校验失败（{loc}: {first['msg']}），请修正后只输出完整 JSON。"


def _output_was_truncated(output_tokens: int, finish_reason: str | None, cfg: ModelConfig) -> bool:
    """输出是否撞上额度上限。

    两个判据缺一不可：``finish_reason == "length"`` 是供应商明确信号；``output_tokens >=
    max_output_tokens`` 是兜底——DeepSeek 思考模式实测会**不返回** ``finish_reason`` 却把
    推理把整份预算吃光（2026-09-18：账本 8 条 ``finish_reason`` 全空、输出恰好 4096、
    content 为空），此时只靠供应商字段会把它误判成"schema 不合格"并原样重试，白烧调用。
    """
    return finish_reason == "length" or output_tokens >= cfg.max_output_tokens


def _truncation_message(
    cfg: ModelConfig,
    output_tokens: int,
    reasoning_tokens: int | None,
    content_chars: int,
) -> str:
    """截断时给出可诊断的一句话：推理吃了多少、真正写了多少。"""
    parts = [
        f"输出达到上限 max_output_tokens={cfg.max_output_tokens}"
        f"（实际 output_tokens={output_tokens}）"
    ]
    if reasoning_tokens is not None:
        parts.append(f"其中推理 reasoning_tokens={reasoning_tokens}")
    if content_chars == 0:
        parts.append("content 为空：输出预算被推理耗尽，未产出任何 JSON")
    parts.append("请提高 max_output_tokens 或关闭思考模式（thinking=disabled）")
    return "；".join(parts)


def _call_validated(
    model: ModelClient,
    cfg: ModelConfig,
    prompt: Prompt,
    user_text: str,
    *,
    task_key: str,
    stage: str,
    sleep: Callable[[float], None],
    usage_sink: UsageSink | None,
) -> tuple[MeetingExtraction, list[UsageRecord]]:
    usages: list[UsageRecord] = []
    last_error: Exception | None = None
    network_attempt = 0
    schema_attempt = 0
    current_text = user_text
    while network_attempt < MAX_RETRIES + 1:
        network_attempt += 1
        try:
            raw = model.complete(prompt.body, current_text, json_mode=True, max_retries=0)
        except LLMError as exc:
            last_error = exc
            if not is_retryable(exc):
                raise ProcessingFailure(str(exc), attempts=network_attempt, stage=stage) from exc
        else:
            raw = replace(raw, attempts=network_attempt)
            usage = record_from_result(cfg, raw, task_key=task_key)
            usages.append(usage)
            if usage_sink is not None:
                usage_sink(usage)
            if _output_was_truncated(raw.usage.output_tokens, raw.finish_reason, cfg):
                raise OutputTruncated(
                    _truncation_message(
                        cfg, raw.usage.output_tokens, raw.usage.reasoning_tokens, raw.content_chars
                    ),
                    attempts=network_attempt,
                    stage=stage,
                )
            try:
                return MeetingExtraction.model_validate_json(raw.text), usages
            except ValidationError as exc:
                last_error = _schema_error(exc, raw.usage.output_tokens, cfg)
                schema_attempt += 1
                if schema_attempt >= 2:
                    break
                current_text = user_text + "\n\n" + _schema_correction(exc)
                continue
        if network_attempt <= MAX_RETRIES:
            sleep(_BACKOFF_BASE * (2 ** (network_attempt - 1)))

    detail = str(last_error) if last_error is not None else "未知模型错误"
    message = f"模型调用失败（共 {network_attempt} 次调用）：{detail}"
    raise ProcessingFailure(message, attempts=network_attempt, stage=stage) from last_error


def _merge_payload(items: Sequence[MeetingExtraction]) -> str:
    return json.dumps(
        [item.model_dump(mode="json") for item in items], ensure_ascii=False, separators=(",", ":")
    )


def _merge_extractions(
    model: ModelClient,
    cfg: ModelConfig,
    merger_prompt: Prompt,
    items: list[MeetingExtraction],
    *,
    task_key: str,
    sleep: Callable[[float], None],
    usage_sink: UsageSink | None,
) -> tuple[MeetingExtraction, list[UsageRecord]]:
    usages: list[UsageRecord] = []
    budget = _context_input_budget(cfg, merger_prompt)
    current = items
    level = 1
    while len(current) > 1:
        groups: list[list[MeetingExtraction]] = []
        group: list[MeetingExtraction] = []
        for item in current:
            candidate = [*group, item]
            if group and estimate_tokens(_merge_payload(candidate)) > budget:
                groups.append(group)
                group = [item]
            else:
                group = candidate
        if group:
            groups.append(group)
        if all(len(batch) == 1 for batch in groups):
            raise ProcessingFailure(
                "单个分段提取结果超过合并模型的安全输入预算",
                attempts=0,
                stage="merge-planning",
            )

        merged_level: list[MeetingExtraction] = []
        for index, batch in enumerate(groups, start=1):
            if len(batch) == 1:
                merged_level.append(batch[0])
                continue
            merged, batch_usages = _call_validated(
                model,
                cfg,
                merger_prompt,
                _merge_payload(batch),
                task_key=f"{task_key}:merge:{level}:{index}",
                stage=f"merge-{level}-{index}",
                sleep=sleep,
                usage_sink=usage_sink,
            )
            usages.extend(batch_usages)
            merged_level.append(merged)
        current = merged_level
        level += 1
    return current[0], usages


def process_transcript(
    cfg: ModelConfig,
    api_key: SecretStr,
    transcript: str,
    *,
    prompt: Prompt,
    task_key: str,
    merger_prompt: Prompt | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] | None = None,
    usage_sink: UsageSink | None = None,
) -> ProcessedMeeting:
    """完整逐字稿优先单次处理；接近上下文上限时分段并分层合并。"""
    sleeper = sleep or time.sleep
    model = ModelClient(cfg, api_key, client=client, sleep=sleeper)
    budget = _input_budget(cfg, prompt)
    chunks = split_transcript(transcript, budget)
    usages: list[UsageRecord] = []
    extracted: list[MeetingExtraction] = []

    def process_chunk(chunk: str, index: str) -> None:
        try:
            item, chunk_usages = _call_validated(
                model,
                cfg,
                prompt,
                chunk,
                task_key=(
                    f"{task_key}:chunk:{index}" if len(chunks) > 1 or "." in index else task_key
                ),
                stage=f"chunk-{index}",
                sleep=sleeper,
                usage_sink=usage_sink,
            )
        except OutputTruncated as exc:
            smaller_budget = max(1, min(2_000, estimate_tokens(chunk) // 2))
            smaller = split_transcript(chunk, smaller_budget)
            if len(smaller) < 2 or max(map(len, smaller)) >= len(chunk):
                # 带上原始截断细节：否则用户只看到"已无法继续缩小该分段"，
                # 仍然不知道真因是输出预算被推理吃光（2026-09-18 的教训）。
                raise ProcessingFailure(
                    f"模型输出被截断，已无法继续缩小该分段；{exc}",
                    attempts=exc.attempts,
                    stage=exc.stage,
                ) from exc
            for sub_index, subchunk in enumerate(smaller, start=1):
                process_chunk(subchunk, f"{index}.{sub_index}")
            return
        usages.extend(chunk_usages)
        extracted.append(item)

    for index, chunk in enumerate(chunks, start=1):
        process_chunk(chunk, str(index))

    final = extracted[0]
    if len(extracted) > 1:
        if merger_prompt is None:
            raise ProcessingFailure(
                "逐字稿需要分段，但未提供 meeting-merger prompt",
                attempts=0,
                stage="planning",
            )
        final, merge_usages = _merge_extractions(
            model,
            cfg,
            merger_prompt,
            extracted,
            task_key=task_key,
            sleep=sleeper,
            usage_sink=usage_sink,
        )
        usages.extend(merge_usages)

    return ProcessedMeeting(
        extraction=final,
        usage_records=tuple(usages),
        prompt_version=prompt.version_label,
        chunk_count=len(extracted),
    )
