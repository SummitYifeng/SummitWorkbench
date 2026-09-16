"""P1-01 worker 的 workspace / 主设备 / 启停门控。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.automation import (
    AutomationJob,
    AutomationRunStatus,
    AutomationSchedule,
)
from summit_workbench.domain.sync import SyncSnapshot, SyncState
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.automation_primary import claim_automation_primary
from summit_workbench.repositories.automation_settings import (
    load_automation_settings,
    save_automation_settings,
)
from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.workflows.automation_worker import (
    WorkerResult,
    _classify_error,
    _record_settings,
    _schedule_is_due,
    run_automation_job,
)


def _context(tmp_path: Path, role: DeviceRole):
    home = tmp_path / "home"
    work = home / "work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    workspace_id = str(uuid.uuid4())
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            workspace_id=workspace_id,
            display_name="test",
            created_at=datetime.now(UTC),
            min_reader_version="0.4.1",
            min_writer_version="0.4.1",
        ),
    )
    profile = LocalProfile(
        workspace_id=workspace_id,
        display_name="test",
        work_root=work,
        vault_dir=vault,
        device_role=role,
        created_at=datetime.now(UTC),
    )
    save_profile(profile, home=home)
    set_active_profile(workspace_id, home=home)
    context = resolve_active_workspace(home=home)
    # active context 读取 device identity；测试替换为声明所用的稳定 id。
    return context, workspace_id, vault, home


def test_secondary_never_writes_automation_state(tmp_path: Path) -> None:
    context, workspace_id, vault, home = _context(tmp_path, DeviceRole.SECONDARY)
    settings = load_automation_settings(workspace_id, home=home)
    settings.jobs[AutomationJob.BRIEF] = AutomationSchedule(enabled=True)
    settings_path = save_automation_settings(settings, home=home)
    before = settings_path.read_text(encoding="utf-8")
    result = run_automation_job(context, AutomationJob.BRIEF)
    assert result.status.value == "not-primary"
    assert settings_path.read_text(encoding="utf-8") == before
    assert not (vault / "_signals").exists()


def test_disabled_primary_skips_without_vault_write(tmp_path: Path) -> None:
    context, workspace_id, vault, _home = _context(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    claim_automation_primary(vault, workspace_id, context.device_id or "device")
    result = run_automation_job(context, AutomationJob.BRIEF)
    assert result.status.value == "skipped"
    assert not (vault / "_signals").exists()


def test_scheduled_worker_is_idempotent_after_wakeup(tmp_path: Path) -> None:
    context, workspace_id, vault, home = _context(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    claim_automation_primary(vault, workspace_id, context.device_id or "device")
    settings = load_automation_settings(workspace_id, home=home)
    settings.jobs[AutomationJob.MEETING_SYNC] = AutomationSchedule(
        enabled=True, hour=8, minute=0, weekdays=[0, 1, 2, 3, 4, 5, 6]
    )
    settings_path = save_automation_settings(settings, home=home)
    now = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    first = run_automation_job(context, AutomationJob.MEETING_SYNC, now=now)
    first_saved = load_automation_settings(workspace_id, home=home).for_job(
        AutomationJob.MEETING_SYNC
    )
    second = run_automation_job(context, AutomationJob.MEETING_SYNC, now=now)
    second_saved = load_automation_settings(workspace_id, home=home).for_job(
        AutomationJob.MEETING_SYNC
    )
    assert first.status.value == "skipped"
    assert second.status.value == "skipped"
    assert first_saved.last_run_at is not None
    assert second_saved.last_run_at == first_saved.last_run_at
    assert settings_path.is_file()


def test_dirty_protected_worker_does_not_write_vault(tmp_path: Path, monkeypatch) -> None:
    context, workspace_id, vault, home = _context(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    claim_automation_primary(vault, workspace_id, context.device_id or "device")
    settings = load_automation_settings(workspace_id, home=home)
    settings.jobs[AutomationJob.MEETING_SYNC] = AutomationSchedule(
        enabled=True, hour=8, minute=0, weekdays=list(range(7))
    )
    save_automation_settings(settings, home=home)
    monkeypatch.setattr(
        "summit_workbench.workflows.automation_worker.sync_coordinator.current_snapshot",
        lambda *args, **kwargs: SyncSnapshot(
            workspace_id=workspace_id,
            state=SyncState.DIRTY_PROTECTED,
            pending_commits=0,
            next_step="先提交或确认本机改动",
        ),
    )

    result = run_automation_job(
        context, AutomationJob.MEETING_SYNC, now=datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    )

    assert result.status.value == "failed"
    assert "dirty-protected" in result.detail
    assert not (vault / "_signals").exists()


def test_failed_brief_retries_after_five_minutes_then_success_deduplicates(
    tmp_path: Path, monkeypatch
) -> None:
    context, workspace_id, _vault, home = _context(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    claim_automation_primary(context.paths.vault_dir, workspace_id, context.device_id or "device")
    settings = load_automation_settings(workspace_id, home=home)
    settings.jobs[AutomationJob.BRIEF] = AutomationSchedule(
        enabled=True, hour=8, minute=0, weekdays=list(range(7))
    )
    save_automation_settings(settings, home=home)
    attempts: list[int] = []

    def fake_run(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("temporary network timeout")
        return SimpleNamespace(
            result=SimpleNamespace(ranking=SimpleNamespace(degraded=False)),
            feishu_unavailable=None,
            persisted_paths=[],
        )

    monkeypatch.setattr("summit_workbench.workflows.automation_worker.run_brief", fake_run)
    monkeypatch.setattr(
        "summit_workbench.workflows.automation_worker.record_run_safely",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "summit_workbench.workflows.automation_worker.publish_brief",
        lambda *_args, **_kwargs: SimpleNamespace(status=SimpleNamespace(value="committed+pushed")),
    )
    monkeypatch.setattr(
        "summit_workbench.workflows.automation_worker.sync_coordinator.current_snapshot",
        lambda *_args, **_kwargs: SyncSnapshot(workspace_id=workspace_id, state=SyncState.READY),
    )

    first = run_automation_job(
        context, AutomationJob.BRIEF, now=datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
    )
    saved = load_automation_settings(workspace_id, home=home).for_job(AutomationJob.BRIEF)
    assert first.status.value == "failed"
    assert saved.retry_at is not None
    assert saved.retry_count == 1
    assert saved.last_success_at is None
    assert not _schedule_is_due(
        saved, datetime(2026, 9, 16, 8, 4, tzinfo=context_timezone(context))
    )

    second = run_automation_job(
        context,
        AutomationJob.BRIEF,
        now=datetime(2026, 9, 16, 0, 5, tzinfo=UTC),
    )
    saved_after_success = load_automation_settings(workspace_id, home=home).for_job(
        AutomationJob.BRIEF
    )
    third = run_automation_job(
        context,
        AutomationJob.BRIEF,
        now=datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
    )

    assert second.status.value == "success"
    assert third.status.value == "skipped"
    assert attempts == [1, 1]
    assert saved_after_success.last_success_at is not None
    assert saved_after_success.retry_count == 0
    assert saved_after_success.retry_at is None


def test_schedule_retries_use_five_fifteen_thirty_minutes_and_reset_next_day() -> None:
    from zoneinfo import ZoneInfo

    local = ZoneInfo("Asia/Shanghai")
    assert not _schedule_is_due(
        AutomationSchedule(
            enabled=True,
            hour=8,
            weekdays=list(range(7)),
            last_run_at=datetime(2026, 9, 16, 0, 0, tzinfo=UTC),
            retry_count=1,
            retry_at=datetime(2026, 9, 16, 8, 5, tzinfo=local),
        ),
        datetime(2026, 9, 16, 8, 4, tzinfo=local),
    )
    assert _schedule_is_due(
        AutomationSchedule(
            enabled=True,
            hour=8,
            weekdays=list(range(7)),
            last_run_at=datetime(2026, 9, 16, 0, 0, tzinfo=UTC),
            retry_count=1,
            retry_at=datetime(2026, 9, 16, 8, 5, tzinfo=local),
        ),
        datetime(2026, 9, 16, 8, 5, tzinfo=local),
    )
    assert _schedule_is_due(
        AutomationSchedule(
            enabled=True,
            hour=8,
            weekdays=list(range(7)),
            last_run_at=datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
            retry_count=3,
            retry_at=datetime(2026, 9, 16, 8, 50, tzinfo=local),
        ),
        datetime(2026, 9, 17, 8, 0, tzinfo=local),
    )


def context_timezone(context) -> object:
    from zoneinfo import ZoneInfo

    return ZoneInfo(context.timezone)


def test_permission_failure_is_visible_without_fast_retry(tmp_path: Path) -> None:
    context, workspace_id, _vault, home = _context(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    settings = load_automation_settings(workspace_id, home=home)
    settings.jobs[AutomationJob.BRIEF] = AutomationSchedule(
        enabled=True, hour=8, weekdays=list(range(7))
    )
    save_automation_settings(settings, home=home)

    _record_settings(
        context,
        settings,
        AutomationJob.BRIEF,
        WorkerResult(
            AutomationJob.BRIEF,
            status=AutomationRunStatus.FAILED,
            detail="凭据不可用",
            error_code="credential_error",
        ),
        now=datetime(2026, 9, 16, 0, 0, tzinfo=UTC),
    )

    saved = load_automation_settings(workspace_id, home=home).for_job(AutomationJob.BRIEF)
    assert saved.last_error_code == "credential_error"
    assert saved.retry_at is None
    assert saved.retry_count == 0


def test_model_error_is_result_unknown_and_not_automatically_retried() -> None:
    from summit_workbench.providers.llm import LLMTimeoutError

    assert _classify_error(LLMTimeoutError("model request timed out")) == (
        "generation_outcome_unknown"
    )
