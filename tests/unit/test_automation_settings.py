"""P1-01 自动化设置模型与本机持久化契约。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from summit_workbench.domain.automation import (
    AutomationJob,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationSettings,
)
from summit_workbench.repositories.automation_settings import (
    automation_settings_file,
    load_automation_settings,
    save_automation_settings,
)


def test_defaults_are_workspace_scoped_and_safe() -> None:
    settings = AutomationSettings.defaults("workspace-123")
    assert settings.workspace_id == "workspace-123"
    assert settings.for_job(AutomationJob.BRIEF).hour == 8
    assert settings.for_job(AutomationJob.WEEKLY).weekdays == [0]
    assert settings.for_job(AutomationJob.BRIEF).enabled is False
    assert settings.for_job(AutomationJob.BRIEF).last_status is AutomationRunStatus.NEVER


def test_settings_round_trip_is_atomic_and_private(tmp_path: Path) -> None:
    settings = AutomationSettings.defaults("workspace-123")
    settings.jobs[AutomationJob.BRIEF] = AutomationSchedule(
        enabled=True, hour=9, minute=15, last_status=AutomationRunStatus.SUCCESS
    )
    path = save_automation_settings(settings, home=tmp_path)
    assert path == automation_settings_file("workspace-123", home=tmp_path)
    assert path.stat().st_mode & 0o777 == 0o600
    loaded = load_automation_settings("workspace-123", home=tmp_path)
    assert loaded == settings
    assert json.loads(path.read_text(encoding="utf-8"))["workspace_id"] == "workspace-123"


def test_missing_new_job_gets_disabled_default(tmp_path: Path) -> None:
    settings = AutomationSettings.defaults("workspace-123")
    settings.jobs.pop(AutomationJob.MEETING_SYNC)
    save_automation_settings(settings, home=tmp_path)
    loaded = load_automation_settings("workspace-123", home=tmp_path)
    assert loaded.for_job(AutomationJob.MEETING_SYNC).enabled is False


def test_mismatched_workspace_is_rejected(tmp_path: Path) -> None:
    path = automation_settings_file("workspace-123", home=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(AutomationSettings.defaults("workspace-456").model_dump(mode="json"))
    )
    with pytest.raises(ValueError, match="workspace_id 不匹配"):
        load_automation_settings("workspace-123", home=tmp_path)
