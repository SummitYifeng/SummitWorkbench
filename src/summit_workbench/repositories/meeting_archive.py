"""会议归档持久层：把完整逐字稿写成证据层 Markdown（PRD 3.1.9 L15）。

- 证据层文件 ``type: meeting-transcript``，``status: archived``，保留说话人/时间戳/来源标识，
  不与 AI 摘要混写；录像不下载，仅留来源标识。
- 在**模型调用之前**可靠落盘（M1-2）；结构化会议笔记（理解层）由 M1-3 产出并回链本文件。
- 写入幂等：证据文件已存在则不覆盖（除非显式 ``overwrite``），避免重复归档破坏证据。

命名 ``<date>-<slug>-transcript.md``，``slug`` 由标题派生；结构化笔记用同一 ``slug`` 回链
（见 ``transcript_stem`` / ``note_stem``），保证 wikilink 与实际文件名一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.review import UNRESOLVED

MEETINGS_SUBDIR = "meetings"
TRANSCRIPTS_SUBDIR = "transcripts"  # 证据层
NOTES_SUBDIR = "notes"  # 理解与行动层（M1-3 结构化笔记）

_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)
_SLUG_MAX = 60


def meetings_dir(vault_dir: Path) -> Path:
    """会议档案根目录 ``<vault>/meetings/``（ADR 0003 / PRD 结构）。"""
    return vault_dir / MEETINGS_SUBDIR


def transcripts_dir(vault_dir: Path) -> Path:
    """逐字稿证据层目录 ``<vault>/meetings/transcripts/``（首次归档按需创建）。"""
    return meetings_dir(vault_dir) / TRANSCRIPTS_SUBDIR


def notes_dir(vault_dir: Path) -> Path:
    """结构化会议笔记目录 ``<vault>/meetings/notes/``（M1-3 使用）。"""
    return meetings_dir(vault_dir) / NOTES_SUBDIR


def slugify(title: str) -> str:
    """把标题压成文件名安全的 slug（保留中文/字母/数字，其余折成 ``-``）。"""
    slug = _SLUG_RE.sub("-", title.strip()).strip("-")
    return (slug[:_SLUG_MAX].strip("-") or "untitled")


def transcript_stem(date: str, slug: str) -> str:
    """逐字稿证据文件的文件名主干（不含扩展名），供结构化笔记回链。"""
    return f"{date}-{slug}-transcript"


def note_stem(date: str, slug: str) -> str:
    """结构化会议笔记的文件名主干（不含扩展名），供 M1-3 使用。"""
    return f"{date}-{slug}"


@dataclass(frozen=True)
class MeetingArchiveInput:
    """归档一场会议逐字稿所需的元数据与正文。

    ``projects`` 在模型理解之前通常未知，默认 ``[unresolved]``（L22 占位约定）；调用方
    若已知关联项目可显式传入。
    """

    date: str  # YYYY-MM-DD
    title: str
    transcript_text: str
    source: SourceKind
    meeting_id: str | None = None
    note_id: str | None = None
    projects: list[str] = field(default_factory=lambda: [UNRESOLVED])


@dataclass(frozen=True)
class ArchiveOutcome:
    """归档结果。``written=False`` 表示证据文件已存在、幂等跳过。"""

    path: Path
    written: bool


def render_transcript(inp: MeetingArchiveInput) -> str:
    """渲染逐字稿证据层 Markdown（frontmatter + 证据正文）。"""
    front = {
        "date": inp.date,
        "type": "meeting-transcript",
        "status": "archived",
        "meeting_id": inp.meeting_id or "",
        "note_id": inp.note_id or "",
        "source": inp.source.value,
        "projects": list(inp.projects) or [UNRESOLVED],
    }
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    body = (
        f"# {inp.title} · 完整逐字稿\n\n"
        "<!-- 证据层：保留说话人、相对时间戳与飞书来源标识；不与 AI 摘要混写 -->\n"
        "<!-- 录像不下载，仅保留来源标识以便回看 -->\n\n"
        f"{inp.transcript_text.strip()}\n"
    )
    return f"---\n{fm}\n---\n\n{body}"


def transcript_path(vault_dir: Path, inp: MeetingArchiveInput) -> Path:
    """该会议逐字稿证据文件的目标路径（不落盘）。"""
    return transcripts_dir(vault_dir) / f"{transcript_stem(inp.date, slugify(inp.title))}.md"


def archive_transcript(
    vault_dir: Path, inp: MeetingArchiveInput, *, overwrite: bool = False
) -> ArchiveOutcome:
    """把逐字稿写入证据层文件；已存在且未 ``overwrite`` 则幂等跳过、不覆盖。"""
    path = transcript_path(vault_dir, inp)
    if path.exists() and not overwrite:
        return ArchiveOutcome(path=path, written=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_transcript(inp), encoding="utf-8")
    return ArchiveOutcome(path=path, written=True)
