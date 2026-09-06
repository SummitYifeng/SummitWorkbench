"""App 内自动化 worker（P1-01）。

该模块只运行一次任务，不启动 Web server；调度器负责何时拉起它。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from summit_workbench.config.git_credentials import profile_identity
from summit_workbench.config.profiles import ActiveWorkspaceContext
from summit_workbench.domain.automation import (
    AutomationJob,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationSettings,
)
from summit_workbench.domain.run_health import RunStatus
from summit_workbench.observability.heartbeat import record_run_safely
from summit_workbench.repositories.automation_primary import load_automation_primary
from summit_workbench.repositories.automation_settings import (
    load_automation_settings,
    save_automation_settings,
)
from summit_workbench.workflows import sync_coordinator
from summit_workbench.workflows.brief.publish import publish_brief
from summit_workbench.workflows.brief.runner import run_brief, today_iso
from summit_workbench.workflows.weekly.weekly import generate_weekly


@dataclass(frozen=True)
class WorkerResult:
    """一次 worker 调用的脱敏结果。"""

    job: AutomationJob
    status: AutomationRunStatus
    detail: str = ""
    published: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "job": self.job.value,
            "status": self.status.value,
            "detail": self.detail or None,
            "published": self.published,
        }


def _record_settings(
    context: ActiveWorkspaceContext,
    settings: AutomationSettings,
    job: AutomationJob,
    result: WorkerResult,
    *,
    now: datetime,
) -> None:
    """只在任务已获准执行后写入最近结果；secondary 不进入此路径。"""
    schedule = settings.for_job(job)
    local_now = now.astimezone(ZoneInfo(context.timezone))
    current = schedule.model_copy(
        update={
            "last_run_at": now.astimezone(UTC),
            "last_status": result.status,
            "last_detail": result.detail or None,
            "next_run_at": _next_scheduled_at(schedule, local_now),
        }
    )
    settings.jobs[job] = current
    save_automation_settings(settings, home=context.home)


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
) -> WorkerResult:
    """按 workspace/profile/主设备门控执行一次自动化任务。"""
    if context.paths is None or context.profile is None or context.workspace_id is None:
        return WorkerResult(job, AutomationRunStatus.SKIPPED, "尚未选择工作区")
    claim = load_automation_primary(context.paths.vault_dir)
    gate = sync_coordinator.automation_gate(
        context.profile,
        claim=claim,
        device_id=context.device_id,
        require_claim=True,
    )
    if gate.value != "primary-ok":
        # 关键安全约束：secondary 不写 vault，也不更新本机任务结果账本。
        return WorkerResult(job, AutomationRunStatus.NOT_PRIMARY, "本机不是该 workspace 的主设备")

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
        result = WorkerResult(job, AutomationRunStatus.FAILED, "workspace 当前不可写")
        _record_settings(context, settings, job, result, now=current)
        return result

    day = local_now.date().isoformat()
    snapshot = sync_coordinator.current_snapshot(
        context.paths.vault_dir,
        home=context.home,
        workspace_id=context.workspace_id,
        backend_kind="dulwich",
        context=context,
    )
    mutation_allowed, mutation_reason = sync_coordinator.mutation_guard(snapshot)
    if not mutation_allowed:
        result = WorkerResult(job, AutomationRunStatus.FAILED, mutation_reason)
        _record_settings(context, settings, job, result, now=current)
        return result
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
            )
            brief_result = run.result
            degraded = bool(run.feishu_unavailable) or brief_result.ranking.degraded
            status = AutomationRunStatus.DEGRADED if degraded else AutomationRunStatus.SUCCESS
            record_run_safely(
                context.paths.vault_dir,
                job="brief",
                status=RunStatus.DEGRADED if degraded else RunStatus.SUCCESS,
                day=day,
                detail=run.feishu_unavailable,
            )
            published = None
            if brief_result.note_path and brief_result.snapshot_path:
                published = publish_brief(
                    context.paths.vault_dir,
                    [brief_result.note_path, brief_result.snapshot_path],
                    message=f"chore(brief): 晨间简报 {day}",
                    push=True,
                    backend_kind="dulwich",
                    workspace_id=context.workspace_id,
                    username=context.profile.git_username,
                    author=profile_identity(context.profile),
                ).status.value
            outcome = WorkerResult(job, status, run.feishu_unavailable or "", published)
        elif job is AutomationJob.WEEKLY:
            weekly_result = generate_weekly(
                context.paths.work_root,
                context.paths.vault_dir,
                today=local_now.date(),
                pending_review_count=0,
                write=True,
            )
            record_run_safely(
                context.paths.vault_dir, job="weekly", status=RunStatus.SUCCESS, day=day
            )
            published = (
                publish_brief(
                    context.paths.vault_dir,
                    [weekly_result.note_path] if weekly_result.note_path else [],
                    message=f"chore(weekly): 周复盘 {weekly_result.review.week}",
                    push=True,
                    backend_kind="dulwich",
                    workspace_id=context.workspace_id,
                    username=context.profile.git_username,
                    author=profile_identity(context.profile),
                ).status.value
                if weekly_result.note_path
                else None
            )
            outcome = WorkerResult(job, AutomationRunStatus.SUCCESS, "", published)
        else:
            outcome = WorkerResult(job, AutomationRunStatus.SKIPPED, "会议同步 worker 尚未配置")
    except Exception as exc:  # worker 必须把失败写入可见状态后退出
        outcome = WorkerResult(job, AutomationRunStatus.FAILED, f"{type(exc).__name__}: {exc}")
        record_run_safely(
            context.paths.vault_dir,
            job=job.value,
            status=RunStatus.FAILED,
            day=day,
            detail=outcome.detail,
        )
    _record_settings(context, settings, job, outcome, now=current)
    return outcome


def worker_json(result: WorkerResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2)
