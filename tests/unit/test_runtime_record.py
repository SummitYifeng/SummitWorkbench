"""P0-12 运行时记录：动态端口、实例身份与陈旧清理。"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from summit_workbench.webapp.runtime import (
    RuntimeRecord,
    cleanup_stale_runtime_record,
    load_runtime_record,
    runtime_record_path,
    write_runtime_record,
)


def _record(*, pid: int | None = None, started_at: datetime | None = None) -> RuntimeRecord:
    return RuntimeRecord(
        schema_version=2,
        product_id="com.summitworkbench.panel",
        api_protocol=2,
        frontend_build="web-build",
        server_instance="server-a",
        workspace_id="workspace-a",
        device_id="device-a",
        pid=pid if pid is not None else os.getpid(),
        port=43123,
        started_at=started_at or datetime.now(UTC),
    )


def test_runtime_record_is_atomic_private_and_round_trips(tmp_path: Path) -> None:
    path = runtime_record_path(tmp_path, "workspace-a")
    written = write_runtime_record(_record(), path=path)

    assert written == path
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_runtime_record(path) == _record_from_json(path)
    assert json.loads(path.read_text(encoding="utf-8"))["server_instance"] == "server-a"


def test_stale_record_is_removed_only_when_pid_is_gone(tmp_path: Path) -> None:
    path = runtime_record_path(tmp_path, "workspace-a")
    write_runtime_record(_record(pid=999_999), path=path)
    assert cleanup_stale_runtime_record(path) is True
    assert not path.exists()

    write_runtime_record(_record(pid=os.getpid()), path=path)
    assert cleanup_stale_runtime_record(path) is False
    assert path.exists()


def test_expired_record_with_live_pid_is_not_removed(tmp_path: Path) -> None:
    path = runtime_record_path(tmp_path, "workspace-a")
    old = datetime.now(UTC) - timedelta(days=2)
    write_runtime_record(_record(pid=os.getpid(), started_at=old), path=path)

    assert cleanup_stale_runtime_record(path, max_age=timedelta(seconds=1)) is False
    assert path.exists()


def _record_from_json(path: Path) -> RuntimeRecord:
    return RuntimeRecord.model_validate_json(path.read_text(encoding="utf-8"))
