"""集中会议审批页的稳定 Markdown 语法、解析和幂等刷新。"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter

REVIEW_PATH = ("review", "meetings.md")
_ITEM_RE = re.compile(r"^- \[([ xX])\] (.+)$")
_PAYLOAD_RE = re.compile(r"^`id: ([^`]+)` \[([^]]+)] (.+)$")
_ORIGINAL_PREFIX = "  <!-- wb-original: "


@dataclass(frozen=True)
class ParsedReviewPage:
    entries: list[ReviewEntry]
    errors: list[str]


@dataclass(frozen=True)
class RefreshOutcome:
    path: Path
    added: int
    preserved: int


def review_path(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*REVIEW_PATH)


def _encode_original(entry: ReviewEntry) -> str:
    raw = json.dumps(
        {
            "description": entry.ai_original,
            "target_project": entry.candidate.target_project,
            "route": entry.candidate.route.value if entry.candidate.route else None,
            "due_date": entry.candidate.due_date,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _render_entry(entry: ReviewEntry) -> str:
    item = entry.candidate
    check = "x" if item.decision is CandidateDecision.APPROVED else " "
    payload = f"`id: {item.candidate_id}` [{item.kind.value}] {item.description}"
    if item.decision is CandidateDecision.REJECTED:
        payload = f"~~{payload}~~ #ignore"
    target = item.target_project or "unresolved"
    route = item.route.value if item.route else ""
    due = item.due_date or ""
    evidence = item.evidence.anchor if item.evidence and item.evidence.anchor else ""
    actionable = "yes" if item.is_actionable() else "no"
    return "\n".join(
        [
            f"- [{check}] {payload}",
            f"  - target_project: {target}",
            f"  - route: {route}",
            f"  - due_date: {due}",
            f"  - start_at: {item.start_at or ''}",
            f"  - end_at: {item.end_at or ''}",
            f"  - evidence: {evidence}",
            f"  - actionable: {actionable}",
            f"  - historical: {'yes' if item.historical else 'no'}",
            f"  - note: {entry.note_link}",
            f"  - transcript: {entry.transcript_link}",
            f"  - error: {entry.apply_error or ''}",
            f"  {_ORIGINAL_PREFIX.strip()} {_encode_original(entry)} -->",
        ]
    )


def render_review_page(entries: list[ReviewEntry], *, today: date | None = None) -> str:
    front = {
        "date": (today or date.today()).isoformat(),
        "type": "approval-page",
        "status": "active",
        "project": "global",
    }
    intro = """# 会议提取待确认

> `- [ ]` 待确认，`- [x]` 批准，`~~整条候选~~`（可选追加 `#ignore`）拒绝。
> 可修改正文、target_project、route 和 due_date；仅保存不会写回。
> `wb review apply` 默认只预演，必须显式添加 `--apply` 才执行。
"""
    groups: dict[tuple[str, str, str], list[ReviewEntry]] = {}
    for entry in entries:
        key = (entry.meeting_date, entry.meeting_title, entry.note_link)
        groups.setdefault(key, []).append(entry)
    sections: list[str] = []
    for (meeting_date, title, note_link), grouped in sorted(groups.items()):
        rendered = "\n\n".join(_render_entry(entry) for entry in grouped)
        sections.append(f"## {meeting_date} {title}  {note_link}\n\n{rendered}")
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    body = intro + ("\n" + "\n\n".join(sections) + "\n" if sections else "\n")
    text = f"---\n{fm}\n---\n\n{body}"
    meta, parsed_body, error = parse_frontmatter(text)
    issues = [] if error else validate_note(meta, parsed_body)
    if error or issues:
        detail = error or "; ".join(str(issue) for issue in issues)
        raise ValueError(f"审批页不符合 vault schema：{detail}")
    return text


def _field(lines: list[str], name: str) -> str:
    prefix = f"  - {name}:"
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _original(lines: list[str]) -> dict[str, object]:
    for line in lines:
        if line.startswith(_ORIGINAL_PREFIX) and line.endswith(" -->"):
            encoded = line[len(_ORIGINAL_PREFIX) : -len(" -->")].strip()
            data = base64.urlsafe_b64decode(encoded.encode("ascii"))
            loaded = json.loads(data)
            return loaded if isinstance(loaded, dict) else {}
    return {}


def _parse_entry(line: str, block: list[str], heading: str) -> ReviewEntry:
    item_match = _ITEM_RE.match(line)
    if item_match is None:
        raise ValueError("候选首行格式无效")
    checked, payload = item_match.groups()
    decision = CandidateDecision.APPROVED if checked.lower() == "x" else CandidateDecision.PENDING
    if payload.startswith("~~") and (payload.endswith("~~") or payload.endswith("~~ #ignore")):
        suffix = "~~ #ignore" if payload.endswith("~~ #ignore") else "~~"
        payload = payload[2 : -len(suffix)]
        decision = CandidateDecision.REJECTED
    payload_match = _PAYLOAD_RE.match(payload)
    if payload_match is None:
        raise ValueError("候选缺少稳定 id / kind / 正文")
    stable_id, kind_raw, description = payload_match.groups()
    target = _field(block, "target_project") or None
    route_raw = _field(block, "route")
    due = _field(block, "due_date") or None
    if due:
        date.fromisoformat(due)
    start_at = _field(block, "start_at") or None
    end_at = _field(block, "end_at") or None
    evidence_raw = _field(block, "evidence")
    original = _original(block)
    heading_parts = heading.removeprefix("## ").split(" ", 1)
    meeting_date = heading_parts[0]
    title_with_link = heading_parts[1] if len(heading_parts) > 1 else "(未知会议)"
    title = title_with_link.split("  [[", 1)[0]
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=CandidateKind(kind_raw),
        description=description,
        target_project=target,
        route=RouteTarget(route_raw) if route_raw else None,
        evidence=EvidenceRef(anchor=evidence_raw) if evidence_raw else None,
        due_date=due,
        start_at=start_at,
        end_at=end_at,
        is_next_step=True,
        decision=decision,
        historical=_field(block, "historical") == "yes",
    )
    return ReviewEntry(
        candidate=candidate,
        ai_original=str(original.get("description") or description),
        meeting_date=meeting_date,
        meeting_title=title,
        note_link=_field(block, "note"),
        transcript_link=_field(block, "transcript"),
        apply_error=_field(block, "error") or None,
    )


def parse_review_page(text: str) -> ParsedReviewPage:
    meta, body, error = parse_frontmatter(text)
    if error is not None:
        return ParsedReviewPage([], [error])
    if meta.get("type") != "approval-page":
        return ParsedReviewPage([], ["不是 approval-page"])
    lines = body.splitlines()
    entries: list[ReviewEntry] = []
    errors: list[str] = []
    heading = ""
    index = 0
    in_comment = False
    while index < len(lines):
        line = lines[index]
        if in_comment:
            if "-->" in line:
                in_comment = False
            index += 1
            continue
        if "<!--" in line and not line.startswith(_ORIGINAL_PREFIX):
            if "-->" not in line:
                in_comment = True
            index += 1
            continue
        if line.startswith("## "):
            heading = line
        if _ITEM_RE.match(line):
            block: list[str] = []
            cursor = index + 1
            while (
                cursor < len(lines)
                and not _ITEM_RE.match(lines[cursor])
                and not lines[cursor].startswith("## ")
            ):
                if lines[cursor].strip():
                    block.append(lines[cursor])
                cursor += 1
            try:
                entries.append(_parse_entry(line, block, heading))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f"第 {index + 1} 行：{exc}")
            index = cursor
            continue
        index += 1
    ids = [entry.candidate.candidate_id for entry in entries]
    duplicates = sorted({stable_id for stable_id in ids if ids.count(stable_id) > 1})
    if duplicates:
        errors.append(f"候选 ID 重复：{duplicates}")
    return ParsedReviewPage(entries, errors)


def refresh_review_page(
    vault_dir: Path, generated: list[ReviewEntry], *, today: date | None = None
) -> RefreshOutcome:
    """新增候选，保留审批页中已有的勾选状态和用户编辑。"""
    # 读旧页 → 合并 → 整页原子重写 的整体与 set_decision/set_decisions/apply 收尾
    # 互斥（同一把 .wb.lock），防止并发 refresh 与人工勾选交错丢更新。
    with workspace_lock(vault_dir.parent):
        path = review_path(vault_dir)
        existing: list[ReviewEntry] = []
        if path.is_file():
            parsed = parse_review_page(path.read_text(encoding="utf-8"))
            if parsed.errors:
                raise ValueError("审批页存在语法错误，拒绝覆盖：" + "; ".join(parsed.errors))
            existing = parsed.entries
        by_id = {entry.candidate.candidate_id: entry for entry in existing}
        added = 0
        for entry in generated:
            stable_id = entry.candidate.candidate_id
            if stable_id not in by_id:
                by_id[stable_id] = entry
                added += 1
        combined = list(by_id.values())
        atomic_write_text(path, render_review_page(combined, today=today), ensure_parents=True)
        return RefreshOutcome(path, added=added, preserved=len(existing))
