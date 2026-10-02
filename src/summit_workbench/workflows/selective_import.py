"""Read-only preview and explicit, hash-bound import for legacy Markdown files."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import yaml

from summit_workbench.domain.approval import RETRIEVAL_TYPES
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter

_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_ORIGINAL_TYPES = frozenset({"source", "meeting-transcript"})


@dataclass(frozen=True)
class ImportCandidate:
    source_path: str
    content_sha256: str
    note_type: str | None
    project: str | None
    dependencies: tuple[str, ...]
    missing_dependencies: tuple[str, ...]
    suggested_path: str
    classification: str
    warning: str | None = None


def preview_markdown_import(source_root: Path) -> tuple[ImportCandidate, ...]:
    """List Markdown/text candidates without changing either tree."""
    root = source_root.resolve(strict=True)
    candidates: list[ImportCandidate] = []
    for path in sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt"}
    ):
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError(f"source path escapes selected folder: {path}") from None
        if any(
            part.startswith(".") or part == "_summit-workbench"
            for part in path.relative_to(root).parts
        ):
            continue
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        metadata, _body, parse_error = parse_frontmatter(text)
        raw_type = metadata.get("type")
        raw_project = metadata.get("project")
        note_type = raw_type if isinstance(raw_type, str) else None
        project = raw_project if isinstance(raw_project, str) else None
        links = tuple(sorted(set(match.strip() for match in _LINK.findall(text))))
        missing_links: list[str] = []
        for link in links:
            found = False
            for target in (root / f"{link}.md", root / link):
                try:
                    target.resolve(strict=True).relative_to(root)
                except (OSError, ValueError):
                    continue
                if target.is_file():
                    found = True
                    break
            if not found:
                missing_links.append(link)
        missing = tuple(missing_links)
        if (
            note_type in _ORIGINAL_TYPES
            or "transcript" in relative.casefold()
            or "sources/" in relative.casefold()
        ):
            classification, suggested = "original", PurePosixPath("sources/imported") / relative
        elif note_type in RETRIEVAL_TYPES:
            classification, suggested = "review", PurePosixPath(relative)
        else:
            classification, suggested = (
                "organize",
                PurePosixPath(".summit-workbench/imports/pending") / relative,
            )
        warning = f"frontmatter: {parse_error}" if parse_error else None
        candidates.append(
            ImportCandidate(
                source_path=relative,
                content_sha256=hashlib.sha256(raw).hexdigest(),
                note_type=note_type,
                project=project,
                dependencies=links,
                missing_dependencies=missing,
                suggested_path=suggested.as_posix(),
                classification=classification,
                warning=warning,
            )
        )
    return tuple(candidates)


def apply_markdown_import(
    source_root: Path,
    workspace_root: Path,
    selected: tuple[ImportCandidate, ...],
) -> tuple[str, ...]:
    """Import only previewed selections; refuse stale sources and conflicting targets.

    Legacy approval proofs are removed. Imports remain unapproved until reviewed in SWB.
    Re-running the same selection is idempotent when the destination bytes still match.
    """
    source = source_root.resolve(strict=True)
    workspace = workspace_root.resolve(strict=True)
    current = {candidate.source_path: candidate for candidate in preview_markdown_import(source)}
    written: list[str] = []
    for candidate in selected:
        live = current.get(candidate.source_path)
        if live is None or live.content_sha256 != candidate.content_sha256:
            raise ValueError(f"source changed since preview: {candidate.source_path}")
        src = (source / candidate.source_path).resolve(strict=True)
        try:
            src.relative_to(source)
        except ValueError:
            raise ValueError("source path escapes selected folder") from None
        relative_target = PurePosixPath(candidate.suggested_path)
        if relative_target.is_absolute() or ".." in relative_target.parts:
            raise ValueError("target path must stay inside workspace")
        dest = (workspace / Path(*relative_target.parts)).resolve()
        try:
            dest.relative_to(workspace)
        except ValueError:
            raise ValueError("target path escapes workspace") from None
        raw = src.read_bytes()
        if src.suffix.lower() == ".md":
            text = raw.decode("utf-8")
            metadata, body, error = parse_frontmatter(text)
            if error is None and "approval" in metadata:
                metadata.pop("approval", None)
                header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
                text = f"---\n{header}\n---\n{body}"
                raw = text.encode("utf-8")
        if dest.exists():
            if dest.is_file() and dest.read_bytes() == raw:
                written.append(relative_target.as_posix())
                continue
            raise FileExistsError(
                f"import target already exists with different content: {relative_target}"
            )
        atomic_write_text(dest, raw.decode("utf-8"), ensure_parents=True)
        written.append(relative_target.as_posix())
    return tuple(written)


def candidate_to_dict(candidate: ImportCandidate) -> dict[str, object]:
    """JSON-friendly representation for CLI preview and selection manifests."""
    result = asdict(candidate)
    result["dependencies"] = list(candidate.dependencies)
    result["missing_dependencies"] = list(candidate.missing_dependencies)
    result["selected"] = False
    return result
