"""会议审批的 dry-run 默认批量应用、部分失败隔离与状态收口。"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.external_action import ExternalActionKind, ExternalActionState
from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.review import (
    UNRESOLVED,
    CandidateDecision,
    CandidateKind,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.providers.feishu.errors import FeishuError
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.external_action_outbox import latest_for_candidate, outbox_path
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.note_projects import merge_note_project
from summit_workbench.repositories.note_status import update_note_status
from summit_workbench.repositories.project_registry import (
    ProjectRegistry,
    load_project_registry,
)
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
    append_knowledge_note,
    append_project_followup,
    append_project_inbox,
    append_project_main,
    append_thread_inbox,
    parse_sink_target,
)
from summit_workbench.workflows.external_actions import (
    EXTERNAL_ACTION_ACCOUNTING_FAILED,
    OPERATION_OUTCOME_UNKNOWN,
    external_action_execution,
    mark_failed,
    mark_sending,
    mark_succeeded,
    mark_unknown,
    prepare_action,
    request_fingerprint,
    workspace_id_for_vault,
)

TaskCreator = Callable[..., str]
# 日历会议创建器：(summary, start_at, end_at, candidate_id) -> event_id
MeetingCreator = Callable[..., str]


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
    touched_paths: list[Path] = field(default_factory=list)


def _project_has_folder(work_root: Path, project: str) -> bool:
    """目标项目是否对应 Work 目录下的真实文件夹（仓库项目）——决定 inbox 落点。"""
    return (work_root / project).is_dir()


def _project_inbox_destination(vault_dir: Path, work_root: Path, project: str) -> str:
    """项目 inbox 落点：仓库项目 → 文件夹 inbox；知识线程（无文件夹）→ vault inbox。"""
    if _project_has_folder(work_root, project):
        return str(work_root / project / "input" / "inbox.md")
    return str(vault_dir / "inboxes" / f"{project}.md")


def _destination(entry: ReviewEntry, vault_dir: Path, work_root: Path) -> str:
    item = entry.candidate
    if item.route is RouteTarget.PROJECT_MAIN:
        return str(vault_dir / "projects" / f"{item.target_project}.md")
    if item.route is RouteTarget.PROJECT_FOLLOWUP:
        # 跟进事项写回主档案本体（同 project-main 文件，区块不同）。
        return str(vault_dir / "projects" / f"{item.target_project}.md")
    if item.route is RouteTarget.PROJECT_INBOX:
        return _project_inbox_destination(vault_dir, work_root, str(item.target_project))
    if item.route is RouteTarget.GLOBAL_INBOX:
        return str(vault_dir / "inbox.md")
    if item.route is RouteTarget.KNOWLEDGE_NOTE:
        rel, _heading = parse_sink_target(str(item.sink_target or ""))
        return str(vault_dir / rel.with_suffix(".md"))
    if item.route is RouteTarget.FEISHU_TASK:
        return "feishu-task"
    if item.route is RouteTarget.FEISHU_MEETING:
        return "feishu-meeting"
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
        elif item.route is RouteTarget.FEISHU_MEETING and item.start_at is None:
            reason = "新建会议需要开始时间（在「修改」里填开始时间）"
        elif item.route is RouteTarget.KNOWLEDGE_NOTE and not Path(destination).is_file():
            # 知识沉淀必须有已建好的目标页（小项目页 / 项目主页），否则无处可落。
            reason = f"写回目标不存在：{destination}（知识沉淀需要先建好目标页）"
        elif (
            item.route in (RouteTarget.PROJECT_MAIN, RouteTarget.PROJECT_FOLLOWUP)
            and not Path(destination).is_file()
        ):
            # 主档案落点必须已存在（用 `wb project new` 创建）；全局 inbox 会按需自建。
            reason = f"写回目标不存在：{destination}（可用 wb project new 创建后再批准）"
        elif (
            item.route is RouteTarget.PROJECT_INBOX
            and _project_has_folder(work_root, str(item.target_project))
            and not Path(destination).is_file()
        ):
            # 仓库项目的 inbox 必须已存在（沿用既有约定）。
            reason = f"写回目标不存在：{destination}"
        elif (
            item.route is RouteTarget.PROJECT_INBOX
            and not _project_has_folder(work_root, str(item.target_project))
            and not (vault_dir / "projects" / f"{item.target_project}.md").is_file()
        ):
            # 知识线程（无文件夹）的 inbox 由 vault 自建，但要求线程已建档。
            reason = (
                f"线程未建档，无法写入 inbox：{item.target_project}（可用 wb project new 创建）"
            )
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
    if item.route is RouteTarget.PROJECT_FOLLOWUP:
        path, _written = append_project_followup(
            vault_dir,
            str(item.target_project),
            item.description,
            item.candidate_id,
        )
        return str(path), None
    if item.route is RouteTarget.PROJECT_INBOX:
        if _project_has_folder(work_root, str(item.target_project)):
            path, _written = append_project_inbox(
                work_root,
                str(item.target_project),
                item.description,
                item.candidate_id,
            )
        else:
            path, _written = append_thread_inbox(
                vault_dir,
                str(item.target_project),
                item.description,
                item.candidate_id,
            )
        return str(path), None
    if item.route is RouteTarget.GLOBAL_INBOX:
        path, _written = append_global_inbox(vault_dir, item.description, item.candidate_id)
        return str(path), None
    if item.route is RouteTarget.KNOWLEDGE_NOTE:
        path, _written = append_knowledge_note(
            vault_dir,
            str(item.sink_target or ""),
            item.description,
            item.candidate_id,
            source_ref=_knowledge_source_ref(vault_dir, entry),
        )
        return str(path), None
    raise ValueError(f"非本地 route：{item.route.value}")


def _resolve_entry(entry: ReviewEntry, registry: ProjectRegistry) -> ReviewEntry:
    """把审批页里的项目名/别名升级为规范 ID；解析不到则原样保留。

    只做「向上升级」：别名 → 规范 ID。解析失败时不改写目标，沿用既有的
    「目标文件不存在 → 留在审批页标 error」安全行为（对齐决策 #2）。
    """
    resolved = registry.resolve(entry.candidate.target_project)
    if resolved is None or resolved == entry.candidate.target_project:
        return entry
    return replace(entry, candidate=replace(entry.candidate, target_project=resolved))


def _task_key(candidate_id: str) -> str:
    return candidate_id.split("#", 1)[0]


def _creator_call(
    creator: Callable[..., str],
    args: tuple[object, ...],
    operation_id: str,
    *,
    start_at: str | None = None,
) -> str:
    """给新版创建器传 operation_id，同时兼容旧的测试/集成回调签名。"""
    parameters = inspect.signature(creator).parameters
    accepts_keyword = "operation_id" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    kwargs: dict[str, object] = {}
    if accepts_keyword:
        kwargs["operation_id"] = operation_id
    if start_at is not None and (
        "start_at" in parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    ):
        kwargs["start_at"] = start_at
    if kwargs:
        return creator(*args, **kwargs)
    return creator(*args)


def _external_kind(entry: ReviewEntry) -> ExternalActionKind:
    if entry.candidate.route is RouteTarget.FEISHU_TASK:
        return ExternalActionKind.FEISHU_TASK
    return ExternalActionKind.FEISHU_MEETING


def _external_request(entry: ReviewEntry) -> dict[str, object]:
    item = entry.candidate
    if item.route is RouteTarget.FEISHU_TASK:
        request: dict[str, object] = {
            "description": item.description,
            "target_project": item.target_project,
            "due_date": item.due_date,
        }
        if item.start_at is not None:
            request["start_at"] = item.start_at
        return request
    return {
        "description": item.description,
        "target_project": item.target_project,
        "start_at": item.start_at,
        "end_at": item.end_at,
    }


def _run_external(
    entry: ReviewEntry,
    vault_dir: Path,
    *,
    task_creator: TaskCreator | None,
    meeting_creator: MeetingCreator | None,
) -> tuple[str, str, str]:
    """准备并执行一个外部动作；未知结果永远停在 outbox，不允许隐式重 POST。"""
    item = entry.candidate
    kind = _external_kind(entry)
    creator: Callable[..., str]
    args: tuple[object, ...]
    destination: str
    if kind is ExternalActionKind.FEISHU_TASK:
        if task_creator is None:
            raise ValueError("缺少飞书任务创建器")
        creator = task_creator
        args = (item.description, item.due_date, item.candidate_id)
        destination = "feishu-task"
    else:
        if meeting_creator is None:
            raise ValueError("缺少飞书日历会议创建器")
        creator = meeting_creator
        args = (item.description, item.start_at, item.end_at, item.candidate_id)
        destination = "feishu-meeting"

    workspace_id = workspace_id_for_vault(vault_dir)
    fingerprint = request_fingerprint(
        candidate_id=item.candidate_id,
        kind=kind,
        business_request=_external_request(entry),
    )
    existing = latest_for_candidate(
        vault_dir,
        item.candidate_id,
        workspace_id=workspace_id,
        kind=kind,
        request_fingerprint=fingerprint,
    )
    if existing is not None:
        if existing.state in {
            ExternalActionState.SUCCEEDED,
            ExternalActionState.RECONCILED_SUCCEEDED,
        }:
            if not existing.remote_id:
                raise ValueError("外部动作已成功但缺少 remote_id，请人工核对")
            return destination, existing.remote_id, existing.operation_id
        if existing.state is ExternalActionState.SENDING:
            raise ValueError("外部动作仍在发送中，请先重新核对，禁止重复创建")
        if existing.state in {
            ExternalActionState.UNKNOWN,
            ExternalActionState.RECONCILED_NOT_FOUND,
        }:
            raise ValueError("外部动作结果未知，请先重新核对或确认未创建后再重试")
        if existing.state is ExternalActionState.PREPARED:
            action = existing
        else:
            action = prepare_action(
                vault_dir,
                candidate_id=item.candidate_id,
                kind=kind,
                request=_external_request(entry),
                target_account_ref="feishu:user",
            )
    else:
        action = prepare_action(
            vault_dir,
            candidate_id=item.candidate_id,
            kind=kind,
            request=_external_request(entry),
            target_account_ref="feishu:user",
        )
    executor_id = str(uuid4())
    with external_action_execution(vault_dir, action, executor_id=executor_id):
        sending = mark_sending(vault_dir, action, executor_id=executor_id)
        try:
            remote_id = _creator_call(
                creator,
                args,
                sending.operation_id,
                start_at=item.start_at if kind is ExternalActionKind.FEISHU_TASK else None,
            )
        except FeishuError as exc:
            if getattr(exc, "result_unknown", False):
                mark_unknown(vault_dir, sending, str(exc))
                raise ValueError(f"飞书创建结果未知，请先重新核对：{exc}") from exc
            mark_failed(vault_dir, sending, str(exc))
            raise ValueError(str(exc)) from exc
        except (ValueError, OSError) as exc:
            mark_failed(vault_dir, sending, str(exc))
            raise

        # The provider has already performed the remote side effect.  Any
        # exception below is local accounting failure and must never become a
        # retryable ``failed`` state.
        try:
            succeeded = mark_succeeded(vault_dir, sending, remote_id)
        except Exception as exc:  # noqa: BLE001 - local persistence boundary
            try:
                mark_unknown(
                    vault_dir,
                    sending,
                    EXTERNAL_ACTION_ACCOUNTING_FAILED,
                    remote_id=remote_id.strip() or None,
                )
            except Exception as accounting_exc:  # noqa: BLE001 - preserve sending
                raise ValueError(OPERATION_OUTCOME_UNKNOWN) from accounting_exc
            raise ValueError(
                f"{EXTERNAL_ACTION_ACCOUNTING_FAILED}: 远端可能已创建，结果待核对"
            ) from exc
    return destination, remote_id, succeeded.operation_id


def _candidate_unchanged_since(current: ReviewEntry, original: ReviewEntry | None) -> bool:
    """最新页条目相对 apply 开始时的同 id 条目是否未被用户改动（P0-5 移除判据）。

    只比较用户在页上可改的字段（裁决 + 正文 + target_project/route/起止/截止）：
    任一被并发改动即视为「最新页已被改动」，条目留在页上、绝不静默覆盖用户编辑。
    """
    if original is None:
        return False
    c, o = current.candidate, original.candidate
    return (
        c.decision is o.decision
        and c.description == o.description
        and c.target_project == o.target_project
        and c.route == o.route
        and c.due_date == o.due_date
        and c.start_at == o.start_at
        and c.end_at == o.end_at
    )


def _note_path(vault_dir: Path, note_link: str) -> Path | None:
    if not note_link.startswith("[[") or not note_link.endswith("]]"):
        return None
    relative = note_link[2:-2]
    return vault_dir / f"{relative}.md"


# 候选类型 → 会议笔记中承载它的固定区块（来源锚点用；区块名与 vault schema 一致，不得改名）。
_KIND_SECTION: dict[CandidateKind, str] = {
    CandidateKind.DECISION: "已形成决策",
    CandidateKind.ACTION_ITEM: "明确行动项",
    CandidateKind.PROJECT_STATUS_CHANGE: "事实与进展",
    CandidateKind.TASK_CREATE: "明确行动项",
}


def _knowledge_source_ref(vault_dir: Path, entry: ReviewEntry) -> str | None:
    """知识沉淀的「出处」：可解析的 ``<会议笔记 source_id>#<区块>``（附证据锚点）。

    为什么必须是 ``路径#区块``：写进小项目页的结论要能被 SummitKnowledge 顺着引用核对回
    原话（契约 §2 的 ``anchor`` 定义）。此前这里直接塞了逐字稿时间戳（如 ``木子 00:03``），
    从检索侧看是个**无法解析**的悬空指针。

    会议笔记缺失时退回证据锚点（宁可给出可读证据，也不编造一个指向不存在文件的引用）。
    """
    source_id: str | None = None
    note_path = _note_path(vault_dir, entry.note_link)
    if note_path is not None and note_path.is_file():
        try:
            source_id = note_path.relative_to(vault_dir).with_suffix("").as_posix()
        except ValueError:  # note_link 指到 vault 之外：不接受
            source_id = None
    heading = _KIND_SECTION.get(entry.candidate.kind)
    anchor = f"{source_id}#{heading}" if source_id and heading else source_id
    evidence = entry.candidate.evidence.anchor if entry.candidate.evidence else None
    parts = [part for part in (anchor, evidence) if part]
    return " · ".join(parts) or None


def _queue_note_project(
    vault_dir: Path, note_project_adds: dict[Path, list[str]], entry: ReviewEntry
) -> None:
    """审批「已批准且目标项目已解析」成功后，登记来源会议笔记要并入的项目（改进 2）。

    收尾阶段（工作区锁内）统一把 ``unresolved`` 解析为实际写回项目——会议笔记由此
    进入该项目的时间线与 Obsidian 图谱。目标不明（unresolved / 缺省）不登记；
    全局 inbox / 新建会议等无项目落点的写回不产生关联。
    """
    target = entry.candidate.target_project
    if not target or target == UNRESOLVED:
        return
    note_path = _note_path(vault_dir, entry.note_link)
    if note_path is None:
        return
    projects = note_project_adds.setdefault(note_path, [])
    if target not in projects:
        projects.append(target)


def _update_meeting_states(
    vault_dir: Path,
    handled: list[ReviewEntry],
    remaining: list[ReviewEntry],
    *,
    now: datetime | None,
) -> list[Path]:
    touched_paths: list[Path] = []
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
        touched_paths.append(record_task(vault_dir, task.advanced_to(final_state), now=now))
        note_path = _note_path(vault_dir, entries[0].note_link)
        if note_path is not None:
            update_note_status(vault_dir, note_path, final_state.value)
            touched_paths.append(note_path)
    return touched_paths


def apply_meeting_review(
    vault_dir: Path,
    work_root: Path,
    *,
    apply: bool = False,
    task_creator: TaskCreator | None = None,
    meeting_creator: MeetingCreator | None = None,
    now: datetime | None = None,
) -> ApplyReport:
    """默认仅返回计划；``apply=True`` 才产生业务写回与审计。"""
    page = review_path(vault_dir)
    if not page.is_file():
        raise ValueError(f"审批页不存在：{page}")
    # apply 从旧快照解析后逐个做外部写回（分钟级）；收尾写页前必须重读最新页，
    # 窗口期内用户在页上的并发勾选/编辑不能被整页重写吞掉（P0-5 乐观合并）。
    page_snapshot = page.read_text(encoding="utf-8")
    parsed = parse_review_page(page_snapshot)
    if parsed.errors:
        raise ValueError("审批页语法错误：" + "; ".join(parsed.errors))
    registry = load_project_registry(vault_dir)
    entries = [_resolve_entry(entry, registry) for entry in parsed.entries]
    actions = _plan(entries, vault_dir, work_root)
    if not apply:
        return ApplyReport(
            True,
            actions,
            applied=0,
            rejected=0,
            failed=sum(not action.executable for action in actions),
        )

    by_id = {entry.candidate.candidate_id: entry for entry in entries}
    touched_paths: list[Path] = [page]
    handled: list[ReviewEntry] = []
    records: list[ExecutionRecord] = []
    failure_reasons: dict[str, str] = {}
    note_project_adds: dict[Path, list[str]] = {}
    failures = 0
    applied_count = rejected_count = 0
    for action in actions:
        entry = by_id[action.candidate_id]
        if action.reason == "already-completed":
            # 历史已应用条目同样补登记：旧版本落库的候选没做过会议回链解析。
            if action.decision is CandidateDecision.APPROVED:
                _queue_note_project(vault_dir, note_project_adds, entry)
            handled.append(entry)
            continue
        if not action.executable:
            failures += 1
            failure_reasons[action.candidate_id] = action.reason or "校验失败"
            continue
        if action.decision is CandidateDecision.REJECTED:
            record = make_execution_record(
                entry, destination="audit-only", result="rejected", now=now
            )
            rejected_count += 1
        else:
            try:
                external_id: str | None
                operation_id: str | None = None
                if entry.candidate.route is RouteTarget.FEISHU_TASK:
                    touched_paths.append(outbox_path(vault_dir))
                    destination, external_id, operation_id = _run_external(
                        entry,
                        vault_dir,
                        task_creator=task_creator,
                        meeting_creator=meeting_creator,
                    )
                elif entry.candidate.route is RouteTarget.FEISHU_MEETING:
                    touched_paths.append(outbox_path(vault_dir))
                    destination, external_id, operation_id = _run_external(
                        entry,
                        vault_dir,
                        task_creator=task_creator,
                        meeting_creator=meeting_creator,
                    )
                else:
                    destination, external_id = _write_local(entry, vault_dir, work_root)
                    touched_paths.append(Path(destination))
                record = make_execution_record(
                    entry,
                    destination=destination,
                    result="applied",
                    external_id=external_id,
                    operation_id=operation_id,
                    now=now,
                )
            except (FeishuError, ValueError, OSError) as exc:
                failures += 1
                failure_reasons[action.candidate_id] = str(exc)
                continue
            applied_count += 1
            _queue_note_project(vault_dir, note_project_adds, entry)
        touched_paths.append(append_execution(vault_dir, record))
        records.append(record)
        handled.append(entry)

    handled_ids = {entry.candidate.candidate_id for entry in handled}
    remaining = []
    for entry in entries:
        stable_id = entry.candidate.candidate_id
        if stable_id in handled_ids:
            continue
        remaining.append(replace(entry, apply_error=failure_reasons.get(stable_id)))
    archive_path = archive_executions(vault_dir, records, now=now) if records else None
    if archive_path is not None:
        touched_paths.append(archive_path)

    # P0-5 收尾「乐观合并」。整段收尾（重读最新页 + 合并 + 整页写 + 会议状态收口）
    # 是纯文件操作，放在工作区锁内；分钟级外部写回阶段不持锁（锁不跨 LLM/网络调用）。
    with workspace_lock(vault_dir.parent):
        latest_text = page.read_text(encoding="utf-8")
        if latest_text == page_snapshot:
            # 页面未被并发改动：维持既有行为（解析后剩余条目整页重写）。
            atomic_write_text(page, render_review_page(remaining))
        else:
            latest = parse_review_page(latest_text)
            if latest.errors:
                raise ValueError("审批页语法错误：" + "; ".join(latest.errors))
            # 只移除「本次 handled 且最新页中该候选未变」的条目；被并发改动的候选
            # 留在页上不动（账本已记 applied/rejected，下次 apply 按 already-completed
            # 幂等清理，不会重复执行）；失败候选的 error 标注只合并进最新页。
            start_by_id = {e.candidate.candidate_id: e for e in parsed.entries}
            merged: list[ReviewEntry] = []
            for entry in latest.entries:
                cid = entry.candidate.candidate_id
                if cid in handled_ids and _candidate_unchanged_since(entry, start_by_id.get(cid)):
                    continue
                if cid in failure_reasons and entry.apply_error is None:
                    entry = replace(entry, apply_error=failure_reasons[cid])
                merged.append(entry)
            atomic_write_text(page, render_review_page(merged))
        touched_paths.extend(_update_meeting_states(vault_dir, handled, remaining, now=now))
        # 改进 2：已批准且目标已解析的写回 → 把来源会议笔记的 unresolved 解析为项目
        # （幂等合并，进该项目时间线与 Obsidian 图谱）。merge 内部同锁重入，安全。
        for note_path, projects in note_project_adds.items():
            for project in projects:
                merge_note_project(vault_dir, note_path, project)
                touched_paths.append(note_path)
    return ApplyReport(
        False,
        actions,
        applied=applied_count,
        rejected=rejected_count,
        failed=failures,
        archive_path=archive_path,
        touched_paths=list(dict.fromkeys(touched_paths)),
    )
