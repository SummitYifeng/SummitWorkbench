"""七天本机表单草稿存储（不进入工作库）。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from summit_workbench.config.app_support import runtime_dir
from summit_workbench.repositories._atomic import atomic_write_text

_TTL = timedelta(days=7)
_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_FIELDS: dict[str, dict[str, str]] = {
    "quick-note": {"text": "text"},
    "journal-log": {
        "did": "text",
        "remaining": "text",
        "reflection": "text",
        "blockers": "text",
        "projects": "list",
    },
    "journal-thought": {
        "problem": "text",
        "thinking": "text",
        "conclusion": "text",
        "summary": "text",
        "projects": "list",
    },
    "inbox-promote": {
        "id": "id",
        "target": "enum",
        "project": "text",
        "block": "enum",
        "due_date": "text",
        "start_date": "text",
        "problem": "text",
        "thinking": "text",
        "conclusion": "text",
        "summary": "text",
    },
    "review-edit": {
        "description": "text",
        "target_project": "text",
        "route": "enum",
        "due_date": "text",
        "start_at": "text",
        "end_at": "text",
        "sink_target": "text",
    },
    "task-edit": {"summary": "text", "due_date": "text"},
    "meeting-edit": {"summary": "text", "start_at": "text", "end_at": "text"},
    "project-edit": {
        "status": "enum",
        "next_step": "text",
        "blockers": "text",
        "followups": "text",
    },
    "thread-log": {"text": "text", "occurred_at": "text", "status": "enum", "projects": "list"},
    "artifact": {"project": "text", "title": "text", "text": "text", "syncState": "bool"},
}


class DraftValidationError(ValueError):
    """草稿键或字段超出固定 schema。"""


def _validate_identity(draft_type: str, draft_id: str) -> None:
    if draft_type not in _FIELDS or not _TYPE_RE.fullmatch(draft_type):
        raise DraftValidationError("不支持此类草稿")
    if (
        not draft_id
        or len(draft_id) > 180
        or "/" in draft_id
        or "\\" in draft_id
        or any(ord(char) < 32 for char in draft_id)
    ):
        raise DraftValidationError("草稿标识无效")


def validate_draft_value(draft_type: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DraftValidationError("草稿内容格式无效")
    allowed = _FIELDS[draft_type]
    unknown = set(value) - set(allowed)
    if unknown:
        raise DraftValidationError("草稿包含不允许保存的字段")
    clean: dict[str, object] = {}
    for key, item in value.items():
        kind = allowed[key]
        if kind in {"text", "id", "enum"}:
            if not isinstance(item, str) or len(item) > (
                100_000 if key in {"text", "problem", "thinking", "conclusion"} else 4_000
            ):
                raise DraftValidationError("草稿字段格式无效或内容过长")
            clean[key] = item
        elif kind == "list":
            if (
                not isinstance(item, list)
                or len(item) > 40
                or any(not isinstance(part, str) or len(part) > 200 for part in item)
            ):
                raise DraftValidationError("草稿项目列表格式无效")
            clean[key] = item
        elif kind == "bool":
            if not isinstance(item, bool):
                raise DraftValidationError("草稿选项格式无效")
            clean[key] = item
    return clean


class LocalDraftStore:
    def __init__(self, workspace_id: str, *, home: Path | None = None) -> None:
        self.directory = runtime_dir(workspace_id, home) / "drafts"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        lock_path = self.directory / ".drafts.lock"
        with lock_path.open("a+b") as handle:
            lock_path.chmod(0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _path(self, draft_type: str, draft_id: str) -> Path:
        _validate_identity(draft_type, draft_id)
        digest = hashlib.sha256(f"{draft_type}\0{draft_id}".encode()).hexdigest()
        return self.directory / f"{digest}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, object] | None:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(record, dict):
            return None
        return record

    @staticmethod
    def _fresh(record: dict[str, object], now: datetime) -> bool:
        try:
            edited = datetime.fromisoformat(str(record["edited_at"]))
            return now - edited <= _TTL
        except (KeyError, ValueError, TypeError):
            return False

    def list(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        current = now or datetime.now(UTC)
        with self._lock():
            drafts = []
            for path in self.directory.glob("*.json"):
                record = self._read(path)
                if record is not None and self._fresh(record, current):
                    drafts.append(record)
                else:
                    path.unlink(missing_ok=True)
        return sorted(drafts, key=lambda draft: str(draft.get("edited_at", "")), reverse=True)

    def get(
        self, draft_type: str, draft_id: str, *, now: datetime | None = None
    ) -> dict[str, object] | None:
        path = self._path(draft_type, draft_id)
        with self._lock():
            record = self._read(path)
            if record is not None and not self._fresh(record, now or datetime.now(UTC)):
                path.unlink(missing_ok=True)
                record = None
        if record is None:
            return None
        return record

    def save(
        self,
        draft_type: str,
        draft_id: str,
        value: object,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        path = self._path(draft_type, draft_id)
        clean = validate_draft_value(draft_type, value)
        edited_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        record: dict[str, object] = {
            "schema_version": 1,
            "type": draft_type,
            "id": draft_id,
            "edited_at": edited_at,
            "value": clean,
        }
        with self._lock():
            atomic_write_text(
                path,
                json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                ensure_parents=True,
                new_mode=0o600,
            )
        return record

    def delete(self, draft_type: str, draft_id: str) -> bool:
        path = self._path(draft_type, draft_id)
        with self._lock():
            try:
                path.unlink()
            except FileNotFoundError:
                return False
        return True


__all__ = ["DraftValidationError", "LocalDraftStore", "validate_draft_value"]
