"""从结构化会议笔记生成稳定的决策/行动审批候选。"""

from __future__ import annotations

import re
from pathlib import Path

from summit_workbench.domain.meeting import ActionItem, Decision, MeetingExtraction
from summit_workbench.domain.review import (
    UNRESOLVED,
    ApprovalCandidate,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    candidate_id,
    route_candidate,
)
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.vault import ParsedNote, load_note

_DECISION_RE = re.compile(r"^- (.+)（项目：(.+)；证据：(.+)）$")
_ACTION_RE = re.compile(r"^- (.+)（项目：(.+)；截止：(.+)；证据：(.+)）$")


def _section(body: str, heading: str) -> list[str]:
    lines = body.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    result: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            result.append(line.strip())
    return result


def _fallback_extraction(note: ParsedNote) -> MeetingExtraction:
    """兼容 M1-3 早期未在 frontmatter 保存 extraction 的既有笔记。"""
    decisions: list[Decision] = []
    for line in _section(note.body, "## 已形成决策"):
        match = _DECISION_RE.match(line)
        if match:
            description, project, evidence = match.groups()
            decisions.append(
                Decision(
                    description=description,
                    target_project=None if project == UNRESOLVED else project,
                    evidence=evidence,
                )
            )
    actions: list[ActionItem] = []
    for line in _section(note.body, "## 明确行动项"):
        match = _ACTION_RE.match(line)
        if match:
            description, project, due, evidence = match.groups()
            actions.append(
                ActionItem(
                    description=description,
                    target_project=None if project == UNRESOLVED else project,
                    due_date=None if due == "无" else due,
                    evidence=evidence,
                )
            )
    return MeetingExtraction(
        one_minute_summary="（从既有会议笔记恢复审批候选）",
        decisions=decisions,
        action_items=actions,
    )


def _extraction(note: ParsedNote) -> MeetingExtraction:
    raw = note.meta.get("extraction")
    if isinstance(raw, dict):
        return MeetingExtraction.model_validate(raw)
    return _fallback_extraction(note)


def _title(note: ParsedNote) -> str:
    for line in note.body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return note.path.stem


def _evidence(value: str) -> EvidenceRef:
    speaker = value.split(maxsplit=1)[0] if value.strip() else None
    return EvidenceRef(speaker=speaker, anchor=value)


def candidates_from_note(
    path: Path, vault_dir: Path, *, historical: bool = False
) -> list[ReviewEntry]:
    """只生成决策和明确行动项；普通事实绝不推断成状态变化。

    ``historical=True``（历史补导 M1-7）给候选打 ``historical`` 标记，便于审批页区分。
    """
    note = load_note(path)
    if note.parse_error is not None or note.meta.get("type") != "meeting-note":
        raise ValueError(f"不是有效的 meeting-note：{path}")
    idem_key = str(note.meta.get("idem_key") or "")
    if not idem_key:
        raise ValueError(f"会议笔记缺少 idem_key：{path}")
    extraction = _extraction(note)
    registry = load_project_registry(vault_dir)
    title = _title(note)
    date = str(note.meta.get("date") or "")
    note_rel = path.relative_to(vault_dir).with_suffix("")
    note_link = f"[[{note_rel.as_posix()}]]"
    transcript_link = str(note.meta.get("transcript") or "")
    entries: list[ReviewEntry] = []

    for index, decision in enumerate(extraction.decisions):
        target = registry.resolve(decision.target_project) or decision.target_project or UNRESOLVED
        candidate = ApprovalCandidate(
            candidate_id=candidate_id(idem_key, CandidateKind.DECISION, index),
            kind=CandidateKind.DECISION,
            description=decision.description,
            target_project=target,
            route=route_candidate(
                target_project=target,
                has_due_date=False,
                involves_others=False,
                is_next_step=True,
            ),
            evidence=_evidence(decision.evidence),
            is_next_step=True,
            historical=historical,
        )
        entries.append(
            ReviewEntry(candidate, decision.description, date, title, note_link, transcript_link)
        )

    for index, action in enumerate(extraction.action_items):
        target = registry.resolve(action.target_project) or action.target_project or UNRESOLVED
        candidate = ApprovalCandidate(
            candidate_id=candidate_id(idem_key, CandidateKind.ACTION_ITEM, index),
            kind=CandidateKind.ACTION_ITEM,
            description=action.description,
            target_project=target,
            route=route_candidate(
                target_project=target,
                has_due_date=action.due_date is not None,
                involves_others=False,
                is_next_step=True,
            ),
            evidence=_evidence(action.evidence),
            due_date=action.due_date,
            is_next_step=True,
            historical=historical,
        )
        entries.append(
            ReviewEntry(candidate, action.description, date, title, note_link, transcript_link)
        )
    return entries
