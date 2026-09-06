"""P1-01 worker 的 workspace / 主设备 / 启停门控。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.automation import AutomationJob, AutomationSchedule
from summit_workbench.domain.sync import SyncSnapshot, SyncState
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.automation_primary import claim_automation_primary
from summit_workbench.repositories.automation_settings import (
    load_automation_settings,
    save_automation_settings,
)
from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.workflows.automation_worker import run_automation_job


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
