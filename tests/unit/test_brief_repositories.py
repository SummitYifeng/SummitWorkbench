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
