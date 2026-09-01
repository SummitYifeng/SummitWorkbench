"""M1-4：只从明确决策/行动项生成稳定候选，普通事实不升级。"""

from __future__ import annotations

from summit_workbench.domain.meeting import (
    ActionItem,
    Decision,
    MeetingExtraction,
    SourcedStatement,
)
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.domain.review import CandidateKind, RouteTarget
from summit_workbench.repositories.meeting_note import MeetingNoteInput, archive_meeting_note
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note


def _note(tmp_path):
    extraction = MeetingExtraction(
        one_minute_summary="摘要",
        facts=[SourcedStatement(text="事实不能升级", evidence="张三 00:01")],
        decisions=[Decision(description="采用 A", target_project="P1", evidence="李四 00:02")],
        action_items=[
            ActionItem(description="内部推进", target_project="P1", evidence="王五 00:03"),
            ActionItem(
                description="周五交付",
                target_project="P2",
                due_date="2026-09-04",
                evidence="赵六 00:04",
            ),
            ActionItem(description="待定归属", evidence="段落 5"),
        ],
    )
    return archive_meeting_note(
        tmp_path,
        MeetingNoteInput(
            date="2026-08-31",
            title="评审会",
            idem_key="m:n",
            extraction=extraction,
            source=SourceKind.FEISHU_NOTE,
            transcript_stem="2026-08-31-评审会-transcript",
            model_id="m",
            prompt_version="p@v2",
        ),
    ).path


def test_generates_decisions_and_actions_only_with_stable_routes(tmp_path):
    # 路由测试需要 P1/P2 是已建项目才能解析命中（否则按新默认走全局 inbox）。
    _project(tmp_path, "P1", aliases=[])
    _project(tmp_path, "P2", aliases=[])
    entries = candidates_from_note(_note(tmp_path), tmp_path)
    assert len(entries) == 4
    assert [entry.candidate.kind for entry in entries] == [
        CandidateKind.DECISION,
        CandidateKind.ACTION_ITEM,
        CandidateKind.ACTION_ITEM,
        CandidateKind.ACTION_ITEM,
    ]
    assert entries[0].candidate.candidate_id == "m:n#decision-0"
    assert entries[0].candidate.route == RouteTarget.PROJECT_MAIN
    assert entries[1].candidate.route == RouteTarget.PROJECT_MAIN
    assert entries[2].candidate.route == RouteTarget.FEISHU_TASK
    assert entries[3].candidate.route == RouteTarget.GLOBAL_INBOX
    # 未匹配项目 → 全局 inbox 兜底捕获，可写回（不再 dead-end 为 error）。
    assert entries[3].candidate.is_actionable() is True


def _project(vault, project: str, *, aliases: list[str]) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        f"aliases: [{', '.join(aliases)}]\n---\n\n# {project}\n\n"
        "## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n",
        encoding="utf-8",
    )


def _note_with_project(tmp_path, target: str):
    extraction = MeetingExtraction(
        one_minute_summary="摘要",
        decisions=[Decision(description="采用 A", target_project=target, evidence="李四 00:02")],
    )
    return archive_meeting_note(
        tmp_path,
        MeetingNoteInput(
            date="2026-08-31",
            title="评审会",
            idem_key="m:n",
            extraction=extraction,
            source=SourceKind.FEISHU_NOTE,
            transcript_stem="2026-08-31-评审会-transcript",
            model_id="m",
            prompt_version="p@v2",
        ),
    ).path


def test_natural_language_project_resolves_to_canonical_id(tmp_path):
    _project(tmp_path, "HIC_WebClass_Chinese_Final", aliases=["网课系统"])
    entries = candidates_from_note(_note_with_project(tmp_path, "网课系统"), tmp_path)
    assert entries[0].candidate.target_project == "HIC_WebClass_Chinese_Final"
    assert entries[0].candidate.route == RouteTarget.PROJECT_MAIN
    assert entries[0].candidate.is_actionable() is True


def test_unmatched_project_captures_to_global_inbox(tmp_path):
    # 无 projects 目录 → 模型给的项目名无法解析 → unresolved → 全局 inbox 兜底、可写回。
    entries = candidates_from_note(_note_with_project(tmp_path, "某个还没建的项目"), tmp_path)
    assert entries[0].candidate.target_project == "unresolved"
    assert entries[0].candidate.route == RouteTarget.GLOBAL_INBOX
    assert entries[0].candidate.is_actionable() is True


def test_existing_note_without_embedded_extraction_uses_body_fallback(tmp_path):
    path = _note(tmp_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = lines.index("extraction:")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1
    path.write_text("\n".join([*lines[:start], *lines[end:]]) + "\n", encoding="utf-8")
    entries = candidates_from_note(path, tmp_path)
    assert len(entries) == 4
    assert entries[2].candidate.due_date == "2026-09-04"
