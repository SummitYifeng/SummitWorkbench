"""Short-lived local service identity used by the native launcher (P0-12)."""

from __future__ import annotations

import os
import subprocess
import sys
from ctypes import CDLL, c_int, c_uint32, c_void_p, create_string_buffer
from datetime import datetime
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


def cleanup_stale_runtime_record(path: Path) -> bool:
    """Remove only a record whose recorded process is gone or is not this server.

    PID values are reusable on macOS.  A record left by a force-closed App can
    therefore point at an unrelated, newly-created process and otherwise block
    every subsequent launch forever.  We only remove the record after checking
    the exact executable identity; we never kill the process on this path.
    """
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
        return _same_server_executable(pid)
    return _same_server_executable(pid)


def _same_server_executable(pid: int) -> bool:
    """Return whether a live PID is still the current Python/server executable."""
    actual = _macos_process_path(pid)
    if actual:
        try:
            return Path(actual).resolve() == Path(sys.executable).resolve()
        except OSError:
            return actual == sys.executable
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            check=False,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        # If identity cannot be established, preserve the record for safety.
        return True
    actual = result.stdout.strip()
    if result.returncode != 0 or not actual:
        return False
    try:
        return Path(actual).resolve() == Path(sys.executable).resolve()
    except OSError:
        return actual == sys.executable


def _macos_process_path(pid: int) -> str | None:
    """Read a live process path without invoking a shell utility on macOS."""
    if sys.platform != "darwin":
        return None
    try:
        libproc = CDLL("/usr/lib/libproc.dylib")
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [c_int, c_void_p, c_uint32]
        proc_pidpath.restype = c_int
        buffer = create_string_buffer(4096)
        length = proc_pidpath(pid, buffer, c_uint32(len(buffer)))
        return buffer.value.decode("utf-8") if length > 0 else None
    except (OSError, AttributeError, TypeError, UnicodeDecodeError):
        return None
