"""项目绑定（``project`` / ``projects``）里**未替换占位符**的校验。

**这条守卫解决什么**（2026-09-14）：模板 frontmatter 里的 ``{{project}}`` 若忘了替换，
页面会**静默绑到一个不存在的项目**，而此前 ``wb vault check`` 完全不看 ``project``，
坏值照样通过。现在占位符会被明确拒掉并给出可执行提示。

**为什么只查占位符，不查字符集（一次判据纠错的记录）**：第一版把「项目 ID 只允许
``[A-Za-z0-9_-]``」也加进了 schema 校验，结果 ``test_review_candidates.py`` 两条既有测试立刻变红——
会议提取管线里模型给出的 ``projects:`` 允许是**自然语言项目名**（如 ``网课系统``），
之后才按别名解析成规范 ID、解析不到则落 ``unresolved`` → 全局收件箱。
即 ``meeting-note`` / ``meeting-transcript`` 的 ``projects:`` 是**线索**而非最终绑定，
在 schema 层按字符集判定会**打断会议导入**。⇒ 字符集约束保留在「创建项目时 + 文档约定」，
schema 层只拦**一定错**的占位符。下面的
``test_allows_natural_language_project_from_meeting_pipeline`` 就是把这个产品行为钉住。

**变异验证**：删掉 ``validate_note`` 里的 ``issues.extend(_check_project_placeholders(meta))``，
本文件的占位符用例必须立刻变红。
"""

from __future__ import annotations

import pytest

from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.vault import parse_frontmatter

_HEAD = """date: 2026-09-14
type: {note_type}
status: active
{project_lines}
"""


# `meeting-note` 是 app 强制九区块的类型：测试页必须写全，否则会因缺区块而失败，
# 从而掩盖我们真正要断言的项目绑定规则（第一版就踩了：三条用例因缺区块而红）。
_MEETING_NOTE_BODY = (
    "# 测试\n\n"
    + "\n\n".join(
        f"## {block}\nx"
        for block in (
            "一分钟摘要",
            "会议信息",
            "事实与进展",
            "已形成决策",
            "明确行动项",
            "未决问题",
            "AI 建议",
            "关联项目",
            "证据索引",
        )
    )
    + "\n"
)


def _validate(note_type: str, project_lines: str) -> list[str]:
    body = _MEETING_NOTE_BODY if note_type == "meeting-note" else "# 测试\n"
    head = _HEAD.format(note_type=note_type, project_lines=project_lines)
    text = "---\n" + head + "---\n\n" + body
    meta, body, error = parse_frontmatter(text)
    assert error is None, error
    return [str(issue) for issue in validate_note(meta, body)]


@pytest.mark.parametrize(
    "project_lines",
    [
        'project: "{{project}}"',
        'project: "{{ 项目 }}"',
        'project: "{{project"',  # 只留左括号也算记号
        'projects: ["{{project}}"]',
        'projects: [hr, "{{project-a}}"]',
    ],
)
def test_rejects_unreplaced_placeholders(project_lines: str) -> None:
    """未替换的占位符必须被判为错误——这正是此前静默通过的那一类。"""
    issues = _validate("note" if "projects" not in project_lines else "work-log", project_lines)
    assert issues and any("占位符" in message for message in issues), issues


def test_placeholder_error_is_actionable() -> None:
    """提示要告诉人**怎么改**，而不是只说"格式错误"。"""
    issues = _validate("note", 'project: "{{project}}"')
    assert any("真实项目 ID" in message for message in issues), issues


def test_placeholder_is_rejected_for_pipeline_types_too() -> None:
    """占位符在会议类页面上同样必须被拒（它们由管线生成，出现占位符说明模板/管线出了问题）。"""
    issues = _validate("meeting-note", 'projects: ["{{project}}"]')
    assert any("占位符" in message for message in issues), issues


@pytest.mark.parametrize(
    "project_id",
    [
        "hii-affairs",
        "it-development",
        "huoman-community",
        "huoman-logistics",
        "hr",
        "global",
        "A_1-b",
    ],
)
def test_accepts_legal_project_ids(project_id: str) -> None:
    """本库 5 个项目 ID、``global``、以及下划线/连字符/数字都不得报错。"""
    assert _validate("note", f"project: {project_id}") == []


@pytest.mark.parametrize("natural_name", ["网课系统", "某个还没建的项目", "HIC 网课"])
def test_allows_natural_language_project_from_meeting_pipeline(natural_name: str) -> None:
    """**产品行为，不要在 schema 层收紧**：会议提取允许项目名是自然语言，稍后才解析成规范 ID。

    ``repositories/review_candidates.py`` 会把无法解析的值判为 ``unresolved`` 并落全局收件箱，
    所以这里放行是**有意**的；如果哪天要收紧，必须同时改会议导入管线与它的测试。
    """
    quoted = f'"{natural_name}"'
    assert _validate("meeting-note", f"projects: [{quoted}]") == []


def test_scope_and_placeholder_errors_can_coexist() -> None:
    """占位符错误不应掩盖 scope 错误（两者是独立规则）。"""
    issues = _validate("project-main", 'projects: ["{{project}}"]')
    assert any("单项目笔记" in message for message in issues)  # scope
    assert any("占位符" in message for message in issues)  # 占位符
