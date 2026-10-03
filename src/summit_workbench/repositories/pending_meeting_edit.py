"""Narrow edits for meeting notes that are still awaiting content approval."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from summit_workbench.domain.approval import approval_digest
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter

_FRONTMATTER = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---\r?\n)(.*)\Z", re.DOTALL)
_DATE_LINE = re.compile(r"(?m)^date:[^\r\n]*$")
_BODY_DATE_LINE = re.compile(r"(?m)^- 日期：[^\r\n]*$")


def update_pending_meeting_date(path: Path, *, meeting_date: str, expected_digest: str) -> None:
    """Update frontmatter and the visible meeting date as one atomic replacement.

    The digest and pending/type checks are repeated immediately before writing so
    a stale approval page cannot overwrite a newer edit or an approved note.
    """
    try:
        parsed_date = date.fromisoformat(meeting_date)
    except ValueError as exc:
        raise ValueError("日期必须是有效的 YYYY-MM-DD") from exc
    if parsed_date.isoformat() != meeting_date:
        raise ValueError("日期必须是有效的 YYYY-MM-DD")

    original = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.fullmatch(original)
    if match is None:
        raise ValueError("会议纪要 frontmatter 无效")
    metadata, body, error = parse_frontmatter(original)
    if error is not None:
        raise ValueError("会议纪要 frontmatter 无效")
    if metadata.get("type") != "meeting-note":
        raise ValueError("只允许修改会议纪要")
    if metadata.get("status") != "pending-review":
        raise ValueError("纪要已不在待审状态，请刷新审批页")
    if approval_digest(metadata, body) != expected_digest:
        raise ValueError("纪要内容已变化，请刷新审批页后重试")

    frontmatter = match.group(2)
    date_match = _DATE_LINE.search(frontmatter)
    body_date_match = _BODY_DATE_LINE.search(match.group(4))
    if date_match is None or len(_DATE_LINE.findall(frontmatter)) != 1:
        raise ValueError("纪要 frontmatter 必须有且仅有一个 date 字段")
    if body_date_match is None or len(_BODY_DATE_LINE.findall(match.group(4))) != 1:
        raise ValueError("纪要正文必须有且仅有一个「日期」行")

    updated_frontmatter = _DATE_LINE.sub(f"date: '{meeting_date}'", frontmatter, count=1)
    updated_body = _BODY_DATE_LINE.sub(f"- 日期：{meeting_date}", match.group(4), count=1)
    updated = match.group(1) + updated_frontmatter + match.group(3) + updated_body
    new_metadata, new_body, new_error = parse_frontmatter(updated)
    if new_error is not None or new_metadata.get("status") != "pending-review":
        raise ValueError("更新后的纪要未通过格式校验")
    if approval_digest(new_metadata, new_body) == expected_digest:
        raise ValueError("更新未产生内容变化")
    atomic_write_text(path, updated)


__all__ = ["update_pending_meeting_date"]
