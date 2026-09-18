"""线程知识录入的模型消化（P1：推进日志 / AI 产物索引）。

策略与快速捕捉一致：单次模型调用、任何失败回退为「原文照存 + 空摘要」，绝不丢数据、
绝不阻塞录入；关联线程由调用方选定并本地解析，不经模型臆造项目名。
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import replace

import httpx
from pydantic import SecretStr, ValidationError

from summit_workbench.domain.threaddoc import (
    ArtifactIndex,
    LogDigest,
    LogTag,
    fallback_artifact_index,
    fallback_log_digest,
)
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.workflows.meetings.processor import estimate_tokens

# 交互场景的默认模型超时。**不再是硬上限**：只在配置未给 timeout_seconds 时兜底，
# 显式配置优先（2026-09-18：旧实现用 min(cfg.timeout, 10) 把长日志摘要压到 10 秒，
# 长文档必然超时、且失败静默回退空摘要 —— 配置写了也不生效）。
_DIGEST_TIMEOUT = 10.0


def _fast(cfg: ModelConfig) -> ModelConfig:
    if cfg.timeout_seconds and cfg.timeout_seconds > 0:
        return cfg
    return replace(cfg, timeout_seconds=_DIGEST_TIMEOUT)


def _merge_digests(parts: list[LogDigest]) -> LogDigest:
    """把多段摘要合并成一份：摘要拼接、人名/标签保序去重、首个非空 next_step/decision。"""
    seen_people: list[str] = []
    seen_tags: list[LogTag] = []
    for part in parts:
        for person in part.involved:
            if person not in seen_people:
                seen_people.append(person)
        for tag in part.tags:
            if tag not in seen_tags:
                seen_tags.append(tag)
    return LogDigest(
        summary=" ".join(part.summary.strip() for part in parts if part.summary.strip())[:600],
        involved=seen_people,
        tags=seen_tags[:3],
        next_step=next((p.next_step for p in parts if p.next_step), None),
        decision=next((p.decision for p in parts if p.decision), None),
    )


def _split_for_digest(text: str, token_budget: int) -> list[str]:
    """按空行段落切分；单段超预算才按字符硬切。预算内的文本原样返回单段。"""
    if token_budget <= 0 or estimate_tokens(text) <= token_budget:
        return [text]
    units = [part for part in text.split("\n\n") if part.strip()]
    max_chars = max(1, token_budget * 2)
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidates = (
            [unit]
            if estimate_tokens(unit) <= token_budget
            else [unit[i : i + max_chars] for i in range(0, len(unit), max_chars)]
        )
        for candidate in candidates:
            if current and estimate_tokens("\n\n".join([*current, candidate])) > token_budget:
                chunks.append("\n\n".join(current))
                current = [candidate]
            else:
                current.append(candidate)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def digest_log(
    cfg: ModelConfig,
    api_key: SecretStr,
    prompt: Prompt,
    text: str,
    *,
    project_hints: list[str] | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> LogDigest:
    """把一段推进日志消化为摘要/涉及人/类型标签；任何失败回退为空摘要。

    超长文本（超过该能力的上下文安全预算）先分段各自消化、再本地合并，避免整篇一次调用
    撞上下文而失败（2026-09-18 同类问题：先前只靠"失败回退空摘要"掩盖了超时/超长）。
    """
    fast_cfg = _fast(cfg)
    model = ModelClient(fast_cfg, api_key, client=client, sleep=sleep)
    prefix = f"（关联线程：{', '.join(project_hints)}）\n\n" if project_hints else ""
    safe_total = math.floor(fast_cfg.context_window_tokens * fast_cfg.context_safety_ratio)
    budget = safe_total - fast_cfg.max_output_tokens - estimate_tokens(prompt.body + prefix)
    try:
        chunks = _split_for_digest(text, budget) if budget > 0 else [text]
        digests: list[LogDigest] = []
        for chunk in chunks:
            result = model.complete(prompt.body, f"{prefix}{chunk}", json_mode=True, max_retries=0)
            digests.append(LogDigest.model_validate_json(result.text))
        if not digests:
            return fallback_log_digest()
        return digests[0] if len(digests) == 1 else _merge_digests(digests)
    except (LLMError, ValidationError, ValueError, TypeError):
        return fallback_log_digest()


def index_artifact(
    cfg: ModelConfig,
    api_key: SecretStr,
    prompt: Prompt,
    text: str,
    *,
    title_hint: str | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ArtifactIndex:
    """把一段 AI 产物文本索引为标题/摘要/分类；任何失败回退为标题提示。"""
    model = ModelClient(_fast(cfg), api_key, client=client, sleep=sleep)
    user_message = text
    if title_hint:
        user_message = f"（用户给定标题：{title_hint}，请沿用或微调）\n\n{text}"
    try:
        result = model.complete(prompt.body, user_message, json_mode=True, max_retries=0)
        return ArtifactIndex.model_validate_json(result.text)
    except (LLMError, ValidationError, ValueError, TypeError):
        return fallback_artifact_index(title_hint)
