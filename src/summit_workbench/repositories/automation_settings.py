"""P1-01 本机自动化设置持久化。"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from pathlib import Path

from pydantic import ValidationError

from summit_workbench.config.app_support import PROFILE_FILE_MODE, profile_dir
from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.automation import (
    AutomationJob,
    AutomationRunStatus,
    AutomationSettings,
)
from summit_workbench.repositories._atomic import atomic_write_text

_FILE_NAME = "automation.json"


def automation_job_lock_root(
    workspace_id: str, job: AutomationJob, *, home: Path | None = None
) -> Path:
    """返回只用于本机 job 领取/结果写回的锁根。"""
    return profile_dir(workspace_id, home=home) / "runtime" / "automation" / job.value


def automation_job_lock(
    workspace_id: str,
    job: AutomationJob,
    *,
    home: Path | None = None,
    timeout: float | None = 60.0,
) -> AbstractContextManager[None]:
    """同一 workspace/job 的本机进程锁，不进入 vault。"""
    return workspace_lock(automation_job_lock_root(workspace_id, job, home=home), timeout=timeout)


def automation_settings_file(workspace_id: str, *, home: Path | None = None) -> Path:
    return profile_dir(workspace_id, home=home) / _FILE_NAME


def load_automation_settings(workspace_id: str, *, home: Path | None = None) -> AutomationSettings:
    """读取 workspace 自动化设置；缺失时返回内存默认值，不创建文件。"""
    path = automation_settings_file(workspace_id, home=home)
    if not path.is_file():
        return AutomationSettings.defaults(workspace_id)
    try:
        settings = AutomationSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"自动化设置损坏，请检查 {path}") from exc
    if settings.workspace_id != workspace_id:
        raise ValueError("自动化设置 workspace_id 不匹配")
    # 旧版本只有最近尝试时间；只有明确 success 才能安全迁为最近成功时间。
    for schedule in settings.jobs.values():
        if (
            schedule.last_success_at is None
            and schedule.last_status is AutomationRunStatus.SUCCESS
            and schedule.last_run_at is not None
        ):
            schedule.last_success_at = schedule.last_run_at
    # 仅在内存中补充可证明的成功证据；不为 degraded/failed 猜测状态，也不让 GET
    # 请求产生副作用。下一次正常结果写回时会保存兼容后的字段。
    return settings


def save_automation_settings(settings: AutomationSettings, *, home: Path | None = None) -> Path:
    path = automation_settings_file(settings.workspace_id, home=home)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, new_mode=PROFILE_FILE_MODE)
    return path
