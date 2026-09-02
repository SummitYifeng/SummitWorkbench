"""问答编排：本地召回 → 构建带来源上下文 → 云端模型 → 校验只引用已提供来源。"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr, ValidationError

from summit_workbench.domain.qa import QaAnswer, QaConflict
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import MAX_RETRIES, CompletionResult, ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMSchemaError
from summit_workbench.providers.llm.usage import UsageRecord, record_from_result
from summit_workbench.workflows.ask.retrieval import (
    Candidate,
    candidate_by_id,
    retrieve_candidates,
)
from summit_workbench.workflows.meetings.processor import estimate_tokens

_BACKOFF_BASE = 0.5

# 追问上下文最多携带的历史轮数（前后端同口径；防无限增长挤占上下文预算）。
_MAX_HISTORY_TURNS = 6


class Completer(Protocol):
    """``ModelClient.complete`` 的结构化协议，便于测试注入。"""

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult: ...


@dataclass(frozen=True)
class AskTurn:
    """一轮历史问答的追问上下文：问题原文 + 当时引用过的来源 id。

    刻意不带当时的 AI 答案全文——AI 回答不是 vault 事实，不得作为下一轮来源。
    """

    question: str
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class AskResult:
    question: str
    answer: QaAnswer
    sources: tuple[Candidate, ...]  # 实际进入上下文的来源
    usage: UsageRecord | None  # 无召回、未调用模型时为 None
    dropped_sources: tuple[str, ...] = ()  # 被剔除的越界引用来源 ID


def _task_key(query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    return f"ask:{digest}"


def _context_budget(cfg: ModelConfig, fixed_tokens: int) -> int:
    safe_total = int(cfg.context_window_tokens * cfg.context_safety_ratio)
    return safe_total - cfg.max_output_tokens - fixed_tokens


def _select_within_budget(
    candidates: list[Candidate], cfg: ModelConfig, fixed_tokens: int
) -> list[Candidate]:
    budget = _context_budget(cfg, fixed_tokens)
    chosen: list[Candidate] = []
    used = 0
    for candidate in candidates:
        cost = estimate_tokens(candidate.body) + estimate_tokens(candidate.source_id) + 8
        if chosen and used + cost > budget:
            break
        chosen.append(candidate)
        used += cost
    return chosen


def _render_sources(sources: list[Candidate]) -> str:
    blocks: list[str] = []
    for candidate in sources:
        header = f"source_id: {candidate.source_id}\ntitle: {candidate.title}"
        blocks.append(f"<source>\n{header}\n---\n{candidate.body}\n</source>")
    return "\n\n".join(blocks)


def _render_history(history: tuple[AskTurn, ...]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for index, turn in enumerate(history, 1):
        if turn.sources:
            lines.append(f"{index}. {turn.question}（当时引用来源：{', '.join(turn.sources)}）")
        else:
            lines.append(f"{index}. {turn.question}")
    return "\n".join(lines)


def _build_user_message(query: str, sources: list[Candidate], history_text: str = "") -> str:
    parts = [f"问题：{query}"]
    if history_text:
        parts.append(
            "以下是用户此前在本会话问过的问题，仅作延续话题的背景，不是知识来源"
            "（AI 之前的回答同样不是来源）：\n" + history_text
        )
    parts.append(
        "以下是从本地知识库召回的来源，只能引用这些来源作答，"
        "每条事实必须给出对应的 source_id；证据矛盾时并列展示；"
        "无法从来源回答时把 unanswerable 设为 true。\n\n"
        f"{_render_sources(sources)}"
    )
    return "\n\n".join(parts)


def _ground(answer: QaAnswer, allowed: set[str]) -> tuple[QaAnswer, tuple[str, ...]]:
    """剔除引用了未提供来源的事实/冲突（PRD：只能引用进入上下文的 Markdown）。"""
    cited = answer.cited_source_ids()
    dropped = tuple(sorted(cited - allowed))
    if not dropped:
        return answer, ()
    facts = [fact for fact in answer.facts if fact.source_id in allowed]
    conflicts: list[QaConflict] = []
    for conflict in answer.conflicts:
        sides = [side for side in conflict.sides if side.source_id in allowed]
        if len(sides) >= 2:
            conflicts.append(conflict.model_copy(update={"sides": sides}))
    grounded = answer.model_copy(update={"facts": facts, "conflicts": conflicts})
    return grounded, dropped


def _parse_answer(text: str) -> QaAnswer:
    if not text.strip():
        raise LLMSchemaError("问答返回为空")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMSchemaError(f"问答返回非 JSON：{exc}") from exc
    try:
        return QaAnswer.model_validate(payload)
    except ValidationError as exc:
        raise LLMSchemaError(f"问答返回不符合 schema：{exc}") from exc


def _aggregate_usage(usages: list[UsageRecord]) -> UsageRecord:
    """把多次尝试的用量合并成一条（token/费用求和，attempts=调用次数）。"""
    if len(usages) == 1:
        return usages[0]
    first = usages[0]
    return replace(
        first,
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        attempts=len(usages),
        estimated_cost=round(sum(u.estimated_cost for u in usages), 6),
        extra={"model_calls": str(len(usages))},
    )


def _answer_with_retry(
    completer: Completer,
    cfg: ModelConfig,
    prompt: Prompt,
    user_message: str,
    *,
    task_key: str,
    now: datetime | None,
    sleep: Callable[[float], None],
) -> tuple[QaAnswer, UsageRecord]:
    """调用模型并解析；对空/非法 JSON 这类瞬时问题按退避重试（复用会议处理的韧性约定）。"""
    usages: list[UsageRecord] = []
    last_error: LLMSchemaError | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        result = completer.complete(prompt.body, user_message, json_mode=True)
        usages.append(record_from_result(cfg, result, task_key=task_key, now=now))
        try:
            return _parse_answer(result.text), _aggregate_usage(usages)
        except LLMSchemaError as exc:
            last_error = exc
            if attempt <= MAX_RETRIES:
                sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
    raise last_error or LLMSchemaError("问答返回无法解析")


def answer_question(
    vault_dir: Path,
    query: str,
    cfg: ModelConfig,
    api_key: SecretStr,
    *,
    prompt: Prompt,
    project: str | None = None,
    limit: int = 6,
    history: tuple[AskTurn, ...] = (),
    completer: Completer | None = None,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AskResult:
    """召回本地来源并让模型带来源作答；无召回则不调用模型。

    ``history`` 提供追问上下文：前几轮问题原文进入 prompt 作背景（非来源），
    历史轮引用过的来源 id 会被重新纳入本次候选（笔记已删除/越界则跳过），
    保证「那后来呢 / 具体哪次会」这类追问能引用同一批笔记。
    """
    query = query.strip()
    if not query:
        raise ValueError("问题不能为空")
    history = history[-_MAX_HISTORY_TURNS:]
    history_text = _render_history(history)

    candidates = retrieve_candidates(vault_dir, query, project=project, limit=limit)
    # 追问轮：把历史引用过的来源补回候选（去重、保持新鲜召回在前）。
    seen: set[str] = set()
    merged: list[Candidate] = []
    for candidate in candidates:
        if candidate.source_id not in seen:
            merged.append(candidate)
            seen.add(candidate.source_id)
    for turn in history:
        for source_id in turn.sources:
            if source_id in seen:
                continue
            pinned = candidate_by_id(vault_dir, source_id)
            if pinned is not None:
                merged.append(pinned)
                seen.add(source_id)
    candidates = merged

    if not candidates:
        return AskResult(
            question=query,
            answer=QaAnswer(summary="本地知识库未召回相关笔记，无法作答。", unanswerable=True),
            sources=(),
            usage=None,
        )

    fixed = (
        estimate_tokens(prompt.body)
        + estimate_tokens(query)
        + (estimate_tokens(history_text) if history_text else 0)
        + 64
    )
    sources = _select_within_budget(candidates, cfg, fixed)
    user_message = _build_user_message(query, sources, history_text)

    client = completer or ModelClient(cfg, api_key)
    answer, usage = _answer_with_retry(
        client, cfg, prompt, user_message, task_key=_task_key(query), now=now, sleep=sleep
    )
    grounded, dropped = _ground(answer, {c.source_id for c in sources})
    return AskResult(
        question=query,
        answer=grounded,
        sources=tuple(sources),
        usage=usage,
        dropped_sources=dropped,
    )
