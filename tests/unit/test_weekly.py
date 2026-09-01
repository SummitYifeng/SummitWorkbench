"""周复盘单测：ISO 周math / 去重分区 / 采集(git+会议笔记) / 渲染 / 端到端幂等。"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from summit_workbench.domain.brief import EvidenceLevel
from summit_workbench.domain.weekly import (
    WeeklyItem,
    WeeklySignals,
    build_review,
    derive_proposals,
    iso_week,
    previous_week_bounds,
    week_bounds,
)
from summit_workbench.workflows.weekly.collect import collect_weekly, extract_section_bullets
from summit_workbench.workflows.weekly.render import render_weekly
from summit_workbench.workflows.weekly.weekly import generate_weekly


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _commit_at(path: Path, message: str, when_iso: str) -> None:
    """在指定提交日期（committer date，git log --since/--until 据此过滤）落一条提交。"""
    import os

    env = {**os.environ, "GIT_COMMITTER_DATE": when_iso, "GIT_AUTHOR_DATE": when_iso}
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
        env=env,
    )


# —— 周 math ——


def test_iso_week_and_bounds() -> None:
    # 2026-09-01 是周二
    assert date(2026, 9, 1).weekday() == 1
    mon, sun = week_bounds(date(2026, 9, 1))
    assert mon == date(2026, 8, 31)
    assert sun == date(2026, 9, 6)
    assert iso_week(mon) == iso_week(date(2026, 9, 1))


def test_previous_week_bounds() -> None:
    # 2026-09-01（周二）的上一周 = 8/24 ~ 8/30
    mon, sun = previous_week_bounds(date(2026, 9, 1))
    assert mon == date(2026, 8, 24)
    assert sun == date(2026, 8, 30)


# —— 去重 + 提议 ——


def test_build_review_dedups_items() -> None:
    signals = WeeklySignals(
        completed=[
            WeeklyItem("修 bug", "P@a1", project="P"),
            WeeklyItem("修 bug", "P@a1", project="P"),  # 重复
            WeeklyItem("修 bug", "Q@b2", project="Q"),  # 不同项目不算重复
        ]
    )
    review = build_review("2026-W35", "2026-08-24", "2026-08-30", signals)
    assert len(review.completed) == 2


def test_derive_proposals_from_stalled_and_unclosed() -> None:
    signals = WeeklySignals(
        stalled=[WeeklyItem("P（本周无提交）", "/p", project="P")],
        unclosed=[WeeklyItem("全局 inbox 待处理 3 条", "inbox.md")],
    )
    proposals = derive_proposals(signals)
    assert any(p.project == "P" and p.evidence is EvidenceLevel.E3 for p in proposals)
    assert any("清理未闭合" in p.text for p in proposals)


# —— 采集 ——


def test_extract_section_bullets() -> None:
    body = "## 已形成决策\n- 采用方案 A\n- [x] 冻结范围\n\n## 明确行动项\n- 别的\n"
    assert extract_section_bullets(body, "已形成决策") == ["采用方案 A", "冻结范围"]


def test_collect_weekly_from_git_and_meeting_notes(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    (vault / "meetings" / "notes").mkdir(parents=True)
    # 本周内的会议笔记（含决策）
    (vault / "meetings" / "notes" / "2026-08-26-周会.md").write_text(
        "---\ndate: 2026-08-26\ntype: meeting-note\nstatus: active\nprojects: [P]\n---\n"
        "## 已形成决策\n- 决定发布 v2\n## 明确行动项\n- x\n",
        encoding="utf-8",
    )
    # 一个本周有提交的 git 项目
    proj = work / "P"
    proj.mkdir(parents=True)
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "t@e.com")
    _git(proj, "config", "user.name", "t")
    (proj / "f.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "f.txt")
    _commit_at(proj, "feat: 完成登录", "2026-08-26T10:00:00")

    signals = collect_weekly(
        work, vault, start_iso="2026-08-24", end_iso="2026-08-30", pending_review_count=2
    )
    assert any("完成登录" in c.text for c in signals.completed)
    assert any("发布 v2" in d.text for d in signals.decisions)
    assert any("待确认 2 条" in u.text for u in signals.unclosed)


def test_collect_weekly_flags_stalled_project(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    proj = work / "Idle"
    proj.mkdir(parents=True)
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "t@e.com")
    _git(proj, "config", "user.name", "t")
    (proj / "f.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "f.txt")
    _commit_at(proj, "old", "2026-01-01T10:00:00")

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    assert any(s.project == "Idle" for s in signals.stalled)


# —— 渲染 + 端到端幂等 ——


def test_render_separates_facts_and_proposals() -> None:
    signals = WeeklySignals(
        completed=[WeeklyItem("修 bug", "P@a1", project="P")],
        stalled=[WeeklyItem("Q（本周无提交）", "/q", project="Q")],
    )
    review = build_review("2026-W35", "2026-08-24", "2026-08-30", signals)
    md = render_weekly(review)
    assert "## 本周完成" in md
    assert "## 下周建议（AI 建议，非事实）" in md
    assert "修 bug" in md  # 事实附来源
    assert "P@a1" in md


def test_generate_weekly_idempotent(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    first = generate_weekly(work, vault, today=date(2026, 9, 1))
    assert first.note_path is not None and first.note_path.is_file()
    assert first.review.week == "2026-W35"  # 上一周
    text1 = first.note_path.read_text(encoding="utf-8")
    second = generate_weekly(work, vault, today=date(2026, 9, 1))
    assert second.note_path is not None
    assert second.note_path.read_text(encoding="utf-8") == text1  # 覆盖、内容一致
