"""简报的 repository 层单测：项目扫描 / 信号快照 / daily 幂等写入。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from summit_workbench.repositories.daily_note import (
    BRIEF_END,
    BRIEF_START,
    write_brief,
)
from summit_workbench.repositories.project_scan import (
    count_inbox_pending,
    extract_next_step,
    scan_projects,
)
from summit_workbench.repositories.signal_snapshot import (
    mark_task_completed,
    read_snapshot,
    write_snapshot,
)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")


# —— 纯解析 ——


def test_count_inbox_pending_only_open_checkboxes() -> None:
    text = "## 待处理\n- [ ] 甲\n- [x] 已完成\n- [ ] 乙\n说明文字\n"
    assert count_inbox_pending(text) == 2


def test_extract_next_step_takes_first_line_under_heading() -> None:
    body = "## 当前状态\n推进中\n\n## 下一步\n- [ ] 完成招生页\n- 次要项\n\n## 阻塞\n无\n"
    assert extract_next_step(body) == "完成招生页"


def test_extract_next_step_none_when_empty() -> None:
    body = "## 下一步\n\n## 阻塞\n无\n"
    assert extract_next_step(body) is None


def test_extract_next_step_skips_html_comment_placeholder() -> None:
    # 模板未填：只有占位注释 → 视为无下一步（不当成真实行动）
    body = "## 下一步\n<!-- 明确的下一步行动；会议审批通过后写入此处 -->\n\n## 阻塞\n"
    assert extract_next_step(body) is None
    # 占位注释后有真实内容 → 取真实内容
    body2 = "## 下一步\n<!-- 占位 -->\n- 完成第 3 章排版\n## 阻塞\n"
    assert extract_next_step(body2) == "完成第 3 章排版"


# —— 项目扫描（真实临时 git 仓库）——


def test_scan_projects_reports_dirty_and_inbox_and_next_step(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    (vault / "projects").mkdir(parents=True)
    # 项目主笔记提供「下一步」
    (vault / "projects" / "ProjA.md").write_text(
        "---\nproject: ProjA\ndate: 2026-09-01\ntype: project-main\nstatus: active\n---\n"
        "## 当前状态\nok\n## 下一步\n- 发布 v2\n## 阻塞\n无\n## 决策记录\n无\n",
        encoding="utf-8",
    )
    proj = work_root / "ProjA"
    _init_repo(proj)
    (proj / "README.md").write_text("hello", encoding="utf-8")  # dirty: 未提交
    (proj / "input").mkdir()
    (proj / "input" / "inbox.md").write_text("- [ ] 想法一\n- [ ] 想法二\n", encoding="utf-8")

    states = scan_projects(work_root, vault)
    assert [s.name for s in states] == ["ProjA"]  # _vault 被跳过
    s = states[0]
    assert s.is_git and s.dirty
    assert s.inbox_pending == 2
    assert s.next_step == "发布 v2"
    assert s.next_step_ref == "projects/ProjA.md#下一步"
    assert s.git_error is None
    # ADR 0023：有 active 档案 → registered，首页可见
    assert s.registered is True
    assert s.status == "active"


def test_scan_projects_classifies_new_and_archived_folders(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    (vault / "projects").mkdir(parents=True)
    # 未建档文件夹（新）与已归档档案
    (work_root / "BrandNew").mkdir(parents=True)
    (work_root / "Done").mkdir(parents=True)
    (vault / "projects" / "Done.md").write_text(
        "---\nproject: Done\ndate: 2026-09-01\ntype: project-main\nstatus: archived\n---\n"
        "## 当前状态\n收尾\n## 下一步\n\n## 阻塞\n无\n## 决策记录\n无\n",
        encoding="utf-8",
    )
    states = {s.name: s for s in scan_projects(work_root, vault)}
    assert states["BrandNew"].registered is False
    assert states["BrandNew"].status is None
    assert states["Done"].registered is True
    assert states["Done"].status == "archived"


def test_scan_projects_handles_non_git_dir(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    (work_root / "PlainDir").mkdir(parents=True)
    states = scan_projects(work_root, work_root / "_vault")
    assert states[0].is_git is False
    assert states[0].dirty is False


# —— 信号快照往返 ——


def test_snapshot_roundtrip_overwrites(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    write_snapshot(vault, "2026-09-01", {"actions": 3})
    write_snapshot(vault, "2026-09-01", {"actions": 5})  # 覆盖
    got = read_snapshot(vault, "2026-09-01")
    assert got is not None
    assert got["actions"] == 5
    # 快照顶层打上 schema_version，便于将来格式演进的兼容读。
    assert got["schema_version"] == 1
    assert read_snapshot(vault, "2026-08-31") is None


def _detail_snapshot(day: str) -> dict[str, object]:
    return {
        "date": day,
        "health": "ok",
        "tasks": 2,
        "meetings": 1,
        "actions": [
            {
                "signal_id": "task-guid-1",
                "title": "提交样章",
                "category": "commitment",
                "evidence": "E2",
                "source_ref": "feishu-task:guid-1",
                "project": None,
                "due_date": day,
                "detail": "",
            },
            {
                "signal_id": "stall-ProjA-dirty",
                "title": "提交改动",
                "category": "anti-stall",
                "evidence": "E2",
                "source_ref": "ProjA",
                "project": "ProjA",
                "due_date": None,
                "detail": "未提交",
            },
        ],
        "proposals": [],
        "completions": 0,
        "pending_review": 0,
        "meeting_list": [{"title": "例会", "start_time": "10:00"}],
        "task_list": [
            {"summary": "提交样章", "due_date": day, "task_id": "guid-1"},
            {"summary": "回邮件", "due_date": None, "task_id": "guid-2"},
        ],
        "completion_list": [],
        "proposal_list": [],
    }


def test_mark_task_completed_mirrors_snapshot(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    day = "2026-09-04"
    write_snapshot(vault, day, _detail_snapshot(day))

    summary = mark_task_completed(vault, day, "GUID-1")  # 大小写不敏感
    assert summary == "提交样章"

    snap = read_snapshot(vault, day)
    assert snap is not None
    # 待办移除该任务并同步计数；无关任务保留
    task_list = snap["task_list"]
    assert isinstance(task_list, list)
    assert [t.get("task_id") for t in task_list] == ["guid-2"]
    assert snap["tasks"] == 1
    # 关联它的行动候选一并移除，避免以「需要行动」重新出现；无关候选保留
    actions = snap["actions"]
    assert isinstance(actions, list)
    assert [a.get("signal_id") for a in actions] == ["stall-ProjA-dirty"]
    # 「最近完成」追加一条 E1 条目（与既有重复时不再追加）
    completions = snap["completion_list"]
    assert isinstance(completions, list)
    assert completions == [{"text": "提交样章", "source_ref": "feishu-task:GUID-1"}]
    assert snap["completions"] == 1
    # meetings / proposal 等其它区块不受影响
    assert snap["meetings"] == 1

    # 幂等：再次标记同一任务 → 快照不变（任务已不在待办）
    assert mark_task_completed(vault, day, "guid-1") is None
    assert read_snapshot(vault, day) == snap


def test_mark_task_completed_noop_when_task_absent_or_old_format(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    day = "2026-09-04"
    # 任务不在当日快照（如当日尚无简报）→ 不写盘
    write_snapshot(vault, day, _detail_snapshot(day))
    assert mark_task_completed(vault, day, "guid-99") is None
    untouched = read_snapshot(vault, day)
    assert untouched is not None
    task_list = untouched["task_list"]
    assert isinstance(task_list, list)
    assert [t.get("task_id") for t in task_list] == ["guid-1", "guid-2"]
    assert untouched["completion_list"] == []
    # 旧格式快照（无 *_list 明细）→ 无镜像目标、零写入
    write_snapshot(vault, day, {"date": day, "health": "ok", "tasks": 1, "actions": []})
    assert mark_task_completed(vault, day, "guid-1") is None


# —— daily 锚点幂等 ——


def test_write_brief_creates_note_with_frontmatter(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    path = write_brief(vault, "2026-09-01", "# 简报\n内容 A")
    text = path.read_text(encoding="utf-8")
    assert "type: daily" in text and "project: global" in text
    assert BRIEF_START in text and BRIEF_END in text
    assert "内容 A" in text


def test_write_brief_replaces_block_idempotently(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    write_brief(vault, "2026-09-01", "内容 A")
    path = write_brief(vault, "2026-09-01", "内容 B")
    text = path.read_text(encoding="utf-8")
    assert "内容 B" in text
    assert "内容 A" not in text
    assert text.count(BRIEF_START) == 1  # 不重复追加


def test_write_brief_preserves_user_content_outside_anchors(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    path = write_brief(vault, "2026-09-01", "内容 A")
    # 用户在锚点之外手写内容
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\n## 我的手记\n重要\n", encoding="utf-8")
    write_brief(vault, "2026-09-01", "内容 B")  # 再次生成
    final = path.read_text(encoding="utf-8")
    assert "我的手记" in final and "重要" in final
    assert "内容 B" in final and "内容 A" not in final
