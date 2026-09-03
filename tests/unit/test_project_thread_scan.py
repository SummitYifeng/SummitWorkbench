"""知识线程项目：内部目录不进项目视野；vault 档案全集含无文件夹线程。

覆盖 P0 需求再梳理结论：
- 下划线前缀目录（_vault / _transcripts-inbox 等）一律不扫描、不提示「加入工作台」；
- 已建档但 Work 目录无同名文件夹的 project-main 档案 = 知识线程项目，与仓库项目
  在「项目全集」中共存（项目页 / 审批目标项目下拉 / 首页推进卡的数据源）。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.repositories.project_scan import (
    is_internal_dirname,
    scan_all_projects,
    scan_projects,
    thread_projects,
)


def _write_project_main(
    vault: Path, project: str, *, status: str = "active", updated: str = "2026-09-01"
) -> Path:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-08-31\ntype: project-main\nstatus: {status}\n"
        f"updated: '{updated}'\n---\n"
        f"# {project}\n\n## 当前状态\n推进中\n## 下一步\n- 下一步动作\n## 阻塞\n无\n"
        f"## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    return path


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)


def test_is_internal_dirname_underscore_prefix() -> None:
    assert is_internal_dirname("_vault")
    assert is_internal_dirname("_transcripts-inbox")
    assert not is_internal_dirname("ProjA")
    assert not is_internal_dirname("HIC_Logistics")  # 项目名可含下划线，但前缀不是下划线


def test_scan_projects_skips_all_internal_dirs(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    (vault / "projects").mkdir(parents=True)
    (work_root / "ProjA").mkdir(parents=True)
    (work_root / "_transcripts-inbox").mkdir(parents=True)
    (work_root / "_other-internal").mkdir(parents=True)

    names = [s.name for s in scan_projects(work_root, vault)]
    assert names == ["ProjA"]
    # scan_all 也不包含内部目录
    assert [s.name for s in scan_all_projects(work_root, vault)] == ["ProjA"]


def test_thread_projects_lists_folderless_registered_archives(tmp_path: Path) -> None:
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    # 仓库项目：文件夹 + 同名档案
    _write_project_main(vault, "ProjA")
    _init_repo(work_root / "ProjA")
    # 知识线程：只有档案，没有文件夹
    _write_project_main(vault, "finance_ops", status="active", updated="2026-09-03")

    threads = thread_projects(vault, work_root)
    assert [t.name for t in threads] == ["finance_ops"]
    t = threads[0]
    assert t.is_thread is True
    assert t.registered is True
    assert t.status == "active"
    assert t.next_step == "下一步动作"
    assert t.updated == "2026-09-03"
    assert t.is_git is False

    all_projects = {s.name: s for s in scan_all_projects(work_root, vault)}
    assert set(all_projects) == {"ProjA", "finance_ops"}
    assert all_projects["ProjA"].is_thread is False
    assert all_projects["finance_ops"].is_thread is True
    # 知识线程档案路径 = vault 档案本身（无 Work 文件夹）
    assert all_projects["finance_ops"].path == vault / "projects" / "finance_ops.md"


def test_thread_projects_excludes_archived_folders_and_archived_threads_still_listed(
    tmp_path: Path,
) -> None:
    """归档语义对线程同样生效：archived 线程仍在「项目全集」（可恢复），只是不在首页。"""
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    _write_project_main(vault, "DoneThread", status="archived")
    names = [t.name for t in thread_projects(vault, work_root)]
    assert names == ["DoneThread"]
    all_projects = {s.name: s for s in scan_all_projects(work_root, vault)}
    assert all_projects["DoneThread"].status == "archived"


def test_thread_projects_normalizes_unquoted_updated_date(tmp_path: Path) -> None:
    """档案 frontmatter 的 updated 未加引号时 YAML 解析成 date 对象，扫描应归一到字符串。"""
    work_root = tmp_path / "Work"
    vault = work_root / "_vault"
    path = vault / "projects" / "rawdate.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nproject: rawdate\ndate: 2026-08-31\ntype: project-main\nstatus: active\n"
        "updated: 2026-09-03\n---\n"
        "# rawdate\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n无\n\n## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    thread = thread_projects(vault, work_root)[0]
    assert thread.name == "rawdate"
    assert thread.updated == "2026-09-03"
