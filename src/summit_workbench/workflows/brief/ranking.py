"""行动排序（M2-4）：LLM 严格 JSON 排序 + 确定性回退。

环 A 硬约束（PRD 3.4）：模型**只输出「id 排序数组 + 分组标签」**，禁止自然语言正文；
模型不得新增/改写/升级候选。任何失败（不可用 / 非法 JSON / 非排列）都退回
:func:`fallback_ranking`，并置 ``degraded=True`` 使首行健康度可见（用户拍板）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pydantic import SecretStr

from summit_workbench.domain.brief import CATEGORY_LABELS, ActionSignal, fallback_ranking
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import CompletionResult, ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMError
from summit_workbench.providers.llm.usage import UsageRecord, record_from_result


class Completer(Protocol):
    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult: ...


@dataclass(frozen=True)
class RankingResult:
    order: list[str]
    groups: dict[str, str] = field(default_factory=dict)
    degraded: bool = False
    usage: UsageRecord | None = None
    model_id: str | None = None


def _default_groups(candidates: list[ActionSignal]) -> dict[str, str]:
    return {c.signal_id: CATEGORY_LABELS.get(c.category, c.category.value) for c in candidates}


def _build_user_message(candidates: list[ActionSignal]) -> str:
    payload = [
        {
            "id": c.signal_id,
            "title": c.title,
            "category": c.category.value,
            "evidence": c.evidence.value,
            "due_date": c.due_date,
        }
        for c in candidates
    ]
    return "候选行动条目（只对这些 id 排序，不得增删改）：\n" + json.dumps(
        payload, ensure_ascii=False
    )


def _parse_order(text: str, allowed: set[str]) -> tuple[list[str], dict[str, str]]:
    """解析模型输出；``order`` 必须恰为 ``allowed`` 的一个排列，否则抛 ValueError。"""
    if not text.strip():
        raise ValueError("排序返回为空")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("排序返回顶层不是对象")
    raw_order = data.get("order")
    if not isinstance(raw_order, list):
        raise ValueError("排序返回缺少 order 数组")
    order = [str(x) for x in raw_order]
    if set(order) != allowed or len(order) != len(allowed):
        raise ValueError("order 必须是候选 id 的一个排列（不得增删）")
    raw_groups = data.get("groups")
    groups = (
        {str(k): str(v) for k, v in raw_groups.items() if str(k) in allowed}
        if isinstance(raw_groups, dict)
        else {}
    )
    return order, groups


def rank_actions(
    candidates: list[ActionSignal],
    cfg: ModelConfig,
    api_key: SecretStr,
    *,
    prompt: Prompt,
    completer: Completer | None = None,
    now: datetime | None = None,
) -> RankingResult:
    """对候选排序。无候选或模型失败时给出确定性、可见的结果。"""
    if not candidates:
        return RankingResult(order=[], groups={}, degraded=False)

    fallback = fallback_ranking(candidates)
    default_groups = _default_groups(candidates)
    allowed = {c.signal_id for c in candidates}

    client = completer or ModelClient(cfg, api_key)
    try:
        result = client.complete(prompt.body, _build_user_message(candidates), json_mode=True)
    except LLMError:
        return RankingResult(order=fallback, groups=default_groups, degraded=True)

    usage = record_from_result(cfg, result, task_key="brief:ranking", now=now)
    try:
        order, model_groups = _parse_order(result.text, allowed)
    except (ValueError, json.JSONDecodeError):
        return RankingResult(
            order=fallback, groups=default_groups, degraded=True, usage=usage
        )

    groups = {**default_groups, **model_groups}
    return RankingResult(
        order=order, groups=groups, degraded=False, usage=usage, model_id=cfg.model_id
    )
