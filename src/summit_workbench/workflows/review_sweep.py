"""``wb review sweep``：一键清理测试/旧会议产生的待确认积压。

把指定会议笔记（默认全部 ``pending-review``，可用 ``--before`` 限定日期）从审批流程中
退役，三件事一次完成（正文原文保留，绝不删除）：

- 审批页上该会议的全部候选批量置为拒绝（应用时只归档，不写回）；
- 笔记 frontmatter 状态置为 ``ignored``；
- 会议任务状态收口为 ``ignored``（仅当当前是 ``pending-review``）。

与 :func:`review_apply.apply_meeting_review` 共用同一事实源（review/meetings.md）与
候选 ID 派生规则：候选经 ``note_link``（``[[meetings/notes/...]]``）对回笔记文件。
默认 dry-run 零写入，与 ``wb review apply`` 的既有安全姿态一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.review import CandidateDecision
from summit_workbench.repositories.meeting_archive import notes_dir
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.note_status import update_note_status
from summit_workbench.repositories.review_edit import set_decisions
from summit_workbench.repositories.review_page import parse_review_page, review_path
from summit_workbench.repositories.vault import load_note


@dataclass(frozen=True)
class SweepReport:
    dry_run: bool
    notes: list[Path]
    candidates: int


def _note_rel(vault_dir: Path, path: Path) -> str:
    return path.relative_to(vault_dir).with_suffix("").as_posix()


def _candidates_by_note(vault_dir: Path) -> dict[str, list[str]]:
    """审批页上按 note_link 分组的候选 ID；页面语法错误时拒绝清扫。"""
    page = review_path(vault_dir)
    if not page.is_file():
        return {}
    parsed = parse_review_page(page.read_text(encoding="utf-8"))
    if parsed.errors:
        raise ValueError("审批页存在语法错误，拒绝清扫：" + "; ".join(parsed.errors))
    buckets: dict[str, list[str]] = {}
    for entry in parsed.entries:
        buckets.setdefault(entry.note_link, []).append(entry.candidate.candidate_id)
    return buckets


def sweep_meeting_review(
    vault_dir: Path,
    *,
    apply: bool = False,
    before: date | None = None,
    now: datetime | None = None,
) -> SweepReport:
    """默认仅列出将退役的笔记；``apply=True`` 才写状态并批量拒绝候选。"""
    by_note = _candidates_by_note(vault_dir)
    notes: list[Path] = []
    for path in sorted(notes_dir(vault_dir).glob("*.md")):
        note = load_note(path)
        if note.parse_error is not None or note.meta.get("status") != "pending-review":
            continue
        if before is not None:
            raw_date = note.meta.get("date")
            if not raw_date:
                continue
            try:
                if date.fromisoformat(str(raw_date)) >= before:
                    continue
            except ValueError:
                continue
        notes.append(path)

    if not apply:
        total = sum(len(by_note.get(f"[[{_note_rel(vault_dir, p)}]]", [])) for p in notes)
        return SweepReport(dry_run=True, notes=notes, candidates=total)

    # 清扫（apply=True）= 审批页批量裁决 + 笔记状态 + 会议任务状态的多步串行 RMW；
    # 无外部调用，整段持锁最简（P0-1），避免与面板并发操作交错。
    with workspace_lock(vault_dir.parent):
        ids: list[str] = []
        for path in notes:
            rel = _note_rel(vault_dir, path)
            ids.extend(by_note.get(f"[[{rel}]]", []))
        if ids:
            set_decisions(vault_dir, ids, CandidateDecision.REJECTED)

        for path in notes:
            note = load_note(path)
            update_note_status(vault_dir, path, ProcessingState.IGNORED.value)
            idem_key = str(note.meta.get("idem_key") or "")
            if not idem_key:
                continue
            task = latest_task(vault_dir, idem_key)
            if task is not None and task.state is ProcessingState.PENDING_REVIEW:
                record_task(vault_dir, task.advanced_to(ProcessingState.IGNORED), now=now)
    return SweepReport(dry_run=False, notes=notes, candidates=len(ids))
