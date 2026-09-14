"""统一的目录忽略规则：**点开头（隐藏 / 机器）+ 已知机器目录名 + 下划线内部前缀**。

承诺来源：2026-09-14 使用者反馈「App【项目】里出现 `.obsidian`」（真实位置
`~/Documents/Work/.obsidian`，与 `_vault` 并列）。根因是 `project_scan.is_internal_dirname`
只挡下划线前缀；而「哪些目录不算内容」当时散在三处各自维护名单
（``project_scan`` / ``vault`` / ``kb_index``）。

本用例覆盖**三处遍历**——App 项目列表、``wb vault check``、知识索引——
保证它们共用 `repositories/ignore.py` 的同一条判据。

变异验证（改坏了必须立刻红）：
- 让 `is_internal_dirname` 退回「只判下划线前缀」→ 第 1、2、3、4 组断言全红；
- 把 `templates` 从 `MACHINE_DIRNAMES` 移除 → 第 1、3 组断言变红；
- 把 `parts[:-1]` 改回 `parts`（按文件名判定）→ 第 5 组断言变红。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.repositories.ignore import (
    MACHINE_DIRNAMES,
    is_hidden_dirname,
    is_internal_dirname,
    is_machine_dirname,
)
from summit_workbench.repositories.kb_index import KnowledgeIndex
from summit_workbench.repositories.project_scan import (
    scan_all_projects,
    scan_projects,
    thread_projects,
)
from summit_workbench.repositories.vault import check_vault, iter_markdown_files


def test_is_internal_dirname_covers_hidden_machine_and_underscore() -> None:
    """判据本身：三种情形都算「不是内容」，普通项目名不算。"""
    # 下划线前缀（原有能力，不能退化）
    assert is_internal_dirname("_vault")
    assert is_internal_dirname("_transcripts-inbox")
    # 点开头 = 隐藏 / 机器目录（本轮修复的漏洞）
    assert is_internal_dirname(".obsidian")
    assert is_internal_dirname(".git")
    assert is_internal_dirname(".summit-workbench")
    assert is_hidden_dirname(".obsidian") and is_machine_dirname(".obsidian")
    # 无前缀机器目录名
    assert "templates" in MACHINE_DIRNAMES
    assert is_internal_dirname("templates")
    # 普通项目名不是内部目录（下划线不是前缀就不算）
    assert not is_internal_dirname("ProjA")
    assert not is_internal_dirname("HIC_Logistics")
    assert not is_internal_dirname("templates-lite")
    assert not is_internal_dirname("obsidian")


def test_scan_projects_skips_obsidian_and_machine_dirs(tmp_path: Path) -> None:
    """App【项目】列表：`Work/.obsidian` 与机器目录都不出现，真项目照旧出现。"""
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    (vault / "projects").mkdir(parents=True)
    # 真实布局的复刻：.obsidian 与 _vault 并列（2026-09-14 就是它漏出来的）
    for name in (".obsidian", ".git", "_vault", "_transcripts-inbox", "templates"):
        (work_root / name).mkdir(parents=True, exist_ok=True)
    for name in ("ProjA", "HIC_Logistics"):
        (work_root / name).mkdir(parents=True, exist_ok=True)

    names = [state.name for state in scan_projects(work_root, vault)]
    assert names == ["HIC_Logistics", "ProjA"]

    # 项目全集同样不把 .obsidian 当成「文件夹已覆盖」，vault 档案线程照旧可见
    (vault / "projects" / "hr.md").write_text(
        "---\nproject: hr\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        "updated: '2026-09-01'\n---\n# hr\n\n## 当前状态\n推进中\n## 下一步\n- 一步\n"
        "## 阻塞\n无\n## 决策记录\n",
        encoding="utf-8",
    )
    all_names = [state.name for state in scan_all_projects(work_root, vault)]
    assert all_names == ["HIC_Logistics", "ProjA", "hr"]
    assert [state.name for state in thread_projects(vault, work_root)] == ["hr"]


def test_vault_check_and_iter_skip_hidden_dirs(tmp_path: Path) -> None:
    """`wb vault check` 与 Markdown 遍历：`.obsidian/` 里的笔记不参与校验/双链。"""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "workspace.md").write_text(
        "---\ndate: {{date}}\ntype: note\nstatus: active\n---\n\n# 非法的机器文件\n",
        encoding="utf-8",
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "note-template.md").write_text(
        "---\ndate: {{date}}\ntype: note\nstatus: active\n---\n\n# {{title}}\n",
        encoding="utf-8",
    )
    real = tmp_path / "index" / "projects.md"
    real.parent.mkdir()
    real.write_text(
        "---\ndate: 2026-09-13\ntype: index\nstatus: active\nproject: global\n---\n\n# 项目索引\n",
        encoding="utf-8",
    )

    results = check_vault(tmp_path)
    assert results == {}
    files = list(iter_markdown_files(tmp_path))
    assert files == [real]


def test_kb_index_skips_hidden_dirs(tmp_path: Path) -> None:
    """知识索引：`.obsidian/` 里的 Markdown 不进索引（否则问答会召回机器文件）。"""
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "machine.md").write_text(
        "---\ndate: 2026-09-13\ntype: note\nstatus: active\n---\n\n# 机器文件\n\n独有标记词。\n",
        encoding="utf-8",
    )
    (vault / "hii").mkdir()
    (vault / "hii" / "real.md").write_text(
        "---\ndate: 2026-09-13\ntype: note\nstatus: active\nworkstream: hii\n---\n\n"
        "# 真笔记\n\n正文。\n",
        encoding="utf-8",
    )

    with KnowledgeIndex(vault_dir=vault, db_path=tmp_path / "kb.sqlite") as index:
        stats = index.build(full=True)
        assert stats.added == 1
        assert set(index.notes()) == {"hii/real"}


def test_iter_markdown_files_only_judges_directories(tmp_path: Path) -> None:
    """判据只作用于目录：名字带下划线/点开头的**文件**本身不是内部目录。"""
    (tmp_path / "sub").mkdir()
    dotted = tmp_path / ".top-note.md"
    dotted.write_text(
        "---\ndate: 2026-09-13\ntype: note\nstatus: active\nproject: global\n---\n\n# x\n",
        encoding="utf-8",
    )
    underscored = tmp_path / "sub" / "_note.md"
    underscored.write_text(
        "---\ndate: 2026-09-13\ntype: note\nstatus: active\nproject: global\n---\n\n# y\n",
        encoding="utf-8",
    )

    files = list(iter_markdown_files(tmp_path))
    assert set(files) == {dotted, underscored}
