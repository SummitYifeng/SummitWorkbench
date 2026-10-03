"""Write version-bound approval proofs after explicit user confirmation."""

from __future__ import annotations

from pathlib import Path

import yaml

from summit_workbench.domain.approval import approval_digest, approval_record
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter


def approve_markdown(
    path: Path,
    *,
    operation_id: str,
    approved_at: str | None = None,
    status: str | None = None,
    expected_digest: str | None = None,
) -> None:
    """Stamp the exact current Markdown version as approved, preserving its body.

    ``status`` can move a workflow-only ``pending-review`` status into its
    business status in the same atomic write as the approval proof.
    """
    if not operation_id.strip():
        raise ValueError("operation_id must not be empty")
    text = path.read_text(encoding="utf-8")
    metadata, body, error = parse_frontmatter(text)
    if error is not None:
        raise ValueError(f"cannot approve invalid frontmatter: {error}")
    if expected_digest is not None and approval_digest(metadata, body) != expected_digest:
        raise ValueError("content changed while approval was being applied")
    if status is not None:
        metadata["status"] = status
    metadata["approval"] = approval_record(
        metadata, body, operation_id=operation_id, approved_at=approved_at
    )
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    atomic_write_text(path, f"---\n{frontmatter}\n---\n{body}")


__all__ = ["approve_markdown"]
