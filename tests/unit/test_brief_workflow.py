"""简报编排单测：采集逐源隔离 / 排序降级 / 渲染事实直取 / 端到端幂等。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.domain.brief import (
    ActionCategory,
    ActionSignal,
    EvidenceLevel,
    fallback_ranking,
)
from summit_workbench.providers.feishu.calendar import CalendarEvent
from summit_workbench.providers.feishu.tasks import TaskItem
from summit_workbench.repositories.daily_note import daily_note_path
from summit_workbench.repositories.signal_snapshot import read_snapshot
from summit_workbench.workflows.brief.brief import generate_brief
from summit_workbench.workflows.brief.collect import collect_signals
from summit_workbench.workflows.brief.ranking import RankingResult, rank_actions
from summit_workbench.workflows.brief.render import render_brief

TZ = "Asia/Shanghai"


class _StubSource:
    def __init__(
        self,
        *,
        meetings: list[CalendarEvent] | None = None,
        open_tasks: list[TaskItem] | None = None,
        completed: list[TaskItem] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self._meetings = meetings or []
        self._open = open_tasks or []
        self._completed = completed or []
        self._fail = fail or set()

    def meetings(self) -> list[CalendarEvent]:
        if "meetings" in self._fail:
            raise RuntimeError("calendar down")
        return self._meetings

    def open_tasks(self) -> list[TaskItem]:
        if "tasks" in self._fail:
            raise RuntimeError("tasks down")
        return self._open

    def completed_tasks(self) -> list[TaskItem]:
        return self._completed


def _fallback_rank(candidates: list[ActionSignal]) -> RankingResult:
    return RankingResult(order=fallback_ranking(candidates), degraded=True)


# —— 采集逐源隔离 ——


def test_collect_isolates_source_failure(tmp_path: Path) -> None:
    source = _StubSource(
        meetings=[CalendarEvent("e1", "周会", "1756700000")],
        open_tasks=[TaskItem("t1", "交周报", "2026-09-02", False)],
        fail={"meetings"},  # 日历失败，任务仍应采集到
    )
    collected = collect_signals(
        tmp_path, tmp_path / "_vault", timezone=TZ, facts_source=source
    )
    assert collected.meetings == []
    assert len(collected.tasks) == 1
    assert any("飞书日历" in f for f in collected.source_failures)
    # 有截止的任务成为承诺候选
    assert any(c.category is ActionCategory.COMMITMENT for c in collected.candidates)


def test_collect_local_only_when_no_feishu(tmp_path: Path) -> None:
    collected = collect_signals(
        tmp_path, tmp_path / "_vault", timezone=TZ, facts_source=None
    )
    assert any("飞书未配置" in f for f in collected.source_failures)


# —— 排序降级 ——


class _BadCompleter:
    def complete(self, system: str, user: str, *, json_mode: bool = True):  # noqa: ANN001
        from summit_workbench.providers.llm.client import CompletionResult, Usage

        return CompletionResult(
            text="not json at all", usage=Usage(1, 1), model_id="m", attempts=1
        )


def test_ranking_degrades_on_bad_json() -> None:
    from summit_workbench.prompts import Prompt
    from summit_workbench.providers.llm.config import ModelConfig

    cfg = ModelConfig(
        capability="ranking", model_id="m", base_url="http://x", credential_account="shared"
    )
    prompt = Prompt(name="brief-ranker", version=1, capability="ranking", body="rank")
    candidates = [
        ActionSignal("a", "A", ActionCategory.MAIN_PUSH, EvidenceLevel.E2, "ref/a"),
    ]
    from pydantic import SecretStr

    result = rank_actions(
        candidates, cfg, SecretStr("k"), prompt=prompt, completer=_BadCompleter()
    )
    assert result.degraded is True
    assert result.order == ["a"]  # 回退仍给出确定性顺序
    assert result.usage is not None  # 调用发生了，用量已记录


# —— 渲染事实直取 + ≤5 ——


def test_render_facts_verbatim_and_action_cap() -> None:
    from summit_workbench.domain.brief import (
        Brief,
        EvidenceLevel,
        HealthState,
        MeetingFact,
        TaskFact,
    )

    actions = tuple(
        ActionSignal(f"m{i}", f"行动{i}", ActionCategory.MAIN_PUSH, EvidenceLevel.E2, f"ref{i}")
        for i in range(5)
    )
    brief = Brief(
        date="2026-09-01",
        health=HealthState("ok"),
        meetings=(MeetingFact("招生周会", "09:30"),),
        tasks=(TaskFact("交周报", "2026-09-02"),),
        actions=actions,
    )
    md = render_brief(brief, {})
    assert "招生周会" in md and "09:30" in md  # 会议原文直取
    assert "交周报" in md and "2026-09-02" in md  # 任务原文直取
    assert "需要行动（5/5）" in md
    assert md.count("[主线推进]") == 5  # 无 groups 时按分类兜底中文标签
    assert "🟢 健康度 正常" in md


# —— 端到端幂等 ——


def test_generate_brief_writes_and_reruns_idempotent(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    vault.mkdir(parents=True)
    source = _StubSource(
        meetings=[CalendarEvent("e1", "周会", "1756700000")],
        open_tasks=[TaskItem("t1", "交周报", "2026-09-02", False)],
    )

    first = generate_brief(
        work_root, vault, day="2026-09-01", timezone=TZ,
        facts_source=source, rank=_fallback_rank,
    )
    assert first.note_path == daily_note_path(vault, "2026-09-01")
    assert first.note_path is not None and first.note_path.is_file()
    assert read_snapshot(vault, "2026-09-01") is not None
    first_text = first.note_path.read_text(encoding="utf-8")

    # 重跑：内容一致，不重复锚点
    second = generate_brief(
        work_root, vault, day="2026-09-01", timezone=TZ,
        facts_source=source, rank=_fallback_rank,
    )
    assert second.note_path is not None
    second_text = second.note_path.read_text(encoding="utf-8")
    assert second_text.count("BRIEF:START") == 1
    assert second.markdown == first.markdown  # 确定性
    assert first_text == second_text


def test_generate_brief_dry_run_writes_nothing(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    vault.mkdir(parents=True)
    result = generate_brief(
        work_root, vault, day="2026-09-01", timezone=TZ,
        facts_source=None, rank=_fallback_rank, write=False,
    )
    assert result.note_path is None
    assert result.snapshot_path is None
    assert not daily_note_path(vault, "2026-09-01").exists()
    # 降级健康度仍渲染出来
    assert "健康度" in result.markdown
