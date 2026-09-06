"""本地结构化日志与轮转（P1-05）。"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from summit_workbench.observability.redaction import redact_fields, redact_text


def short_id(value: str | None) -> str:
    """只在日志中保留 identity 的短码，不写完整 workspace/device id。"""
    if not value:
        return "unknown"
    return value.replace("-", "")[:8]


class StructuredLogger:
    """进程安全的 JSONL logger；默认 5 MiB、保留 3 个轮转文件。"""

    def __init__(
        self, path: Path | None, *, component: str, max_bytes: int = 5 * 1024 * 1024
    ) -> None:
        self.path = path
        self.component = component
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def log(
        self,
        event: str,
        *,
        level: str = "info",
        operation_id: str | None = None,
        workspace_id: str | None = None,
        device_id: str | None = None,
        error_code: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": level,
            "component": self.component,
            "event": redact_text(event),
            "operation_id": short_id(operation_id),
            "workspace_id": short_id(workspace_id),
            "device_id": short_id(device_id),
            "error_code": redact_text(error_code or ""),
        }
        extra = redact_fields(fields or {})
        for reserved in (
            "timestamp",
            "level",
            "component",
            "event",
            "operation_id",
            "workspace_id",
            "device_id",
            "error_code",
        ):
            extra.pop(reserved, None)
        payload.update(extra)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        if self.path is None:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            next_size = (
                self.path.stat().st_size + len(line.encode("utf-8")) if self.path.is_file() else 0
            )
            if next_size > self.max_bytes:
                self._rotate()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if self.path is None or not self.path.is_file():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        except (OSError, UnicodeDecodeError):
            return []
        result: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                result.append(redact_fields(value))
        return result

    def _rotate(self) -> None:
        assert self.path is not None
        for index in range(3, 0, -1):
            old = self.path.with_name(self.path.name + f".{index}")
            newer = (
                self.path if index == 1 else self.path.with_name(self.path.name + f".{index - 1}")
            )
            if old.exists():
                old.unlink()
            if newer.exists():
                newer.replace(old)


__all__ = ["StructuredLogger", "short_id"]
