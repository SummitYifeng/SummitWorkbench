"""逐字稿证据层归档：渲染、schema 合法性、幂等写入（M1-2）。"""

from __future__ import annotations

from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.meeting_archive import (
    MeetingArchiveInput,
    archive_transcript,
    render_transcript,
    slugify,
    transcript_stem,
)
from summit_workbench.repositories.vault import parse_frontmatter


def _input(**kw) -> MeetingArchiveInput:
    base = dict(
        date="2026-08-30",
        title="招生进度会",
        transcript_text="张三 00:01 大家好\n李四 00:05 我们开始",
        source=SourceKind.FEISHU_NOTE,
        meeting_id="m1",
        note_id="n1",
    )
    base.update(kw)
    return MeetingArchiveInput(**base)  # type: ignore[arg-type]


def test_slugify_keeps_cjk_and_folds_unsafe():
    assert slugify("招生进度会（8月）") == "招生进度会-8月"
    assert slugify("a / b : c") == "a-b-c"
    assert slugify("   ") == "untitled"


def test_rendered_transcript_passes_vault_schema():
    meta, body, error = parse_frontmatter(render_transcript(_input()))
    assert error is None
    assert validate_note(meta, body) == []  # meeting-transcript 需非空 projects
    assert meta["type"] == "meeting-transcript"
    assert meta["status"] == "archived"
    assert meta["projects"] == ["unresolved"]  # 默认占位


def test_rendered_transcript_contains_body_and_no_ai_mixing():
    text = render_transcript(_input())
    assert "张三 00:01 大家好" in text  # 保留说话人+时间戳的原文
    assert "证据层" in text
    assert "AI 建议" not in text  # 证据层不与 AI 摘要混写


def test_archive_writes_then_is_idempotent(tmp_path):
    inp = _input()
    first = archive_transcript(tmp_path, inp)
    assert first.written is True
    assert first.path.exists()
    original = first.path.read_text(encoding="utf-8")

    second = archive_transcript(tmp_path, inp)
    assert second.written is False  # 幂等：不覆盖证据
    assert second.path == first.path
    assert second.path.read_text(encoding="utf-8") == original


def test_archive_overwrite_when_requested(tmp_path):
    archive_transcript(tmp_path, _input(transcript_text="旧内容 00:01"))
    out = archive_transcript(tmp_path, _input(transcript_text="新内容 00:02"), overwrite=True)
    assert out.written is True
    assert "新内容 00:02" in out.path.read_text(encoding="utf-8")


def test_transcript_stem_matches_filename(tmp_path):
    inp = _input()
    out = archive_transcript(tmp_path, inp)
    assert out.path.stem == transcript_stem("2026-08-30", slugify("招生进度会"))


def test_transcript_lands_in_meetings_transcripts_subdir(tmp_path):
    # ADR 0003 / PRD 结构：证据层落 meetings/transcripts/，笔记落 meetings/notes/。
    out = archive_transcript(tmp_path, _input())
    assert out.path.parent == tmp_path / "meetings" / "transcripts"


def test_explicit_projects_rendered(tmp_path):
    text = render_transcript(_input(projects=["ProjA", "ProjB"]))
    meta, _body, _err = parse_frontmatter(text)
    assert meta["projects"] == ["ProjA", "ProjB"]
