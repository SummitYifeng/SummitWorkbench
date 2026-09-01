"""排序器单测：模型给出合法排列 → 采用；空候选 → 空结果不调用模型。"""

from __future__ import annotations

import json

from pydantic import SecretStr

from summit_workbench.domain.brief import ActionCategory, ActionSignal, EvidenceLevel
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.client import CompletionResult, Usage
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.workflows.brief.ranking import rank_actions

CFG = ModelConfig(
    capability="ranking", model_id="m", base_url="http://x", credential_account="shared"
)
PROMPT = Prompt(name="brief-ranker", version=1, capability="ranking", body="rank")


def _sig(sid: str) -> ActionSignal:
    return ActionSignal(sid, sid, ActionCategory.MAIN_PUSH, EvidenceLevel.E2, f"ref/{sid}")


class _Completer:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> CompletionResult:
        self.calls += 1
        return CompletionResult(
            text=json.dumps(self.payload), usage=Usage(10, 5), model_id="m", attempts=1
        )


def test_valid_permutation_is_adopted() -> None:
    candidates = [_sig("a"), _sig("b"), _sig("c")]
    completer = _Completer({"order": ["c", "a", "b"], "groups": {"a": "主线"}})
    result = rank_actions(candidates, CFG, SecretStr("k"), prompt=PROMPT, completer=completer)
    assert result.order == ["c", "a", "b"]
    assert result.degraded is False
    assert result.groups["a"] == "主线"
    assert result.model_id == "m"
    assert result.usage is not None


def test_non_permutation_degrades() -> None:
    candidates = [_sig("a"), _sig("b")]
    # 缺少 b、混入 x → 非排列 → 回退
    completer = _Completer({"order": ["a", "x"]})
    result = rank_actions(candidates, CFG, SecretStr("k"), prompt=PROMPT, completer=completer)
    assert result.degraded is True
    assert set(result.order) == {"a", "b"}


def test_empty_candidates_skips_model() -> None:
    completer = _Completer({"order": []})
    result = rank_actions([], CFG, SecretStr("k"), prompt=PROMPT, completer=completer)
    assert result.order == []
    assert result.degraded is False
    assert completer.calls == 0  # 无候选不调用模型
