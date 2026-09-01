"""已归档逐字稿 → 结构化笔记 → pending-review 的可靠端到端编排。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import SecretStr

from summit_workbench.domain.pipeline import ProcessingState, SourceKind
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.usage import UsageRecord
from summit_workbench.repositories.meeting_archive import transcript_stem
from summit_workbench.repositories.meeting_note import MeetingNoteInput, archive_meeting_note
from summit_workbench.repositories.meeting_state import latest_task, record_task
from summit_workbench.repositories.model_errors import clear_model_error, record_model_error
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.meetings.processor import ProcessingFailure, process_transcript

_DONE_STATES = frozenset(
    {
        ProcessingState.PENDING_REVIEW,
        ProcessingState.APPLIED,
        ProcessingState.IGNORED,
    }
)


@dataclass(frozen=True)
class ProcessReport:
    task_key: str
    state: ProcessingState
    action: str  # processed | skipped-existing | failed
    note_path: Path | None = None
    error_path: Path | None = None
    model_calls: int = 0
    chunks: int = 0
    reason: str | None = None


def _clean_transcript(body: str) -> str:
    lines = body.splitlines()
    kept = [line for line in lines if not line.startswith("# ") and not line.startswith("<!--")]
    text = "\n".join(kept).strip()
    if not text:
        raise ValueError("逐字稿笔记正文为空")
    return text


def _title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].removesuffix(" · 完整逐字稿").strip() or fallback
    return fallback


def _projects(meta: dict[str, object]) -> list[str]:
    raw = meta.get("projects")
    return [str(item) for item in raw] if isinstance(raw, list) else []


def process_archived_transcript(
    vault_dir: Path,
    transcript_path: Path,
    cfg: ModelConfig,
    api_key: SecretStr,
    *,
    prompt: Prompt,
    merger_prompt: Prompt,
    task_key: str | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] | None = None,
    now: datetime | None = None,
) -> ProcessReport:
    """只在完整原文已归档后处理；任何失败只记队列，不写半成品笔记。"""
    note = load_note(transcript_path)
    if note.parse_error is not None or note.meta.get("type") != "meeting-transcript":
        raise ValueError(f"不是有效的 meeting-transcript：{transcript_path}")
    resolved_key = task_key or str(note.meta.get("idem_key") or "")
    if not resolved_key:
        meeting_id = str(note.meta.get("meeting_id") or "")
        note_id = str(note.meta.get("note_id") or "")
        if meeting_id:
            resolved_key = f"{meeting_id}:{note_id}" if note_id else meeting_id
    if not resolved_key:
        raise ValueError("逐字稿缺少 idem_key；旧本地归档请显式传 --task-key")

    task = latest_task(vault_dir, resolved_key)
    if task is None:
        raise ValueError(f"状态账本不存在任务：{resolved_key}")
    if task.state in _DONE_STATES:
        return ProcessReport(resolved_key, task.state, "skipped-existing")
    if task.state not in {ProcessingState.ARCHIVED, ProcessingState.FAILED}:
        raise ValueError(f"任务状态 {task.state.value} 不能开始结构化处理")

    try:

        def save_usage(usage: UsageRecord) -> None:
            append_usage(vault_dir, usage)

        processed = process_transcript(
            cfg,
            api_key,
            _clean_transcript(note.body),
            prompt=prompt,
            merger_prompt=merger_prompt,
            task_key=resolved_key,
            client=client,
            sleep=sleep,
            usage_sink=save_usage,
        )
        source = SourceKind(str(note.meta.get("source")))
        title = _title(note.body, transcript_path.stem)
        date = str(note.meta.get("date"))
        slug = transcript_path.stem.removesuffix("-transcript").removeprefix(f"{date}-")
        stem = transcript_stem(date, slug)
        outcome = archive_meeting_note(
            vault_dir,
            MeetingNoteInput(
                date=date,
                title=title,
                idem_key=resolved_key,
                extraction=processed.extraction,
                source=source,
                transcript_stem=stem,
                model_id=cfg.model_id,
                prompt_version=processed.prompt_version,
                meeting_id=str(note.meta.get("meeting_id") or "") or None,
                note_id=str(note.meta.get("note_id") or "") or None,
                projects=_projects(note.meta),
            ),
        )
    except ProcessingFailure as exc:
        failed = task.advanced_to(ProcessingState.FAILED, reason=str(exc))
        record_task(vault_dir, failed, now=now)
        error_path = record_model_error(
            vault_dir,
            task_key=resolved_key,
            model_id=cfg.model_id,
            prompt_version=prompt.version_label,
            stage=exc.stage,
            attempts=exc.attempts,
            reason=str(exc),
            transcript_path=transcript_path,
            now=now,
        )
        return ProcessReport(
            resolved_key,
            failed.state,
            "failed",
            error_path=error_path,
            reason=str(exc),
        )

    processed_task = task.advanced_to(ProcessingState.PROCESSED)
    record_task(vault_dir, processed_task, now=now)
    pending = processed_task.advanced_to(ProcessingState.PENDING_REVIEW)
    record_task(vault_dir, pending, now=now)
    clear_model_error(vault_dir, resolved_key)
    return ProcessReport(
        resolved_key,
        pending.state,
        "processed" if outcome.written else "skipped-existing",
        note_path=outcome.path,
        model_calls=len(processed.usage_records),
        chunks=processed.chunk_count,
    )
