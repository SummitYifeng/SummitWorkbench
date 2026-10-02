"""周复盘单测：ISO 周math / 去重分区 / 采集(git+会议笔记+线程停滞) / 渲染 / 端到端幂等。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from summit_workbench.domain.approval import approval_record
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
from summit_workbench.workflows.weekly.collect import (
    THREAD_STALL_DAYS,
    collect_weekly,
    extract_section_bullets,
)
from summit_workbench.workflows.weekly.render import render_weekly
from summit_workbench.workflows.weekly.weekly import generate_weekly


def _approved_note(path: Path, metadata: dict[str, object], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata["approval"] = approval_record(metadata, body, operation_id="weekly-test")
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")


def _thread_archive(
    vault: Path,
    project: str,
    *,
    updated: str,
    status: str = "active",
    blocked: str = "无",
    followup: str = "",
    quote_updated: bool = True,
    activity_at: str | None = None,
) -> None:
    """写一篇线程主档案（无对应 Work 文件夹 → thread_projects 会视为知识线程）。"""
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_line = f"updated: '{updated}'" if quote_updated else f"updated: {updated}"
    activity_line = f"activity_at: '{activity_at}'\n" if activity_at else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-01\ntype: project-main\nstatus: {status}\n"
        f"{updated_line}\n{activity_line}---\n\n# {project}\n\n## 当前状态\n\n## 下一步\n\n"
        f"## 阻塞\n{blocked}\n\n## 决策记录\n\n## 跟进事项\n{followup}\n",
        encoding="utf-8",
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


def test_collect_weekly_from_approved_work_logs_and_meeting_notes(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    _thread_archive(vault, "P", updated="2026-08-26", followup="- [ ] 待办")
    meeting = vault / "meetings" / "notes" / "2026-08-26-周会.md"
    _approved_note(
        meeting,
        {"date": "2026-08-26", "title": "周会", "type": "meeting-note", "status": "active"},
        "## 已形成决策\n- 决定发布 v2\n",
    )
    log = vault / "logs" / "2026-08-26-001.md"
    _approved_note(
        log,
        {
            "date": "2026-08-26",
            "title": "完成登录",
            "type": "work-log",
            "status": "active",
            "projects": ["P"],
        },
        "## 今天 / 本周做了什么\n\n完成登录\n",
    )

    signals = collect_weekly(
        work, vault, start_iso="2026-08-24", end_iso="2026-08-30", pending_review_count=2
    )
    assert any("完成登录" in item.text for item in signals.completed)
    assert any(item.source_ref == "logs/2026-08-26-001.md" for item in signals.completed)
    assert any("发布 v2" in item.text for item in signals.decisions)
    assert any("待确认 2 条" in item.text for item in signals.unclosed)


def test_collect_weekly_flags_stalled_project_from_registry_not_git(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    _thread_archive(vault, "Idle", updated="2026-01-01", followup="- [ ] 未闭环")
    (work / "Idle").mkdir(parents=True)
    (work / "UnregisteredSourceRepo").mkdir()

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    assert any(item.project == "Idle" for item in signals.stalled)
    assert all(item.project != "UnregisteredSourceRepo" for item in signals.stalled)


# —— 线程内容停滞（P3）：N 天无更新 + 有未决/未闭环跟进 → 停滞点名 ——


def _stale_thread(
    vault: Path,
    project: str,
    *,
    updated: str,
    status: str = "active",
    blocked: str = "无",
    followup: str = "- [ ] 木子月底前完成 Coach 梳理",
    quote_updated: bool = True,
) -> None:
    """写一篇「停滞候选」线程档案：默认带一条未闭环跟进。"""
    _thread_archive(
        vault,
        project,
        updated=updated,
        status=status,
        blocked=blocked,
        followup=followup,
        quote_updated=quote_updated,
    )


def test_collect_weekly_names_stale_thread_with_open_followup(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    # 距复盘周截止日（2026-08-30）远超 14 天的线程 + 未闭环跟进 → 停滞点名
    _stale_thread(vault, "FinanceOps", updated="2026-07-01")

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    item = next(s for s in signals.stalled if s.project == "FinanceOps")
    assert "60 天无更新" in item.text
    assert "1 条跟进待闭环" in item.text
    assert item.source_ref == "projects/FinanceOps.md#跟进事项"
    assert item.evidence is EvidenceLevel.E2


def test_s2_recent_activity_does_not_exempt_stale_thread(tmp_path: Path) -> None:
    """S2：停滞线程（updated 超 14 天 + 未闭环跟进）即使最近有日志活动（activity_at 新）
    也不被豁免点名——停滞判据只读实质更新 updated（P1 语义拆分）。"""
    work = tmp_path / "Work"
    vault = work / "_vault"
    # 实质更新停留在 2026-07-01（>14 天），但最近一天刚有推进日志/产物（activity_at 新）
    _thread_archive(
        vault,
        "BusyOps",
        updated="2026-07-01",
        activity_at="2026-08-29",
        followup="- [ ] 木子月底前完成 Coach 梳理",
    )

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    item = next(s for s in signals.stalled if s.project == "BusyOps")
    assert "60 天无更新" in item.text
    assert item.source_ref == "projects/BusyOps.md#跟进事项"


def test_collect_weekly_thread_stall_ignores_recent_or_clean(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    # 最近有更新（阈值内）：不点名
    _stale_thread(vault, "RecentOps", updated="2026-08-28")
    # 停滞但跟进已闭环（档案干净）：不点名
    _thread_archive(vault, "DoneOps", updated="2026-07-01", followup="- [x] 已闭环")
    # 停滞但完全无跟进条目、无阻塞：不点名
    _thread_archive(vault, "EmptyOps", updated="2026-07-01")
    # archived 线程：不点名
    _stale_thread(vault, "RetiredOps", updated="2026-07-01", status="archived")

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    named = {s.project for s in signals.stalled}
    assert "FinanceOps" not in named  # 本测试未创建
    assert "RecentOps" not in named
    assert "DoneOps" not in named
    assert "EmptyOps" not in named
    assert "RetiredOps" not in named


def test_collect_weekly_thread_stall_blocked_only_and_threshold(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    # 只有阻塞、无跟进条目 → 也点名（未决 = 阻塞），锚点指向 #阻塞
    _thread_archive(
        vault, "BlockedOps", updated="2026-07-01", blocked="等金老师回复税务口径", followup=""
    )
    # 恰好 14 天：阈值是「超过 14 天」，不点名；第 15 天点名（两者都带未闭环跟进）
    stale_end = date(2026, 8, 30)
    _thread_archive(
        vault,
        "Edge14",
        updated=(stale_end - timedelta(days=14)).isoformat(),
        followup="- [ ] 待闭环跟进",
    )
    _thread_archive(
        vault,
        "Edge15",
        updated=(stale_end - timedelta(days=15)).isoformat(),
        followup="- [ ] 待闭环跟进",
    )

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    by_name = {s.project: s for s in signals.stalled}
    blocked_item = by_name["BlockedOps"]
    assert "阻塞：等金老师回复税务口径" in blocked_item.text
    assert blocked_item.source_ref == "projects/BlockedOps.md#阻塞"
    assert "Edge14" not in by_name
    assert "Edge15" in by_name
    assert THREAD_STALL_DAYS == 14


def test_collect_weekly_thread_stall_unquoted_updated_date(tmp_path: Path) -> None:
    """frontmatter 的 updated 未加引号时 YAML 解析成 date 对象，也应能判停滞（P3 数据兼容）。"""
    work = tmp_path / "Work"
    vault = work / "_vault"
    _stale_thread(vault, "UnquotedOps", updated="2026-07-01", quote_updated=False)

    signals = collect_weekly(work, vault, start_iso="2026-08-24", end_iso="2026-08-30")
    assert any(s.project == "UnquotedOps" for s in signals.stalled)


def test_weekly_thread_stall_flows_into_render_and_proposals(tmp_path: Path) -> None:
    """端到端：停滞线程出现在渲染的「停滞项目」区块，并派生「推进」提议。"""
    work = tmp_path / "Work"
    vault = work / "_vault"
    _stale_thread(vault, "FinanceOps", updated="2026-07-01")

    result = generate_weekly(work, vault, today=date(2026, 9, 1))
    assert "## 停滞项目" in result.markdown
    assert "FinanceOps" in result.markdown
    assert "天无更新" in result.markdown
    assert any(
        p.project == "FinanceOps" and "推进停滞项目" in p.text for p in result.review.proposals
    )


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
