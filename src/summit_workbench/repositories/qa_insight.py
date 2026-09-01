"""qa-insight 笔记落盘（PRD M1-6 ``--save``）。

只有显式保存时才生成；派生洞察落 ``<vault>/insights/``，frontmatter ``type: qa-insight``、
``project: global``。事实检索默认排除该类型（见 retrieval），避免问答吃自己的产出。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.domain.qa import QaAnswer
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.meeting_archive import slugify
from summit_workbench.repositories.vault import parse_frontmatter

INSIGHTS_SUBDIR = "insights"


@dataclass(frozen=True)
class QaInsightInput:
    question: str
    answer: QaAnswer
    source_ids: list[str]
    model_id: str
    prompt_version: str
    date: str


@dataclass(frozen=True)
class QaInsightOutcome:
    path: Path
    written: bool


def insights_dir(vault_dir: Path) -> Path:
    return vault_dir / INSIGHTS_SUBDIR


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def _facts_block(inp: QaInsightInput) -> str:
    if not inp.answer.facts:
        return "- 无"
    return "\n".join(f"- {fact.text}（来源：[[{fact.source_id}]]）" for fact in inp.answer.facts)


def _conflicts_block(inp: QaInsightInput) -> str:
    if not inp.answer.conflicts:
        return "- 无"
    lines: list[str] = []
    for conflict in inp.answer.conflicts:
        lines.append(f"- {conflict.topic}")
        for side in conflict.sides:
            lines.append(f"  - {side.position}（来源：[[{side.source_id}]]）")
    return "\n".join(lines)


def render_qa_insight(inp: QaInsightInput) -> str:
    fm = "\n".join(
        [
            f"date: {inp.date}",
            "type: qa-insight",
            "status: generated",
            "project: global",
            f"model: {inp.model_id}",
            f"prompt: {inp.prompt_version}",
        ]
    )
    body = f"""# 问答：{inp.question}

## 回答

{inp.answer.summary}

## 事实

{_facts_block(inp)}

## 建议

{_bullets(inp.answer.suggestions)}

## 证据冲突

{_conflicts_block(inp)}

## 来源

{_bullets([f"[[{sid}]]" for sid in inp.source_ids])}
"""
    rendered = f"---\n{fm}\n---\n\n{body}"
    meta, parsed_body, error = parse_frontmatter(rendered)
    issues = [] if error else validate_note(meta, parsed_body)
    if error or issues:
        detail = error or "; ".join(str(issue) for issue in issues)
        raise ValueError(f"qa-insight 不符合 vault schema：{detail}")
    return rendered


def _stem(inp: QaInsightInput) -> str:
    digest = hashlib.sha256(inp.question.encode("utf-8")).hexdigest()[:8]
    return f"{inp.date}-{slugify(inp.question)}-{digest}"


def save_qa_insight(vault_dir: Path, inp: QaInsightInput) -> QaInsightOutcome:
    """原子写入 qa-insight；同问题同日已存在则不覆盖（幂等）。"""
    path = insights_dir(vault_dir) / f"{_stem(inp)}.md"
    if path.exists():
        return QaInsightOutcome(path=path, written=False)
    rendered = render_qa_insight(inp)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)
    return QaInsightOutcome(path=path, written=True)


def qa_insight_date(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()
