"""M1-6：问答编排——召回、只引用已提供来源、无召回不调用模型。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import SecretStr

from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import CompletionResult, Usage
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.workflows.ask.ask import AskTurn, answer_question

CFG = ModelConfig(capability="qa", model_id="m", base_url="http://x", credential_account="shared")
PROMPT = Prompt(name="qa-answer", version=1, capability="qa", body="系统提示")


class FakeCompleter:
    def __init__(self, payload: dict[str, object]) -> None:
        self._text = json.dumps(payload, ensure_ascii=False)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        self.calls.append((system, user))
        return CompletionResult(text=self._text, usage=Usage(120, 40), model_id="m", attempts=1)


class SequenceCompleter:
    """按序返回预设的原始文本，模拟瞬时空响应后恢复。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.calls = 0

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return CompletionResult(text=text, usage=Usage(100, 30), model_id="m", attempts=1)


def _note(vault: Path, rel: str, project: str, body: str) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndate: 2026-08-31\ntype: project-main\nstatus: active\nproject: {project}\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _note(vault, "projects/P1.md", "P1", "# P1\n\n价格由后台设置为免费实现。")
    return vault


def test_no_candidates_skips_model_and_marks_unanswerable(tmp_path):
    completer = FakeCompleter({"summary": "x"})
    result = answer_question(
        _vault(tmp_path), "毫不相关xyz", CFG, SecretStr("k"), prompt=PROMPT, completer=completer
    )
    assert completer.calls == []  # 无召回不调用模型
    assert result.answer.unanswerable is True
    assert result.usage is None
    assert result.sources == ()


def test_grounds_answer_to_provided_sources(tmp_path):
    completer = FakeCompleter(
        {
            "summary": "价格设为免费。",
            "facts": [
                {"text": "免费由后台设置", "source_id": "projects/P1"},
                {"text": "编造事实", "source_id": "projects/NOPE"},
            ],
            "suggestions": ["建议关注白名单"],
        }
    )
    result = answer_question(
        _vault(tmp_path), "价格怎么定", CFG, SecretStr("k"), prompt=PROMPT, completer=completer
    )
    assert len(completer.calls) == 1
    ids = [f.source_id for f in result.answer.facts]
    assert ids == ["projects/P1"]  # 越界引用被剔除
    assert result.dropped_sources == ("projects/NOPE",)
    assert result.answer.suggestions == ["建议关注白名单"]
    assert result.usage is not None
    assert result.usage.task_key.startswith("ask:")


def test_retries_transient_empty_response_then_succeeds(tmp_path):
    valid = json.dumps({"summary": "免费。", "facts": []}, ensure_ascii=False)
    completer = SequenceCompleter(["", valid])  # 先空响应，后正常
    result = answer_question(
        _vault(tmp_path),
        "价格",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        sleep=lambda _: None,
    )
    assert completer.calls == 2
    assert result.answer.summary == "免费。"
    assert result.usage is not None
    assert result.usage.attempts == 2  # 用量合并两次调用


def test_source_id_appears_in_model_context(tmp_path):
    completer = FakeCompleter({"summary": "ok"})
    answer_question(
        _vault(tmp_path), "价格", CFG, SecretStr("k"), prompt=PROMPT, completer=completer
    )
    _, user = completer.calls[0]
    assert "source_id: projects/P1" in user


def test_followup_reincludes_historical_source_when_fresh_retrieval_empty(tmp_path):
    """追问轮：当前问题召回为空，但历史轮引用过的来源被重新纳入 → 仍可作答。"""
    completer = FakeCompleter({"summary": "延续：免费实现。"})
    result = answer_question(
        _vault(tmp_path),
        "那后来呢",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        history=(AskTurn(question="价格怎么定", sources=("projects/P1",)),),
    )
    assert len(completer.calls) == 1
    _, user = completer.calls[0]
    assert "source_id: projects/P1" in user  # 历史来源重新进入上下文
    assert "价格怎么定" in user  # 历史问题作为背景传入
    assert "不是知识来源" in user
    assert result.answer.unanswerable is False


def test_history_brings_prior_questions_as_background_only(tmp_path):
    """历史轮只携带问题原文；AI 当时的回答绝不进入下一轮上下文。"""
    completer = FakeCompleter({"summary": "ok"})
    answer_question(
        _vault(tmp_path),
        "价格",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        history=(AskTurn(question="上一轮问题", sources=("projects/P1",)),),
    )
    _, user = completer.calls[0]
    assert "上一轮问题" in user
    assert "不是知识来源" in user


def test_history_missing_note_is_skipped(tmp_path):
    """历史轮引用的笔记已被删除 → 跳过，不报错；仍无候选则不调用模型。"""
    completer = FakeCompleter({"summary": "x"})
    result = answer_question(
        _vault(tmp_path),
        "那后来呢",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        history=(AskTurn(question="问过 P1", sources=("projects/GONE",)),),
    )
    assert completer.calls == []
    assert result.answer.unanswerable is True
    assert result.usage is None


def test_history_capped_to_last_turns(tmp_path):
    """追问上下文最多携带最近 6 轮，更早的被截断。"""
    completer = FakeCompleter({"summary": "ok"})
    turns = tuple(AskTurn(question=f"前轮问题{i}") for i in range(1, 9))  # 8 轮 → 保留后 6 轮
    answer_question(
        _vault(tmp_path),
        "价格",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        history=turns,
    )
    _, user = completer.calls[0]
    assert "前轮问题1" not in user
    assert "前轮问题2" not in user
    assert "前轮问题3" in user
    assert "前轮问题8" in user
