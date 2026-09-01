"""晨间简报纯领域规则单测（配额 / 回退排序 / 健康度）。"""

from __future__ import annotations

from summit_workbench.domain.brief import (
    ActionCategory,
    ActionSignal,
    CollectedSignals,
    EvidenceLevel,
    MeetingFact,
    evaluate_health,
    fallback_ranking,
    select_actions,
)


def _sig(
    sid: str,
    category: ActionCategory,
    *,
    evidence: EvidenceLevel = EvidenceLevel.E2,
    due: str | None = None,
) -> ActionSignal:
    return ActionSignal(
        signal_id=sid,
        title=sid,
        category=category,
        evidence=evidence,
        source_ref=f"ref/{sid}",
        due_date=due,
    )


def test_evidence_rank_orders_e1_e2_e3() -> None:
    assert EvidenceLevel.E1.rank < EvidenceLevel.E2.rank < EvidenceLevel.E3.rank


def test_select_actions_respects_default_quota_and_cap() -> None:
    candidates = [
        _sig("m1", ActionCategory.MAIN_PUSH),
        _sig("m2", ActionCategory.MAIN_PUSH),
        _sig("m3", ActionCategory.MAIN_PUSH),  # 超配额，第一轮不入
        _sig("c1", ActionCategory.COMMITMENT),
        _sig("c2", ActionCategory.COMMITMENT),
        _sig("a1", ActionCategory.ANTI_STALL),
    ]
    order = [s.signal_id for s in candidates]
    chosen = select_actions(candidates, order)
    ids = [s.signal_id for s in chosen]
    # 主线 2 + 承诺 2 + 防停 1 = 5，命中上限；m3 被挤出。
    assert ids == ["m1", "m2", "c1", "c2", "a1"]
    assert len(ids) == 5


def test_select_actions_dynamic_backfill_when_category_missing() -> None:
    # 无承诺、无防停信号：主线应动态补位到 5 条上限。
    candidates = [_sig(f"m{i}", ActionCategory.MAIN_PUSH) for i in range(1, 8)]
    order = [s.signal_id for s in candidates]
    chosen = select_actions(candidates, order)
    assert [s.signal_id for s in chosen] == ["m1", "m2", "m3", "m4", "m5"]


def test_select_actions_excludes_proposals_from_action_region() -> None:
    candidates = [
        _sig("p1", ActionCategory.PROPOSAL),
        _sig("m1", ActionCategory.MAIN_PUSH),
    ]
    chosen = select_actions(candidates, ["p1", "m1"])
    assert [s.signal_id for s in chosen] == ["m1"]


def test_select_actions_follows_model_order() -> None:
    candidates = [
        _sig("m1", ActionCategory.MAIN_PUSH),
        _sig("m2", ActionCategory.MAIN_PUSH),
    ]
    # 模型把 m2 排在前
    chosen = select_actions(candidates, ["m2", "m1"])
    assert [s.signal_id for s in chosen] == ["m2", "m1"]


def test_select_actions_backfills_ids_missing_from_order() -> None:
    candidates = [
        _sig("m1", ActionCategory.MAIN_PUSH),
        _sig("m2", ActionCategory.MAIN_PUSH),
    ]
    # order 只覆盖 m1；m2 仍应稳定补齐
    chosen = select_actions(candidates, ["m1"])
    assert {s.signal_id for s in chosen} == {"m1", "m2"}


def test_fallback_ranking_is_deterministic_by_due_then_category() -> None:
    candidates = [
        _sig("late", ActionCategory.MAIN_PUSH, due="2026-09-10"),
        _sig("soon", ActionCategory.MAIN_PUSH, due="2026-09-02"),
        _sig("nodate", ActionCategory.MAIN_PUSH, due=None),
        _sig("commit-soon", ActionCategory.COMMITMENT, due="2026-09-02"),
    ]
    order = fallback_ranking(candidates)
    # 同一天内承诺优先于主线；无日期排最后
    assert order == ["commit-soon", "soon", "late", "nodate"]


def test_fallback_ranking_stable_on_full_tie() -> None:
    candidates = [
        _sig("b", ActionCategory.MAIN_PUSH),
        _sig("a", ActionCategory.MAIN_PUSH),
    ]
    assert fallback_ranking(candidates) == ["a", "b"]


def test_health_ok_when_signals_and_no_failures() -> None:
    health = evaluate_health(signal_count=3, ranking_degraded=False, source_failures=())
    assert health.level == "ok"
    assert health.ok


def test_health_degraded_on_ranking_fallback() -> None:
    health = evaluate_health(signal_count=3, ranking_degraded=True, source_failures=())
    assert health.level == "degraded"
    assert any("排序降级" in r for r in health.reasons)


def test_health_degraded_on_source_failure_and_zero_signals() -> None:
    health = evaluate_health(signal_count=0, ranking_degraded=False, source_failures=("飞书日历",))
    assert health.level == "degraded"
    assert any("飞书日历" in r for r in health.reasons)
    assert any("无任何" in r for r in health.reasons)


def test_collected_signal_count_counts_facts_and_candidates() -> None:
    collected = CollectedSignals(
        meetings=[MeetingFact("周会", "09:00")],
        candidates=[_sig("m1", ActionCategory.MAIN_PUSH)],
    )
    assert collected.signal_count == 2
