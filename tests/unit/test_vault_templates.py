"""库内模板与 schema 的一致性护栏。

模板是「人写笔记的起点」，如果模板 frontmatter 与 `domain.vault` 的词表/scope 漂移，
所有新笔记都会一开始就过不了 `wb vault check`。本文件把模板渲染一次再送进 `validate_note`，
把这种漂移变成可判定的失败（变异验证：在任一模板里把 `type:` 改错，本文件必须变红）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.vault import parse_frontmatter
from summit_workbench.workflows.onboarding import default_vault_templates_dir

DAY = "2026-09-13"

# 新增的模板（既有 6 个不在本用例范围内，避免把旧行为绑死）。
NEW_TEMPLATES = (
    "workstream.template.md",
    "note.template.md",
    "decision.template.md",
    "source.template.md",
    "index.template.md",
    "long-form-thought.template.md",
    "work-log.template.md",
)


def _render(text: str) -> str:
    return (
        text.replace("{{date}}", DAY)
        .replace("{{title}}", "样例标题")
        .replace("{{project}}", "demo-project")
    )


@pytest.mark.parametrize("name", NEW_TEMPLATES)
def test_new_template_renders_to_a_valid_note(name: str) -> None:
    path = default_vault_templates_dir() / name
    assert path.is_file(), f"缺少模板 {name}"
    meta, body, error = parse_frontmatter(_render(path.read_text(encoding="utf-8")))
    assert error is None, (name, error)
    issues = validate_note(meta, body)
    assert issues == [], (name, [str(i) for i in issues])


@pytest.mark.parametrize("name", NEW_TEMPLATES)
def test_new_template_keeps_placeholder_project_optional(name: str) -> None:
    """模板不得硬编码项目绑定，否则 `free` scope 的笔记会被迫挂到某个项目上。

    `global` scope 的模板（workstream / index）按 schema 必须写 `project: global`；
    `multi` scope 的 work-log 必须写 `projects: [...]`（那是它的正确形态，不是硬编码项目）。
    """
    from summit_workbench.domain.vault import NOTE_TYPES

    text = (default_vault_templates_dir() / name).read_text(encoding="utf-8")
    meta, _, _ = parse_frontmatter(_render(text))
    scope = NOTE_TYPES[str(meta["type"])].scope

    frontmatter = text.split("---", 2)[1]
    bindings = [
        line.strip()
        for line in frontmatter.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if scope == "free":
        assert not any(line.startswith(("project: ", "projects: [")) for line in bindings), name
    elif scope == "global":
        assert "project: global" in bindings, name
    else:  # multi
        assert any(line.startswith("projects: [") for line in bindings), name


def test_templates_dir_is_not_shipped_into_new_workspace_allowlist() -> None:
    """新模板只是**参考骨架**，不得顺手扩开 onboarding 的种子 allowlist。

    扩 allowlist 会改变「新建 workspace」的产物，属于契约级行为变化；本轮刻意不做。
    """
    from summit_workbench.workflows.onboarding import TEMPLATE_TARGETS

    assert TEMPLATE_TARGETS == {
        "inbox.template.md": "inbox.md",
        "conventions.template.md": "conventions.md",
    }


def test_repo_has_no_stray_untracked_template() -> None:
    """模板目录里不应出现不在清单里的 md（防止有人加了模板却忘了接进校验）。"""
    names = {p.name for p in Path(default_vault_templates_dir()).glob("*.template.md")}
    legacy = {
        "project-main.template.md",
        "meeting-transcript.template.md",
        "inbox.template.md",
        "meeting-note.template.md",
        "review-meetings.template.md",
        "conventions.template.md",
    }
    assert names == set(NEW_TEMPLATES) | legacy, names
