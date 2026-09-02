"""快速捕捉的智能分类（M4 形态先行版，供 Web 面板 /api/capture 使用）。

策略（交互场景低延迟优先）：

- 单次模型调用（不重试、超时收紧到 8s），任何失败都回退为「想法」，绝不阻塞录入；
- #项目 标签在本地解析（project_registry），不让模型臆造项目名；
- 承诺与想法当前都落入全局 inbox（M4 的 wb task 再承接结构化任务），分类以稳定标记写回，
  供后续路由与展示复用。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import replace

import httpx
from pydantic import SecretStr, ValidationError

from summit_workbench.domain.capture import (
    CaptureClassification,
    fallback_classification,
)
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.repositories.project_registry import ProjectRegistry

# 交互场景的模型超时上限：分类是加分项，不能让用户等太久。
_CAPTURE_TIMEOUT = 8.0

_TAG_RE = re.compile(r"#([^\s#，,。]+)")


def extract_project_tags(text: str, registry: ProjectRegistry) -> list[str]:
    """从文本里取出能解析到已知项目的 #标签（按出现顺序去重）。

    解析不到的标签直接忽略——项目未建档时保持原文，不臆造归属。
    """
    seen: list[str] = []
    for raw in _TAG_RE.findall(text):
        resolved = registry.resolve(raw)
        if resolved and resolved not in seen:
            seen.append(resolved)
    return seen


def classify_capture(
    cfg: ModelConfig,
    api_key: SecretStr,
    prompt: Prompt,
    text: str,
    *,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> CaptureClassification:
    """单次调用分类；任何失败（超时/网络/解析/schema）都回退为想法。"""
    fast_cfg = replace(cfg, timeout_seconds=min(cfg.timeout_seconds, _CAPTURE_TIMEOUT))
    model = ModelClient(fast_cfg, api_key, client=client, sleep=sleep)
    try:
        result = model.complete(prompt.body, text, json_mode=True, max_retries=0)
        return CaptureClassification.model_validate_json(result.text)
    except (LLMError, ValidationError, ValueError, TypeError):
        return fallback_classification()
