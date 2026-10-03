"""Read-only discovery of formal Markdown versions awaiting user approval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from summit_workbench.domain.approval import RETRIEVAL_TYPES, approval_digest
from summit_workbench.repositories.vault import iter_markdown_files, load_note, meta_date_iso


@dataclass(frozen=True)
class PendingContent:
    """A stable preview of one unapproved formal page."""

    path: str
    title: str
    content_type: str
    date: str
    summary: str
    body: str
    content_sha256: str


def list_pending_content(vault_dir: Path) -> list[PendingContent]:
    """Find pending formal pages without changing files or calling a model."""
    pending: list[PendingContent] = []
    root = vault_dir.resolve()
    for path in iter_markdown_files(root):
        note = load_note(path)
        if note.parse_error is not None:
            continue
        if note.meta.get("status") != "pending-review":
            continue
        content_type = note.meta.get("type")
        if not isinstance(content_type, str) or content_type not in RETRIEVAL_TYPES:
            continue
        if content_type in {"source", "meeting-transcript"}:
            continue
        relative = path.relative_to(root).as_posix()
        title = note.meta.get("title")
        if not isinstance(title, str) or not title.strip():
            title = next(
                (line[2:].strip() for line in note.body.splitlines() if line.startswith("# ")),
                path.stem,
            )
        summary = note.meta.get("summary")
        try:
            digest = approval_digest(note.meta, note.body)
        except (TypeError, ValueError):
            continue
        pending.append(
            PendingContent(
                path=relative,
                title=title.strip(),
                content_type=content_type,
                date=meta_date_iso(note.meta.get("date")) or "",
                summary=summary.strip() if isinstance(summary, str) else "",
                body=note.body,
                content_sha256=digest,
            )
        )
    return pending


__all__ = ["PendingContent", "list_pending_content"]
