"""Short-lived local service identity used by the native launcher (P0-12)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from summit_workbench.config.app_support import PROFILE_FILE_MODE, runtime_dir
from summit_workbench.repositories._atomic import atomic_write_text


class RuntimeRecord(BaseModel):
    """The only native-discoverable description of an owned server instance."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=2, ge=2)
    product_id: str
    api_protocol: int
    frontend_build: str
    server_instance: str
    workspace_id: str | None
    device_id: str | None
    pid: int = Field(gt=0)
    port: int = Field(ge=1, le=65535)
    started_at: datetime


def runtime_record_path(home: Path, workspace_id: str) -> Path:
    return runtime_dir(workspace_id, home=home) / "runtime.json"


def write_runtime_record(record: RuntimeRecord, *, path: Path) -> Path:
    atomic_write_text(
        path,
        record.model_dump_json(indent=2) + "\n",
        ensure_parents=True,
        new_mode=PROFILE_FILE_MODE,
    )
    return path


def load_runtime_record(path: Path) -> RuntimeRecord | None:
    try:
        return RuntimeRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None


def cleanup_stale_runtime_record(
    path: Path, *, now: datetime | None = None, max_age: timedelta = timedelta(days=7)
) -> bool:
    """Remove only a record whose process is gone; never kill by port or age alone."""
    record = load_runtime_record(path)
    if record is None:
        if path.exists():
            path.unlink(missing_ok=True)
            return True
        return False
    # A live process wins over age: a long-running service must not disappear
    # merely because the app has been open for a long time.
    if _pid_alive(record.pid):
        return False
    path.unlink(missing_ok=True)
    return True


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
