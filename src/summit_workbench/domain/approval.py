"""Version-bound approval proof and retrieval qualification contract v1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

APPROVAL_VERSION = 1
APPROVAL_METADATA_FIELDS = frozenset(
    {
        "title",
        "summary",
        "type",
        "project",
        "projects",
        "date",
        "status",
        "decision_status",
        "decision",
        "replaces",
        "superseded_by",
        "source",
        "workstream",
        "area",
        "start_at",
        "end_at",
        "due_date",
        "meeting_date",
    }
)
RETRIEVAL_TYPES = frozenset(
    {
        "project-main",
        "note",
        "decision",
        "meeting-note",
        "long-form-thought",
        "work-log",
        "thread-doc",
        "weekly-review",
    }
)
RETRIEVAL_STATUSES = frozenset(
    {"active", "paused", "archived", "generated", "applied", "superseded"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def normalize_approved_body(body: str) -> str:
    """Normalize line endings and terminal whitespace, then add one LF."""
    if body.startswith("\ufeff"):
        raise ValueError("UTF-8 BOM is not allowed in workspace Markdown")
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip() + "\n"


def approval_payload(metadata: Mapping[str, Any], body: str) -> dict[str, Any]:
    """Return the canonical semantic payload defined by contract v1."""
    selected = {
        key: _json_value(metadata[key]) for key in APPROVAL_METADATA_FIELDS if key in metadata
    }
    # Archiving a project is a workspace lifecycle operation, not a new content
    # version. Keep the approved proof valid across active <-> archived only.
    if selected.get("type") == "project-main" and selected.get("status") == "archived":
        selected["status"] = "active"
    return {"metadata": selected, "body": normalize_approved_body(body)}


def _json_value(value: Any) -> Any:
    """Normalize YAML date values and containers to the JSON contract domain."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported approval metadata value: {type(value).__name__}")


def approval_digest(metadata: Mapping[str, Any], body: str) -> str:
    encoded = json.dumps(
        approval_payload(metadata, body),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def approval_record(
    metadata: Mapping[str, Any],
    body: str,
    *,
    operation_id: str,
    approved_at: str | None = None,
) -> dict[str, object]:
    """Create an approval proof for an explicit user-confirmed write."""
    return {
        "version": APPROVAL_VERSION,
        "content_sha256": approval_digest(metadata, body),
        "approved_at": approved_at or datetime.now(UTC).isoformat(),
        "operation_id": operation_id,
    }


def has_valid_approval(metadata: Mapping[str, Any], body: str) -> bool:
    approval = metadata.get("approval")
    if not isinstance(approval, Mapping):
        return False
    digest = approval.get("content_sha256")
    if (
        approval.get("version") != APPROVAL_VERSION
        or not isinstance(digest, str)
        or not _SHA256.fullmatch(digest)
        or not isinstance(approval.get("approved_at"), str)
        or not approval["approved_at"].strip()
        or not isinstance(approval.get("operation_id"), str)
        or not approval["operation_id"].strip()
    ):
        return False
    try:
        return digest == approval_digest(metadata, body)
    except (TypeError, ValueError):
        return False


def retrieval_eligible(metadata: Mapping[str, Any], body: str) -> bool:
    """Default-deny retrieval predicate shared with future SK implementation."""
    kind = metadata.get("type")
    status = metadata.get("status")
    if kind not in RETRIEVAL_TYPES or status not in RETRIEVAL_STATUSES:
        return False
    if kind in {"source", "meeting-transcript"}:
        return False
    return has_valid_approval(metadata, body)
