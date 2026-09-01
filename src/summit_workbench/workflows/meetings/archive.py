"""会议发现 → 原文归档的编排（PRD 3.1.9 L14/L15，M1-2）。

把「发现的会议 + 一个取稿回调」变成：幂等防重 → 取回完整逐字稿 → **在模型调用之前**
可靠落盘证据层 → 记录处理状态。取稿回调（``fetch``）由调用方注入（飞书 Note 主链路或本地
兜底），本模块因此不直接联网，可用假回调完整单测。

幂等（L14 第 6 条）：
- 飞书链路先按 ``meeting_id + note_id`` 查状态账本，已归档或更靠后即空转，连取稿都不做。
- 本地导入按逐字稿内容哈希防重（内容已在手才能算键，故先取后判）。
- 无 ``note_id`` 的飞书会议记为 ``unavailable`` 并留原因，不下载、不冒充完整处理（L14 第 7 条）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from summit_workbench.domain.pipeline import (
    MeetingTask,
    ProcessingState,
    SourceKind,
    local_idempotency_key,
    remote_idempotency_key,
)
from summit_workbench.domain.review import UNRESOLVED
from summit_workbench.repositories.meeting_archive import (
    MeetingArchiveInput,
    archive_transcript,
    slugify,
    transcript_stem,
    transcripts_dir,
)
from summit_workbench.repositories.meeting_state import latest_task, record_task

# 逐字稿已安全落盘（含及以后）的状态：这些状态下再次归档只会重复劳动，直接空转。
_ARCHIVED_OR_BEYOND = frozenset(
    {
        ProcessingState.ARCHIVED,
        ProcessingState.PROCESSED,
        ProcessingState.PENDING_REVIEW,
        ProcessingState.APPLIED,
        ProcessingState.IGNORED,
        ProcessingState.FAILED,  # 模型阶段失败，逐字稿已在 archived 时落盘
    }
)


@dataclass(frozen=True)
class DiscoveredMeeting:
    """一场待归档会议的最小描述（发现层给出，与供应商无关）。"""

    title: str
    date: str  # YYYY-MM-DD
    source: SourceKind
    meeting_id: str | None = None
    note_id: str | None = None


@dataclass(frozen=True)
class ArchiveReport:
    """单场会议归档的结果，供 CLI 汇报与 ``wb status`` 复用。"""

    idem_key: str
    state: ProcessingState
    action: str  # "archived" | "skipped-existing" | "unavailable"
    path: Path | None = None
    reason: str | None = None


TranscriptFetch = Callable[[DiscoveredMeeting], str]


def _archive_input(
    meeting: DiscoveredMeeting, text: str, projects: list[str], idem_key: str
) -> MeetingArchiveInput:
    return MeetingArchiveInput(
        date=meeting.date,
        title=meeting.title,
        transcript_text=text,
        source=meeting.source,
        meeting_id=meeting.meeting_id,
        note_id=meeting.note_id,
        idem_key=idem_key,
        projects=projects,
    )


def _skip_report(
    vault_dir: Path, meeting: DiscoveredMeeting, idem_key: str, state: ProcessingState
) -> ArchiveReport:
    stem = transcript_stem(meeting.date, slugify(meeting.title))
    path = transcripts_dir(vault_dir) / f"{stem}.md"
    return ArchiveReport(
        idem_key=idem_key,
        state=state,
        action="skipped-existing",
        path=path if path.exists() else None,
    )


def archive_meeting(
    vault_dir: Path,
    meeting: DiscoveredMeeting,
    fetch: TranscriptFetch,
    *,
    projects: list[str] | None = None,
    now: datetime | None = None,
) -> ArchiveReport:
    """幂等地归档一场会议的逐字稿。取稿失败向上抛，状态停在 discovered/fetched 便于重试。"""
    projects = projects or [UNRESOLVED]

    if meeting.source is SourceKind.FEISHU_NOTE:
        if not meeting.meeting_id:
            raise ValueError("飞书会议缺少 meeting_id，无法计算幂等键")

        # 无 note_id：无完整逐字稿权限，记 unavailable，不取稿、不冒充（L14 第 7 条）。
        if not meeting.note_id:
            idem_key = remote_idempotency_key(meeting.meeting_id, None)
            prior = latest_task(vault_dir, idem_key)
            if prior is not None and prior.state in _ARCHIVED_OR_BEYOND:
                return _skip_report(vault_dir, meeting, idem_key, prior.state)
            task = MeetingTask.for_remote(meeting.meeting_id, None)
            record_task(vault_dir, task, now=now)
            task = task.advanced_to(
                ProcessingState.UNAVAILABLE, reason="无完整逐字稿权限（该会议无 note_id）"
            )
            record_task(vault_dir, task, now=now)
            return ArchiveReport(idem_key, task.state, "unavailable", reason=task.reason)

        idem_key = remote_idempotency_key(meeting.meeting_id, meeting.note_id)
        prior = latest_task(vault_dir, idem_key)
        if prior is not None and prior.state in _ARCHIVED_OR_BEYOND:
            return _skip_report(vault_dir, meeting, idem_key, prior.state)

        task = MeetingTask.for_remote(meeting.meeting_id, meeting.note_id)
        record_task(vault_dir, task, now=now)  # discovered
        text = fetch(meeting)  # 取稿失败在此抛出，状态停在 discovered
        outcome = archive_transcript(vault_dir, _archive_input(meeting, text, projects, idem_key))
        task = task.advanced_to(ProcessingState.FETCHED).advanced_to(ProcessingState.ARCHIVED)
        record_task(vault_dir, task, now=now)
        action = "archived" if outcome.written else "skipped-existing"
        return ArchiveReport(idem_key, task.state, action, path=outcome.path)

    # 本地导入：内容已在手才能算幂等键，故先取后判。
    text = fetch(meeting)
    idem_key = local_idempotency_key(text)
    prior = latest_task(vault_dir, idem_key)
    if prior is not None and prior.state in _ARCHIVED_OR_BEYOND:
        return _skip_report(vault_dir, meeting, idem_key, prior.state)

    task = MeetingTask(
        idem_key=idem_key,
        source=SourceKind.LOCAL_FILE,
        state=ProcessingState.FETCHED,
        meeting_id=meeting.meeting_id,
    )
    record_task(vault_dir, task, now=now)  # fetched
    outcome = archive_transcript(vault_dir, _archive_input(meeting, text, projects, idem_key))
    task = task.advanced_to(ProcessingState.ARCHIVED)
    record_task(vault_dir, task, now=now)
    action = "archived" if outcome.written else "skipped-existing"
    return ArchiveReport(idem_key, task.state, action, path=outcome.path)


def archive_meetings(
    vault_dir: Path,
    meetings: Iterable[DiscoveredMeeting],
    fetch: TranscriptFetch,
    *,
    projects: list[str] | None = None,
    now: datetime | None = None,
) -> list[ArchiveReport]:
    """批量归档；逐场独立，单场取稿失败向上抛由调用方决定是否继续。"""
    return [archive_meeting(vault_dir, m, fetch, projects=projects, now=now) for m in meetings]
