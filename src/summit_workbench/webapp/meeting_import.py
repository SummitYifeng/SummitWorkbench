"""会议逐字稿导入链路：先归档，后由可恢复单 worker 异步结构化。"""

from __future__ import annotations

import hashlib
import queue
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from summit_workbench.config.app_support import meeting_import_jobs_file
from summit_workbench.domain.pipeline import ProcessingState, SourceKind
from summit_workbench.repositories.meeting_archive import transcripts_dir
from summit_workbench.repositories.meeting_import_jobs import (
    ImportJob,
    ImportJobStage,
    ImportJobStatus,
    ImportJobStore,
)
from summit_workbench.repositories.meeting_state import latest_task
from summit_workbench.repositories.review_page import (
    RefreshOutcome,
    refresh_review_page,
    review_path,
)
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.model_config import _load_model_config_for_context
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, run_local_mutation
from summit_workbench.workflows.meetings.archive import (
    ArchiveReport,
    DiscoveredMeeting,
    archive_meeting,
)
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note


def _jobs_file(ctx: WebContext) -> Path:
    workspace_id = ctx.workspace_id
    if not workspace_id:
        workspace_id = hashlib.sha256(str(ctx.vault_dir.resolve()).encode()).hexdigest()[:24]
    home = ctx.active_workspace.home if ctx.active_workspace is not None else None
    return meeting_import_jobs_file(workspace_id, home=home)


class MeetingImportManager:
    """单 workspace 的可恢复会议导入 worker；App 退出时不继续发起新模型调用。"""

    def __init__(self, ctx: WebContext, runtime: MutationRuntime) -> None:
        self.ctx = ctx
        self.runtime = runtime
        self.store = ImportJobStore(_jobs_file(ctx))
        self._queue: queue.Queue[str] = queue.Queue()
        self._submit_lock = threading.Lock()
        self._stop = threading.Event()
        self._worker_condition = threading.Condition()
        self._accepting = True
        self._paused = False
        self._active_job_id: str | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._recover()
        self._thread = threading.Thread(target=self._work, name="wb-meeting-import", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._worker_condition:
            self._worker_condition.notify_all()

    def pause_and_wait(self, *, timeout: float = 90.0) -> bool:
        """Reject new imports and wait for an active job before switching workspace."""
        deadline = time.monotonic() + timeout
        with self._worker_condition:
            self._accepting = False
            self._paused = True
            self._worker_condition.notify_all()
            return self._worker_condition.wait_for(
                lambda: self._active_job_id is None,
                timeout=max(0.0, deadline - time.monotonic()),
            )

    def resume(self) -> None:
        """Reopen the old workspace worker after a switch attempt is cancelled."""
        with self._worker_condition:
            self._accepting = True
            self._paused = False
            self._worker_condition.notify_all()

    def _recover(self) -> None:
        jobs = self.store.list_recent()
        if self.store.corrupt_backup is not None:
            self._rebuild_from_meeting_ledger()
            jobs = self.store.list_recent()
        done = {
            ProcessingState.PROCESSED,
            ProcessingState.PENDING_REVIEW,
            ProcessingState.APPLIED,
            ProcessingState.IGNORED,
        }
        for job in jobs:
            if job.status is ImportJobStatus.QUEUED:
                self._queue.put(job.job_id)
            elif job.status is ImportJobStatus.RUNNING:
                state = latest_task(self.ctx.vault_dir, job.idem_key)
                if state is not None and state.state in done:
                    self.store.update(
                        job.job_id,
                        status=ImportJobStatus.SUCCEEDED,
                        stage=ImportJobStage.COMPLETED,
                        result={"message": "App 重启后核对到任务已完成"},
                    )
                elif state is not None and state.state is ProcessingState.ARCHIVED:
                    self.store.update(
                        job.job_id,
                        status=ImportJobStatus.QUEUED,
                        stage=ImportJobStage.ARCHIVED,
                    )
                    self._queue.put(job.job_id)
                elif state is not None and state.state is ProcessingState.FAILED:
                    self.store.update(
                        job.job_id,
                        status=ImportJobStatus.FAILED,
                        error=state.reason or "结构化失败，请继续处理",
                        retryable=True,
                    )
                else:
                    self.store.update(
                        job.job_id,
                        status=ImportJobStatus.FAILED,
                        error="App 上次退出时任务状态无法确认，请继续处理",
                        retryable=True,
                    )

    def _rebuild_from_meeting_ledger(self) -> None:
        """队列文件损坏时，用 vault 中已归档逐字稿和状态账本重建最小任务视图。"""
        for transcript_path in transcripts_dir(self.ctx.vault_dir).glob("*.md"):
            note = load_note(transcript_path)
            idem_key = note.meta.get("idem_key")
            if note.parse_error is not None or not isinstance(idem_key, str) or not idem_key:
                continue
            state = latest_task(self.ctx.vault_dir, idem_key)
            if state is None:
                continue
            try:
                size = transcript_path.stat().st_size
            except OSError:
                size = 0
            job = self.store.create(None, idem_key, transcript_path.name, size)
            if state.state is ProcessingState.ARCHIVED:
                self.store.update(
                    job.job_id,
                    status=ImportJobStatus.QUEUED,
                    stage=ImportJobStage.ARCHIVED,
                    transcript_path=str(transcript_path),
                )
            elif state.state is ProcessingState.FAILED:
                self.store.update(
                    job.job_id,
                    status=ImportJobStatus.FAILED,
                    stage=ImportJobStage.STRUCTURING,
                    transcript_path=str(transcript_path),
                    error=state.reason or "结构化失败",
                    retryable=True,
                )
            else:
                self.store.update(
                    job.job_id,
                    status=ImportJobStatus.SUCCEEDED,
                    stage=ImportJobStage.COMPLETED,
                    transcript_path=str(transcript_path),
                    result={"message": "从会议状态账本恢复", "note_path": str(transcript_path)},
                )

    def _work(self) -> None:
        while not self._stop.is_set():
            with self._worker_condition:
                self._worker_condition.wait_for(
                    lambda: self._stop.is_set() or not self._paused,
                    timeout=0.1,
                )
                if self._stop.is_set():
                    return
            try:
                job_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            with self._worker_condition:
                if self._stop.is_set():
                    self._queue.task_done()
                    return
                if self._paused:
                    self._queue.put(job_id)
                    self._queue.task_done()
                    continue
                self._active_job_id = job_id
            try:
                self._process(job_id)
            finally:
                with self._worker_condition:
                    self._active_job_id = None
                    self._worker_condition.notify_all()
                self._queue.task_done()

    def submit(self, file_name: str, text: str) -> ImportJob:
        """串行化上传归档，保证并发重复上传只会创建一个任务。"""
        with self._submit_lock:
            with self._worker_condition:
                if not self._accepting:
                    raise ValueError("工作台正在切换，会议导入已暂停")
            return self._submit_locked(file_name, text)

    def _submit_locked(self, file_name: str, text: str) -> ImportJob:
        """先归档原文，再把模型阶段排入单 worker。"""
        tmp_dir = Path(tempfile.mkdtemp(prefix="wb-web-import-"))
        job: ImportJob | None = None
        try:
            target = tmp_dir / Path(file_name).name
            target.write_text(text, encoding="utf-8")
            from summit_workbench.workflows.meetings.backfill import scan_for_import

            items = scan_for_import(self.ctx.vault_dir, target)
            if not items:
                raise ValueError("未识别为可导入的逐字稿（需要 .md/.txt 且内容非空）")
            item = items[0]
            existing = self.store.find_by_idem_key(item.idem_key)
            if existing is not None:
                return existing
            job = self.store.create(None, item.idem_key, file_name, len(text.encode("utf-8")))
            if item.done:
                completed = self.store.update(
                    job.job_id,
                    status=ImportJobStatus.SUCCEEDED,
                    stage=ImportJobStage.COMPLETED,
                    result={"message": "导入完成（幂等，未重复归档）", "idempotent": True},
                )
                return completed or job
            meeting = DiscoveredMeeting(
                title=item.title, date=item.date, source=SourceKind.LOCAL_FILE
            )

            def fetch(_meeting: DiscoveredMeeting) -> str:
                return text

            def save_archive(_operation_id: str) -> LocalMutationOutcome[ArchiveReport]:
                report = archive_meeting(self.ctx.vault_dir, meeting, fetch)
                paths = [
                    self.ctx.vault_dir / "_signals" / "meeting-state" / "log.jsonl",
                ]
                if report.path is not None:
                    paths.append(report.path)
                return LocalMutationOutcome(report, tuple(paths))

            result = self.runtime.run("meetings/archive", save_archive)
            report = result.business_return
            if report.path is None:
                raise ValueError("归档未产生逐字稿")
            operation_ids = [str(result.operation_id)] if result.operation_id else []
            job = (
                self.store.update(
                    job.job_id,
                    status=ImportJobStatus.QUEUED,
                    stage=ImportJobStage.ARCHIVED,
                    transcript_path=str(report.path),
                    operation_ids=operation_ids,
                )
                or job
            )
            self._queue.put(job.job_id)
            return job
        except Exception as exc:
            if job is not None:
                self.store.update(
                    job.job_id,
                    status=ImportJobStatus.FAILED,
                    error=str(exc),
                    retryable=True,
                )
            raise ValueError(str(exc)) from exc
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def retry(self, job_id: str) -> ImportJob | None:
        with self._worker_condition:
            if not self._accepting:
                raise ValueError("工作台正在切换，会议处理已暂停")
        job = self.store.get(job_id)
        if job is None:
            return None
        if job.status not in {ImportJobStatus.FAILED, ImportJobStatus.PARTIAL}:
            return job
        updated = self.store.update(
            job_id,
            status=ImportJobStatus.QUEUED,
            stage=ImportJobStage.ARCHIVED,
            error=None,
            retryable=False,
        )
        if updated is not None:
            self._queue.put(job_id)
        return updated

    def _process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or not job.transcript_path:
            return
        self.store.update(job_id, status=ImportJobStatus.RUNNING, stage=ImportJobStage.STRUCTURING)
        try:
            from summit_workbench.config.secrets import resolve_credential
            from summit_workbench.prompts import load_prompt
            from summit_workbench.workflows.meetings.process_archived import (
                ProcessMutationRunner,
                process_archived_transcript,
            )

            cfg = _load_model_config_for_context(self.ctx, "meeting")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("meeting-processor")
            merger_prompt = load_prompt("meeting-merger")

            def mutation_runner(
                _vault: Path,
                action: str,
                mutation: Callable[[str], LocalMutationOutcome[object]],
            ) -> object:
                return self.runtime.run(action, mutation)

            report = process_archived_transcript(
                self.ctx.vault_dir,
                Path(job.transcript_path),
                cfg,
                api_key,
                prompt=prompt,
                merger_prompt=merger_prompt,
                task_key=job.idem_key,
                local_mutation=cast(ProcessMutationRunner, mutation_runner),
            )
            if report.action == "failed":
                self.store.update(
                    job_id,
                    status=ImportJobStatus.FAILED,
                    error=report.reason,
                    retryable=True,
                    result={"message": report.reason or "结构化失败"},
                )
                return
            candidates = 0
            operation_ids = list(job.operation_ids)
            if report.operation_id:
                operation_ids.append(report.operation_id)
            note_path = report.note_path
            if note_path is None and report.action == "skipped-existing" and job.result:
                stored_note_path = job.result.get("note_path")
                if isinstance(stored_note_path, str):
                    note_path = Path(stored_note_path)
            if note_path is not None:
                try:
                    self.store.update(job_id, stage=ImportJobStage.CANDIDATES)
                    entries = candidates_from_note(note_path, self.ctx.vault_dir, historical=False)
                    if entries:

                        def save_review(_operation_id: str) -> LocalMutationOutcome[RefreshOutcome]:
                            return LocalMutationOutcome(
                                refresh_review_page(self.ctx.vault_dir, entries),
                                (review_path(self.ctx.vault_dir),),
                            )

                        review_result = self.runtime.run("meetings/review", save_review)
                        if review_result.operation_id:
                            operation_ids.append(review_result.operation_id)
                        candidates = len(entries)
                except Exception as exc:
                    self.store.update(
                        job_id,
                        status=ImportJobStatus.PARTIAL,
                        error=str(exc),
                        retryable=True,
                        operation_ids=operation_ids,
                        result={
                            "message": "结构化已完成，但候选生成失败",
                            "note_path": str(note_path),
                        },
                    )
                    return
            result = {
                "message": "导入完成",
                "candidates": candidates,
                "note_path": str(note_path) if note_path else None,
            }
            self.store.update(
                job_id,
                status=ImportJobStatus.SUCCEEDED,
                stage=ImportJobStage.COMPLETED,
                operation_ids=operation_ids,
                result=result,
                retryable=False,
            )
        except Exception as exc:
            self.store.update(
                job_id,
                status=ImportJobStatus.FAILED,
                error=str(exc),
                retryable=True,
                result={"message": "导入失败"},
            )


def _job_payload(job: ImportJob) -> dict[str, object]:
    return job.model_dump(mode="json")


def _run_web_import(
    ctx: WebContext,
    transcript_path: Path,
    *,
    local_mutation: Callable[..., object] | None = None,
) -> dict[str, object]:
    """把一份本地逐字稿全自动归档 + 结构化 + 生成审批候选（复用 backfill 链路）。

    与 wb meeting import 同一套幂等逻辑；Web 侧按产品约定走全自动（不二次确认），
    软预算只报告不阻断（PRD：预算是提醒线，不是停机线）。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.observability.status import load_budget_settings
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError
    from summit_workbench.repositories.usage_ledger import monthly_totals
    from summit_workbench.workflows.meetings.backfill import (
        plan_backfill,
        run_backfill,
        scan_for_import,
    )

    items = scan_for_import(ctx.vault_dir, transcript_path)
    if not items:
        return {"ok": False, "message": "未识别为可导入的逐字稿（需要 .md/.txt 且内容非空）"}

    # 先检查幂等账本：重复导入已经完成的逐字稿不应因为当前模型凭据不可用而
    # 被误报为“模型未配置”，也不应再次调用模型或写入归档。
    if all(item.done for item in items):
        skipped = len(items)
        lines = [f"处理 0、跳过 {skipped}、失败 0、生成候选 0"]
        return {
            "ok": True,
            "status": "success",
            "message": "导入完成：" + "；".join(lines) + "（幂等，未重复调用模型）",
            "details": lines,
            "operation_ids": [],
            "estimate": {
                "pending": 0,
                "already_done": skipped,
                "est_input_tokens": 0,
                "est_output_tokens": 0,
                "est_cost": 0,
                "currency": "—",
                "projected_month_cost": 0,
                "soft_limit": None,
                "crosses_soft_budget": False,
            },
        }

    try:
        cfg = _load_model_config_for_context(ctx, "meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return {"ok": False, "status": "failed", "message": f"导入未启动（模型未配置？）：{exc}"}

    month = datetime.now(ZoneInfo(ctx.timezone)).strftime("%Y-%m")
    month_spent = monthly_totals(ctx.vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(ctx.provider_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)

    report = run_backfill(
        ctx.vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=True,
        local_mutation=local_mutation or run_local_mutation,
    )
    lines = [
        f"处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}、"
        f"生成候选 {report.candidates}"
    ]
    for result in report.results:
        if result.action == "failed":
            lines.append(f"✗ {result.item.date} {result.item.title}：{result.reason}")
    operation_ids = list(report.operation_ids)
    operation_note = f" · operation_id：{operation_ids[-1]}" if operation_ids else ""
    status = (
        "success"
        if report.failed == 0
        else ("partial" if report.processed or report.skipped else "failed")
    )
    message_prefix = {
        "success": "导入完成：",
        "partial": "导入部分完成：",
        "failed": "导入失败：",
    }[status]
    return {
        "ok": report.failed == 0,
        "status": status,
        "message": message_prefix + "；".join(lines) + operation_note,
        "details": lines,
        "operation_ids": operation_ids,
        "estimate": {
            "pending": est.pending,
            "already_done": est.already_done,
            "est_input_tokens": est.est_input_tokens,
            "est_output_tokens": est.est_output_tokens,
            "est_cost": est.est_cost,
            "currency": est.currency,
            "projected_month_cost": est.projected_month_cost,
            "soft_limit": soft_limit,
            "crosses_soft_budget": est.crosses_soft_budget,
        },
    }


__all__ = ["_run_web_import"]
