"""App 内自动化 worker（P1-01）。

该模块只运行一次任务，不启动 Web server；调度器负责何时拉起它。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from summit_workbench.config.locking import LockBusy
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.domain.automation import (
    AUTOMATION_UNAVAILABLE_REASON,
    AutomationJob,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationSettings,
    automation_is_supported,
)
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.heartbeat import record_run_safely
from summit_workbench.providers.llm import LLMError
from summit_workbench.repositories.automation_settings import (
    automation_job_lock,
    load_automation_settings,
    save_automation_settings,
)
from summit_workbench.workflows.brief.runner import run_brief, today_iso
from summit_workbench.workflows.weekly.weekly import generate_weekly


@dataclass(frozen=True)
class WorkerResult:
    """一次 worker 调用的脱敏结果。"""

    job: AutomationJob
    status: AutomationRunStatus
    detail: str = ""
    published: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "job": self.job.value,
            "status": self.status.value,
            "detail": self.detail or None,
            "published": self.published,
            "error_code": self.error_code,
        }


_RETRY_INTERVALS_MINUTES = (5, 15, 30)
_MAX_RETRIES = len(_RETRY_INTERVALS_MINUTES)
_RETRYABLE_ERROR_CODES = frozenset({"network_error", "request_timeout"})


def _classify_error(error: BaseException) -> str:
    """把 worker 异常压成不含内部细节的稳定分类。"""
    name = type(error).__name__.casefold()
    detail = str(error).casefold()
    if isinstance(error, LLMError):
        # 模型请求可能已被服务端接受；只能人工确认，不能自动重复计费。
        return "generation_outcome_unknown"
    if isinstance(error, TimeoutError) or "timeout" in name or "timed out" in detail:
        return "request_timeout"
    if isinstance(error, ConnectionError) or any(
        marker in name or marker in detail
        for marker in ("network", "connection", "unreachable", "temporarily")
    ):
        return "network_error"
    if "credential" in name or "auth" in name or "permission" in detail:
        return "credential_error"
    return "worker_error"


def _publish_generated(
    context: ActiveWorkspaceContext,
    paths: list[Path],
    *,
    message: str,
) -> tuple[str | None, str]:
    """Deprecated publication hook. Generated display files are local-only."""
    del context, paths, message
    return "local-only", ""


def _record_settings(
    context: ActiveWorkspaceContext,
    settings: AutomationSettings,
    job: AutomationJob,
    result: WorkerResult,
    *,
    now: datetime,
) -> None:
    """只在任务已获准执行后写入最近结果；secondary 不进入此路径。"""
    # 结果写回前重新读取，保留用户在 worker 外修改的开关、时间和星期。
    latest = load_automation_settings(
        context.workspace_id or settings.workspace_id, home=context.home
    )
    schedule = latest.for_job(job)
    local_now = now.astimezone(ZoneInfo(context.timezone))
    last_local_date = (
        schedule.last_run_at.astimezone(local_now.tzinfo).date()
        if schedule.last_run_at is not None
        else None
    )
    retry_count = schedule.retry_count if last_local_date == local_now.date() else 0
    retry_at = None
    last_success_at = schedule.last_success_at
    error_code = result.error_code
    if result.status in {AutomationRunStatus.SUCCESS, AutomationRunStatus.DEGRADED}:
        if result.status is AutomationRunStatus.SUCCESS:
            last_success_at = now.astimezone(UTC)
        retry_count = 0
    elif result.status is AutomationRunStatus.FAILED:
        if error_code in _RETRYABLE_ERROR_CODES and retry_count < _MAX_RETRIES:
            retry_count += 1
            retry_at = local_now + timedelta(minutes=_RETRY_INTERVALS_MINUTES[retry_count - 1])
        else:
            retry_count = 0
    current = schedule.model_copy(
        update={
            "last_run_at": now.astimezone(UTC),
            "last_success_at": last_success_at,
            "retry_count": retry_count,
            "retry_at": retry_at,
            "last_error_code": error_code,
            "last_status": result.status,
            "last_detail": result.detail or None,
            "next_run_at": retry_at or _next_scheduled_at(schedule, local_now),
        }
    )
    latest.jobs[job] = current
    save_automation_settings(latest, home=context.home)


def _next_scheduled_at(schedule: AutomationSchedule, current: datetime) -> datetime | None:
    """返回严格晚于 current 的下一次本机调度时间。"""
    if not schedule.weekdays:
        return None
    scheduled = time(hour=schedule.hour, minute=schedule.minute)
    for offset in range(0, 8):
        candidate_date = current.date()
        if offset:
            candidate_date = date.fromordinal(candidate_date.toordinal() + offset)
        if candidate_date.weekday() not in schedule.weekdays:
            continue
        candidate = datetime.combine(candidate_date, scheduled, tzinfo=current.tzinfo)
        if candidate > current:
            return candidate
    return None


def _schedule_is_due(schedule: AutomationSchedule, current: datetime) -> bool:
    """判断一次轮询是否应执行；last_run_at 防止唤醒/轮询重复写入。"""
    if current.weekday() not in schedule.weekdays:
        return False
    if schedule.last_success_at is not None:
        success_local = schedule.last_success_at.astimezone(current.tzinfo)
        if success_local.date() == current.date():
            return False
    if schedule.retry_at is not None:
        retry_local = schedule.retry_at.astimezone(current.tzinfo)
        if retry_local.date() == current.date():
            return current >= retry_local and schedule.retry_count <= _MAX_RETRIES
    if (current.hour, current.minute) < (schedule.hour, schedule.minute):
        return False
    if schedule.last_run_at is not None:
        last_local = schedule.last_run_at.astimezone(current.tzinfo)
        if last_local.date() == current.date():
            return False
    return True


def run_automation_job(
    context: ActiveWorkspaceContext,
    job: AutomationJob,
    *,
    now: datetime | None = None,
    force: bool = False,
    lock_timeout: float | None = None,
) -> WorkerResult:
    """按 workspace/job 锁领取并执行，避免两个轮询同时生成。"""
    if context.workspace_id is None:
        return _run_automation_job_unlocked(context, job, now=now, force=force)
    timeout = lock_timeout if lock_timeout is not None else (2.0 if force else 60.0)
    try:
        with automation_job_lock(context.workspace_id, job, home=context.home, timeout=timeout):
            return _run_automation_job_unlocked(context, job, now=now, force=force)
    except LockBusy:
        return WorkerResult(
            job,
            AutomationRunStatus.FAILED,
            "另一个相同自动化任务正在运行，请稍后再试",
            error_code="workspace_busy",
        )


def _run_automation_job_unlocked(
    context: ActiveWorkspaceContext,
    job: AutomationJob,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> WorkerResult:
    """Run a one-shot report job for the selected local workspace."""
    if context.paths is None or context.profile is None or context.workspace_id is None:
        return WorkerResult(job, AutomationRunStatus.SKIPPED, "尚未选择工作区")
    if not automation_is_supported(job):
        return WorkerResult(
            job,
            AutomationRunStatus.FAILED,
            AUTOMATION_UNAVAILABLE_REASON,
            error_code="automation_not_supported",
        )
    settings = load_automation_settings(context.workspace_id, home=context.home)
    schedule = settings.for_job(job)
    if not schedule.enabled:
        return WorkerResult(job, AutomationRunStatus.SKIPPED, "任务未启用")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    local_now = current.astimezone(ZoneInfo(context.timezone))
    if not force and not _schedule_is_due(schedule, local_now):
        return WorkerResult(job, AutomationRunStatus.SKIPPED, "当前不在任务执行时间")
    if context.compatibility is None or not context.can_write:
        result = WorkerResult(
            job,
            AutomationRunStatus.FAILED,
            "workspace 当前不可写",
            error_code="configuration_error",
        )
        _record_settings(context, settings, job, result, now=current)
        return result

    day = local_now.date().isoformat()
    try:
        if job is AutomationJob.BRIEF:
            run = run_brief(
                work_root=context.paths.work_root,
                vault_dir=context.paths.vault_dir,
                timezone=context.timezone,
                day=day or today_iso(context.timezone),
                write=True,
                notify=True,
                config_file=context.config_file,
                workspace_id=context.workspace_id,
                home=context.home,
            )
            brief_result = run.result
            degraded = bool(run.feishu_unavailable) or brief_result.ranking.degraded
            status = AutomationRunStatus.DEGRADED if degraded else AutomationRunStatus.SUCCESS
            heartbeat_path = record_run_safely(
                context.paths.vault_dir,
                job="brief",
                status=RunStatus.DEGRADED if degraded else RunStatus.SUCCESS,
                day=day,
                detail=run.feishu_unavailable,
            )
            # Brief text and heartbeat are local workspace/app state; no Git publication occurs.
            written_paths = list(run.persisted_paths)
            if heartbeat_path is not None:
                written_paths.append(heartbeat_path)
            published, publish_detail = _publish_generated(
                context,
                written_paths,
                message=f"chore(brief): 晨间简报 {day}",
            )
            outcome = WorkerResult(
                job,
                status,
                publish_detail or run.feishu_unavailable or "",
                published,
            )
        elif job is AutomationJob.WEEKLY:
            weekly_result = generate_weekly(
                context.paths.work_root,
                context.paths.vault_dir,
                today=local_now.date(),
                pending_review_count=0,
                write=True,
                workspace_id=context.workspace_id,
                home=context.home,
            )
            heartbeat_path = record_run_safely(
                context.paths.vault_dir, job="weekly", status=RunStatus.SUCCESS, day=day
            )
            # 周复盘正文已不在 vault 内：只有心跳（_signals/，已 gitignore）走发布。
            weekly_paths = [heartbeat_path] if heartbeat_path else []
            published, publish_detail = _publish_generated(
                context,
                weekly_paths,
                message=f"chore(weekly): 周复盘 {weekly_result.review.week}",
            )
            outcome = WorkerResult(job, AutomationRunStatus.SUCCESS, publish_detail, published)
        else:
            outcome = WorkerResult(job, AutomationRunStatus.SKIPPED, "会议同步 worker 尚未配置")
    except Exception as exc:  # worker 必须把失败写入可见状态后退出
        outcome = WorkerResult(
            job,
            AutomationRunStatus.FAILED,
            f"{type(exc).__name__}: {exc}",
            error_code=_classify_error(exc),
        )
        record_run_safely(
            context.paths.vault_dir,
            job=job.value,
            status=RunStatus.FAILED,
            day=day,
            detail=outcome.detail,
        )
    _record_settings(context, settings, job, outcome, now=current)
    return outcome
