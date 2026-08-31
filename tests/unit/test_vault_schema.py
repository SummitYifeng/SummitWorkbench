"""vault frontmatter / 固定区块校验规则测试。"""

from __future__ import annotations

from summit_workbench.domain.vault import validate_note

PROJECT_BODY = "## 当前状态\n## 下一步\n## 阻塞\n## 决策记录\n"


def _fields(issues):
    return {i.field for i in issues}


def test_valid_project_main_passes():
    meta = {
        "project": "HIC_SWB_LaTEX",
        "date": "2026-08-30",
        "type": "project-main",
        "status": "active",
    }
    assert validate_note(meta, PROJECT_BODY) == []


def test_missing_required_fields():
    issues = validate_note({}, "")
    assert {"date", "type", "status"} <= _fields(issues)


def test_bad_date_format():
    meta = {"project": "P", "date": "2026/08/30", "type": "project-main", "status": "active"}
    assert "date" in _fields(validate_note(meta, PROJECT_BODY))


def test_unknown_status():
    meta = {"project": "P", "date": "2026-08-30", "type": "project-main", "status": "weird"}
    assert "status" in _fields(validate_note(meta, PROJECT_BODY))


def test_unknown_type_short_circuits():
    meta = {"date": "2026-08-30", "type": "nope", "status": "active"}
    issues = validate_note(meta, "")
    assert "type" in _fields(issues)


def test_single_scope_requires_project_not_projects():
    meta = {"projects": ["A"], "date": "2026-08-30", "type": "project-main", "status": "active"}
    fields = _fields(validate_note(meta, PROJECT_BODY))
    assert "project" in fields and "projects" in fields


def test_single_scope_project_cannot_be_global():
    meta = {"project": "global", "date": "2026-08-30", "type": "project-main", "status": "active"}
    assert "project" in _fields(validate_note(meta, PROJECT_BODY))


def test_multi_scope_meeting_note_requires_projects():
    body = "\n".join(
        [
            "## 一分钟摘要",
            "## 会议信息",
            "## 事实与进展",
            "## 已形成决策",
            "## 明确行动项",
            "## 未决问题",
            "## AI 建议",
            "## 关联项目",
            "## 证据索引",
        ]
    )
    ok = {
        "projects": ["A", "B"],
        "date": "2026-08-30",
        "type": "meeting-note",
        "status": "pending-review",
    }
    assert validate_note(ok, body) == []
    bad = {"project": "A", "date": "2026-08-30", "type": "meeting-note", "status": "pending-review"}
    fields = _fields(validate_note(bad, body))
    assert "project" in fields and "projects" in fields


def test_global_scope_requires_project_global():
    ok = {"project": "global", "date": "2026-08-30", "type": "inbox", "status": "active"}
    assert validate_note(ok, "") == []
    bad = {"project": "SomeProj", "date": "2026-08-30", "type": "inbox", "status": "active"}
    assert "project" in _fields(validate_note(bad, ""))


def test_project_main_missing_fixed_block():
    meta = {"project": "P", "date": "2026-08-30", "type": "project-main", "status": "active"}
    issues = validate_note(meta, "## 当前状态\n## 下一步\n")  # 缺 阻塞 / 决策记录
    msgs = " ".join(str(i) for i in issues)
    assert "阻塞" in msgs and "决策记录" in msgs
