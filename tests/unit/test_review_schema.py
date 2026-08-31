"""审批候选 schema、证据引用与路由规则测试（M1-1）。"""

from __future__ import annotations

from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    RouteTarget,
    candidate_id,
    route_candidate,
)


def test_evidence_valid_needs_anchor_or_quote():
    assert EvidenceRef(anchor="00:12:30").is_valid()
    assert EvidenceRef(quote="下周交初稿").is_valid()
    assert not EvidenceRef(speaker="张三").is_valid()  # 只有说话人不够
    assert not EvidenceRef().is_valid()
    assert not EvidenceRef(anchor="   ").is_valid()


def _candidate(**kw) -> ApprovalCandidate:
    base = dict(
        candidate_id="k#action-item-0",
        kind=CandidateKind.ACTION_ITEM,
        description="张三下周交初稿",
        target_project="ProjA",
        evidence=EvidenceRef(anchor="00:12:30"),
    )
    base.update(kw)
    return ApprovalCandidate(**base)  # type: ignore[arg-type]


def test_candidate_actionable_requires_project_and_evidence():
    assert _candidate().is_actionable()


def test_candidate_not_actionable_without_project():
    assert not _candidate(target_project=None).is_actionable()
    assert not _candidate(target_project="").is_actionable()
    assert not _candidate(target_project=UNRESOLVED).is_actionable()


def test_candidate_not_actionable_without_evidence():
    assert not _candidate(evidence=None).is_actionable()
    assert not _candidate(evidence=EvidenceRef(speaker="张三")).is_actionable()


def test_candidate_defaults():
    c = _candidate()
    assert c.decision == CandidateDecision.PENDING
    assert c.historical is False
    assert c.involves_others is False


def test_route_unresolved_project_goes_global_inbox():
    for proj in (None, "", UNRESOLVED):
        assert (
            route_candidate(
                target_project=proj,
                has_due_date=True,
                involves_others=True,
                is_next_step=True,
            )
            == RouteTarget.GLOBAL_INBOX
        )


def test_route_due_date_or_others_goes_feishu_task():
    assert (
        route_candidate(
            target_project="ProjA", has_due_date=True, involves_others=False, is_next_step=False
        )
        == RouteTarget.FEISHU_TASK
    )
    assert (
        route_candidate(
            target_project="ProjA", has_due_date=False, involves_others=True, is_next_step=True
        )
        == RouteTarget.FEISHU_TASK
    )


def test_route_next_step_goes_project_main():
    assert (
        route_candidate(
            target_project="ProjA", has_due_date=False, involves_others=False, is_next_step=True
        )
        == RouteTarget.PROJECT_MAIN
    )


def test_route_immature_idea_goes_project_inbox():
    assert (
        route_candidate(
            target_project="ProjA", has_due_date=False, involves_others=False, is_next_step=False
        )
        == RouteTarget.PROJECT_INBOX
    )


def test_candidate_id_is_stable_and_unique_per_kind_index():
    a = candidate_id("m1:n1", CandidateKind.ACTION_ITEM, 0)
    assert a == candidate_id("m1:n1", CandidateKind.ACTION_ITEM, 0)  # 重跑稳定
    assert a != candidate_id("m1:n1", CandidateKind.ACTION_ITEM, 1)
    assert a != candidate_id("m1:n1", CandidateKind.DECISION, 0)
