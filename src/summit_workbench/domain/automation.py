"""App 内自动化任务的纯领域模型（P1-01）。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AutomationJob(StrEnum):
    """由 App 管理的自动化任务。"""

    BRIEF = "brief"
    WEEKLY = "weekly"
    MEETING_SYNC = "meeting-sync"


class AutomationRunStatus(StrEnum):
    """最近一次任务运行结果。"""

    NEVER = "never"
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    NOT_PRIMARY = "not-primary"
    SKIPPED = "skipped"


class AutomationSchedule(BaseModel):
    """单个任务的本机调度设置与最近结果。"""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    hour: Annotated[int, Field(ge=0, le=23)] = 8
    minute: Annotated[int, Field(ge=0, le=59)] = 0
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=lambda: list(range(7))
    )
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    retry_count: int = Field(default=0, ge=0)
    retry_at: datetime | None = None
    last_error_code: str | None = None
    last_status: AutomationRunStatus = AutomationRunStatus.NEVER
    last_detail: str | None = None
    next_run_at: datetime | None = None


class AutomationSettings(BaseModel):
    """workspace 作用域的自动化设置（只保存本机，不进入 vault）。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    workspace_id: str = Field(min_length=8, max_length=64)
    jobs: dict[AutomationJob, AutomationSchedule] = Field(default_factory=dict)

    @classmethod
    def defaults(cls, workspace_id: str) -> AutomationSettings:
        return cls(
            workspace_id=workspace_id,
            jobs={
                AutomationJob.BRIEF: AutomationSchedule(hour=8, minute=0),
                AutomationJob.WEEKLY: AutomationSchedule(hour=7, minute=30, weekdays=[0]),
                AutomationJob.MEETING_SYNC: AutomationSchedule(hour=8, minute=30),
            },
        )

    def for_job(self, job: AutomationJob) -> AutomationSchedule:
        """读取任务设置；旧配置缺失新任务时安全返回默认禁用设置。"""
        return self.jobs.get(job, AutomationSchedule())
