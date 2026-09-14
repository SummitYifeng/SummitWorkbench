"""M1-6：问答编排——召回、只引用已提供来源、无召回不调用模型。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from summit_workbench.prompts import Prompt, load_prompt
from summit_workbench.providers.llm.client import CompletionResult, Usage
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMSchemaError
from summit_workbench.workflows.ask.ask import AskTurn, answer_question

CFG = ModelConfig(capability="qa", model_id="m", base_url="http://x", credential_account="shared")
# 必须与 prompts/qa-answer.md 的 frontmatter 对齐（由下方 test_qa_answer_prompt_version 锁住）
PROMPT = Prompt(name="qa-answer", version=2, capability="qa", body="系统提示")


def test_qa_answer_prompt_version_is_locked_to_the_file() -> None:
    """prompt 版本会写进 qa-insight 的 `prompt_version`，所以文件与断言必须同步。

    这条锁是必要的：文档与 CHANGELOG 声称 v2 时，prompt 文件曾经停在 v1 而没有任何测试会红。
    """
    prompt = load_prompt("qa-answer")
    assert prompt.version_label == "qa-answer@v2"
    # v2 的契约变化：`source_id` 可能是 `路径#区块标题`，模型必须逐字照抄整个 id
    # （只写路径部分会让引用退化到「整篇」，答案的精确性就丢了）
    assert "路径#区块标题" in prompt.body
    # 上面的 stub 必须与真实文件同版本，否则这组编排测试测的就不是线上 prompt 的契约
    assert PROMPT.version == prompt.version


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


class TruncationCompleter:
    """模拟「输出触顶」：返回被截断的 JSON，并把 output_tokens 报到上限。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        self.calls.append(user)
        return CompletionResult(
            text='{"summary": "很长很长的答案被截断了',
            usage=Usage(100, CFG.max_output_tokens),
            model_id="m",
            attempts=1,
        )


def test_truncated_answer_reports_an_actionable_hint(tmp_path: Path) -> None:
    """输出触顶导致 JSON 截断时，错误必须说清「被截断 + 怎么办」。

    2026-09-14 实测：来源块本身很长（主题簇页的 `## 关键结论` 是逐条清单）时，
    模型答案会撞上 ``max_output_tokens`` 把 JSON 截断，而旧文案只有
    「问答返回非 JSON：Unterminated string…」——使用者完全不知道能做什么。
    """
    completer = TruncationCompleter()
    with pytest.raises(LLMSchemaError) as exc_info:
        answer_question(
            _vault(tmp_path),
            "价格",
            CFG,
            SecretStr("k"),
            prompt=PROMPT,
            completer=completer,
            sleep=lambda _: None,
        )
    message = str(exc_info.value)
    assert "截断" in message and "max_output_tokens" in message, message


class RecordingCompleter:
    """第一次返回空（触发重试），第二次返回合法 JSON；记录每次的 user message。"""

    def __init__(self, payload: dict[str, object]) -> None:
        self._valid = json.dumps(payload, ensure_ascii=False)
        self.calls: list[str] = []

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        self.calls.append(user)
        text = "" if len(self.calls) == 1 else self._valid
        return CompletionResult(text=text, usage=Usage(100, 30), model_id="m", attempts=1)


def test_retry_narrows_the_sources(tmp_path: Path) -> None:
    """重试必须换用「来源收窄」的消息。

    原样重发在「输出触顶」场景下必然同样失败；减少来源是最有效的自救。
    判据：第二次调用的 user message 里 source 条数严格少于第一次（fixture 给 ≥4 个来源）。
    """
    vault = tmp_path / "vault"
    for index in range(6):
        _note(
            vault,
            f"projects/P{index}.md",
            f"P{index}",
            f"# P{index}\n\n价格与费用由后台设置为免费实现，第 {index} 条。",
        )
    completer = RecordingCompleter({"summary": "免费。"})
    answer_question(
        vault,
        "价格",
        CFG,
        SecretStr("k"),
        prompt=PROMPT,
        completer=completer,
        sleep=lambda _: None,
    )
    assert len(completer.calls) == 2
    first, second = completer.calls
    assert first.count("source_id:") >= 4, first[:200]
    assert second.count("source_id:") < first.count("source_id:")
