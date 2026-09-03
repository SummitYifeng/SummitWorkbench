"""线程知识录入的模型消化（P1：推进日志 / AI 产物索引）。

策略与快速捕捉一致：单次模型调用、任何失败回退为「原文照存 + 空摘要」，绝不丢数据、
绝不阻塞录入；关联线程由调用方选定并本地解析，不经模型臆造项目名。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

import httpx
from pydantic import SecretStr, ValidationError

from summit_workbench.domain.threaddoc import (
    ArtifactIndex,
    LogDigest,
    fallback_artifact_index,
    fallback_log_digest,
)
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMError

# 录入场景的模型超时上限：摘要/索引是加分项，不能让用户等太久。
_DIGEST_TIMEOUT = 10.0


def _fast(cfg: ModelConfig) -> ModelConfig:
    return replace(cfg, timeout_seconds=min(cfg.timeout_seconds, _DIGEST_TIMEOUT))


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
    """把一段推进日志消化为摘要/涉及人/类型标签；任何失败回退为空摘要。"""
    model = ModelClient(_fast(cfg), api_key, client=client, sleep=sleep)
    user_message = text
    if project_hints:
        user_message = f"（关联线程：{', '.join(project_hints)}）\n\n{text}"
    try:
        result = model.complete(prompt.body, user_message, json_mode=True, max_retries=0)
        return LogDigest.model_validate_json(result.text)
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
