"""Portable receipts for multi-file local mutations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from summit_workbench.repositories._atomic import atomic_write_text


def _directory(root: Path) -> Path:
    return root / ".summit-workbench" / "operations"


def write_mutation_record(root: Path, operation_id: str, record: dict[str, Any]) -> Path:
    if not operation_id or not all(char.isalnum() or char in "-_" for char in operation_id):
        raise ValueError("invalid operation ID")
    path = _directory(root) / f"{operation_id}.json"
    atomic_write_text(
        path,
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        ensure_parents=True,
    )
    return path


def start_mutation_record(
    root: Path, operation_id: str, action: str, before: dict[str, str]
) -> Path:
    return write_mutation_record(
        root,
        operation_id,
        {
            "version": 1,
            "operation_id": operation_id,
            "action": action,
            "state": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "before_sha256": before,
        },
    )


def finish_mutation_record(
    root: Path,
    operation_id: str,
    record_path: Path,
    *,
    state: str,
    changed_paths: list[str],
    after: dict[str, str],
) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record.update(
        state=state,
        finished_at=datetime.now(UTC).isoformat(),
        changed_paths=changed_paths,
        after_sha256={path: after.get(path) for path in changed_paths},
    )
    write_mutation_record(root, operation_id, record)


def interrupted_mutations(root: Path, snapshot: dict[str, str]) -> list[dict[str, object]]:
    """Mark interrupted operations without restoring or overwriting workspace files."""
    directory = _directory(root)
    if not directory.is_dir():
        return []
    pending: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pending.append({"operation_id": path.stem, "state": "corrupt"})
            continue
        if not isinstance(record, dict) or record.get("state") != "running":
            continue
        before = record.get("before_sha256")
        if not isinstance(before, dict):
            before = {}
        changed = sorted(
            key for key in set(before) | set(snapshot) if before.get(key) != snapshot.get(key)
        )
        record.update(
            state="interrupted",
            changed_paths=changed,
            after_sha256={key: snapshot.get(key) for key in changed},
            recovery_note="文件变化已定位；请人工检查，系统不会自动覆盖当前文件。",
        )
        atomic_write_text(
            path,
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        pending.append(
            {
                "operation_id": record.get("operation_id", path.stem),
                "action": record.get("action"),
                "state": "interrupted",
                "changed_paths": changed,
                "started_at": record.get("started_at"),
            }
        )
    return pending


def list_mutation_records(root: Path) -> list[dict[str, object]]:
    directory = _directory(root)
    if not directory.is_dir():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {"operation_id": path.stem, "state": "corrupt"}
        if isinstance(value, dict):
            value.pop("before_sha256", None)
            records.append(value)
    return records
