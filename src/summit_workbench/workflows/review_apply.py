"""会议审批的 dry-run 默认批量应用、部分失败隔离与状态收口。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.review import (
    CandidateDecision,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.note_status import update_note_status
from summit_workbench.repositories.review_audit import (
    ExecutionRecord,
    append_execution,
    archive_executions,
    completed_decisions,
    completed_ids,
    make_execution_record,
)
from summit_workbench.repositories.review_page import (
    parse_review_page,
    render_review_page,
    review_path,
)
from summit_workbench.repositories.writeback import (
    append_global_inbox,
    append_project_inbox,
    append_project_main,
)

TaskCreator = Callable[[str, str | None, str], str]


@dataclass(frozen=True)
class ApplyAction:
    candidate_id: str
    decision: CandidateDecision
    destination: str
    executable: bool
    reason: str | None = None


@dataclass(frozen=True)
class ApplyReport:
    dry_run: bool
    actions: list[ApplyAction]
    applied: int
    rejected: int
    failed: int
    archive_path: Path | None = None


def _destination(entry: ReviewEntry, vault_dir: Path, work_root: Path) -> str:
    item = entry.candidate
    if item.route is RouteTarget.PROJECT_MAIN:
        return str(vault_dir / "projects" / f"{item.target_project}.md")
    if item.route is RouteTarget.PROJECT_INBOX:
        return str(work_root / str(item.target_project) / "input" / "inbox.md")
    if item.route is RouteTarget.GLOBAL_INBOX:
        return str(vault_dir / "inbox.md")
    if item.route is RouteTarget.FEISHU_TASK:
        return "feishu-task"
    return ""


def _plan(entries: list[ReviewEntry], vault_dir: Path, work_root: Path) -> list[ApplyAction]:
    actions: list[ApplyAction] = []
    done = completed_ids(vault_dir)
    for entry in entries:
        item = entry.candidate
        if item.decision is CandidateDecision.PENDING:
            continue
        destination = _destination(entry, vault_dir, work_root)
        if item.candidate_id in done:
            actions.append(
                ApplyAction(
                    item.candidate_id, item.decision, destination, True, "already-completed"
                )
            )
            continue
        if item.decision is CandidateDecision.REJECTED:
            actions.append(ApplyAction(item.candidate_id, item.decision, "audit-only", True))
            continue
        reason: str | None = None
        if not item.is_actionable():
            reason = "缺少已解析 target_project 或有效 evidence"
        elif item.route is None:
            reason = "缺少 route"
        elif item.route is not RouteTarget.FEISHU_TASK and not Path(destination).is_file():
            reason = f"写回目标不存在：{destination}"
        actions.append(
            ApplyAction(item.candidate_id, item.decision, destination, reason is None, reason)
        )
    return actions


def _write_local(entry: ReviewEntry, vault_dir: Path, work_root: Path) -> tuple[str, str | None]:
    item = entry.candidate
    assert item.route is not None
    if item.route is RouteTarget.PROJECT_MAIN:
        path, _written = append_project_main(
            vault_dir,
            str(item.target_project),
            item.description,
            item.candidate_id,
            item.kind,
        )
        return str(path), None
    if item.route is RouteTarget.PROJECT_INBOX:
        path, _written = append_project_inbox(
            work_root,
            str(item.target_project),
            item.description,
            item.candidate_id,
        )
        return str(path), None
    if item.route is RouteTarget.GLOBAL_INBOX:
        path, _written = append_global_inbox(
            vault_dir, item.description, item.candidate_id
        )
        return str(path), None
    raise ValueError(f"非本地 route：{item.route.value}")


def _task_key(candidate_id: str) -> str:
    return candidate_id.split("#", 1)[0]


def _note_path(vault_dir: Path, note_link: str) -> Path | None:
    if not note_link.startswith("[[") or not note_link.endswith("]]"):
        return None
    relative = note_link[2:-2]
    return vault_dir / f"{relative}.md"


def _update_meeting_states(
    vault_dir: Path,
    handled: list[ReviewEntry],
    remaining: list[ReviewEntry],
    *,
    now: datetime | None,
) -> None:
    remaining_keys = {_task_key(entry.candidate.candidate_id) for entry in remaining}
    grouped: dict[str, list[ReviewEntry]] = {}
    for entry in handled:
        grouped.setdefault(_task_key(entry.candidate.candidate_id), []).append(entry)
    for task_key, entries in grouped.items():
        if task_key in remaining_keys:
            continue
        task = latest_task(vault_dir, task_key)
        if task is None or task.state is not ProcessingState.PENDING_REVIEW:
            continue
        historical = completed_decisions(vault_dir, task_key)
        final_state = (
            ProcessingState.APPLIED
            if CandidateDecision.APPROVED in historical
            else ProcessingState.IGNORED
        )
        record_task(vault_dir, task.advanced_to(final_state), now=now)
        note_path = _note_path(vault_dir, entries[0].note_link)
        if note_path is not None:
            update_note_status(note_path, final_state.value)


def apply_meeting_review(
    vault_dir: Path,
    work_root: Path,
    *,
    apply: bool = False,
    task_creator: TaskCreator | None = None,
    now: datetime | None = None,
) -> ApplyReport:
    """默认仅返回计划；``apply=True`` 才产生业务写回与审计。"""
    page = review_path(vault_dir)
    if not page.is_file():
        raise ValueError(f"审批页不存在：{page}")
    parsed = parse_review_page(page.read_text(encoding="utf-8"))
    if parsed.errors:
        raise ValueError("审批页语法错误：" + "; ".join(parsed.errors))
    actions = _plan(parsed.entries, vault_dir, work_root)
    if not apply:
        return ApplyReport(
            True,
            actions,
            applied=0,
            rejected=0,
            failed=sum(not action.executable for action in actions),
        )

    by_id = {entry.candidate.candidate_id: entry for entry in parsed.entries}
    handled: list[ReviewEntry] = []
    records: list[ExecutionRecord] = []
    failures = 0
    applied_count = rejected_count = 0
    for action in actions:
        entry = by_id[action.candidate_id]
        if action.reason == "already-completed":
            handled.append(entry)
            continue
        if not action.executable:
            failures += 1
            continue
        if action.decision is CandidateDecision.REJECTED:
            record = make_execution_record(
                entry, destination="audit-only", result="rejected", now=now
            )
            rejected_count += 1
        else:
            try:
                external_id: str | None
                if entry.candidate.route is RouteTarget.FEISHU_TASK:
                    if task_creator is None:
                        raise ValueError("缺少飞书任务创建器")
                    external_id = task_creator(
                        entry.candidate.description,
                        entry.candidate.due_date,
                        entry.candidate.candidate_id,
                    )
                    destination = "feishu-task"
                else:
                    destination, external_id = _write_local(entry, vault_dir, work_root)
                record = make_execution_record(
                    entry,
                    destination=destination,
                    result="applied",
                    external_id=external_id,
                    now=now,
                )
            except (ValueError, OSError):
                failures += 1
                continue
            applied_count += 1
        append_execution(vault_dir, record)
        records.append(record)
        handled.append(entry)

    handled_ids = {entry.candidate.candidate_id for entry in handled}
    remaining = [
        entry for entry in parsed.entries if entry.candidate.candidate_id not in handled_ids
    ]
    archive_path = archive_executions(vault_dir, records, now=now) if records else None
    temporary = page.with_suffix(".md.tmp")
    temporary.write_text(render_review_page(remaining), encoding="utf-8")
    temporary.replace(page)
    _update_meeting_states(vault_dir, handled, remaining, now=now)
    return ApplyReport(
        False,
        actions,
        applied=applied_count,
        rejected=rejected_count,
        failed=failures,
        archive_path=archive_path,
    )
