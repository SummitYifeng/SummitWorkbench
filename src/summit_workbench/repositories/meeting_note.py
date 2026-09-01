"""结构化会议笔记的渲染与原子、幂等落盘。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from summit_workbench.domain.meeting import MeetingExtraction
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.review import UNRESOLVED
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.meeting_archive import note_stem, notes_dir, slugify
from summit_workbench.repositories.vault import parse_frontmatter


@dataclass(frozen=True)
class MeetingNoteInput:
    date: str
    title: str
    idem_key: str
    extraction: MeetingExtraction
    source: SourceKind
    transcript_stem: str
    model_id: str
    prompt_version: str
    meeting_id: str | None = None
    note_id: str | None = None
    projects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NoteOutcome:
    path: Path
    written: bool


def _projects(inp: MeetingNoteInput) -> list[str]:
    values = [project for project in inp.projects if project and project != UNRESOLVED]
    values.extend(
        decision.target_project for decision in inp.extraction.decisions if decision.target_project
    )
    values.extend(
        action.target_project for action in inp.extraction.action_items if action.target_project
    )
    unique = list(dict.fromkeys(values))
    return unique or [UNRESOLVED]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def render_meeting_note(inp: MeetingNoteInput) -> str:
    """生成符合 vault schema 的理解层 Markdown，并保留每条原文证据。"""
    projects = _projects(inp)
    front = {
        "date": inp.date,
        "type": "meeting-note",
        "status": "pending-review",
        "meeting_id": inp.meeting_id or "",
        "note_id": inp.note_id or "",
        "idem_key": inp.idem_key,
        "source": inp.source.value,
        "projects": projects,
        "transcript": f"[[{inp.transcript_stem}]]",
        "model": inp.model_id,
        "prompt_version": inp.prompt_version,
        "extraction": inp.extraction.model_dump(mode="json"),
    }
    facts = [f"{item.text}（证据：{item.evidence}）" for item in inp.extraction.facts]
    decisions = [
        f"{item.description}（项目：{item.target_project or UNRESOLVED}；证据：{item.evidence}）"
        for item in inp.extraction.decisions
    ]
    actions = [
        f"{item.description}（项目：{item.target_project or UNRESOLVED}；"
        f"截止：{item.due_date or '无'}；证据：{item.evidence}）"
        for item in inp.extraction.action_items
    ]
    questions = [f"{item.text}（证据：{item.evidence}）" for item in inp.extraction.open_questions]
    evidence = list(
        dict.fromkeys(
            [item.evidence for item in inp.extraction.facts]
            + [item.evidence for item in inp.extraction.decisions]
            + [item.evidence for item in inp.extraction.action_items]
            + [item.evidence for item in inp.extraction.open_questions]
        )
    )
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    body = f"""# {inp.title}

## 一分钟摘要

{inp.extraction.one_minute_summary}

## 会议信息

- 日期：{inp.date}
- 来源：{inp.source.value}
- 原文：[[{inp.transcript_stem}]]

## 事实与进展

{_bullets(facts)}

## 已形成决策

{_bullets(decisions)}

## 明确行动项

{_bullets(actions)}

## 未决问题

{_bullets(questions)}

## AI 建议

{_bullets(inp.extraction.ai_suggestions)}

## 关联项目

{_bullets(projects)}

## 证据索引

{_bullets([f"[[{inp.transcript_stem}]] · {item}" for item in evidence])}
"""
    rendered = f"---\n{fm}\n---\n\n{body}"
    meta, parsed_body, error = parse_frontmatter(rendered)
    issues = [] if error else validate_note(meta, parsed_body)
    if error or issues:
        detail = error or "; ".join(str(issue) for issue in issues)
        raise ValueError(f"结构化会议笔记不符合 vault schema：{detail}")
    return rendered


def archive_meeting_note(
    vault_dir: Path, inp: MeetingNoteInput, *, overwrite: bool = False
) -> NoteOutcome:
    """原子写入结构化笔记；既有文件默认不覆盖，避免重跑破坏人工编辑。"""
    path = notes_dir(vault_dir) / f"{note_stem(inp.date, slugify(inp.title))}.md"
    if path.exists() and not overwrite:
        return NoteOutcome(path=path, written=False)
    rendered = render_meeting_note(inp)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)
    return NoteOutcome(path=path, written=True)
