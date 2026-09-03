"""本地项目状态采集（M2-2）：git 状态 + 项目 inbox 待处理数 + 主笔记「下一步」。

**离线**：只读本地 git ref（``status --porcelain`` 与 ``rev-list @{u}...HEAD``），**不联网 fetch**，
以满足简报 P95≤5s 的时延预算（联网同步由 ``wb sync`` 单独负责）。任何 git 失败都转成可见的
``git_error`` 字段（NFR-6），绝不抛出中断整份简报。

事实区硬约束：git 状态、inbox 计数、「下一步」文本均原样取自文件系统，不经模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.vault import load_note, meta_date_iso

# 下划线前缀目录 = 系统内部目录（vault、落料夹等），一律不进「项目」视野：
# 不扫描、不提示「加入工作台」、不允许激活/归档操作。
_VAULT_DIRNAME = "_vault"
_INTERNAL_PREFIX = "_"


def is_internal_dirname(name: str) -> bool:
    """是否为系统内部目录名（下划线前缀，如 ``_vault`` / ``_transcripts-inbox``）。"""
    return name.startswith(_INTERNAL_PREFIX)


@dataclass(frozen=True)
class ProjectState:
    """单个工作项目的离线状态快照。"""

    name: str
    path: Path
    is_git: bool
    dirty: bool
    ahead: int
    behind: int
    has_upstream: bool
    inbox_pending: int
    next_step: str | None
    next_step_ref: str | None
    git_error: str | None = None
    # ADR 0023：是否已建档（有效 project-main 档案）及其 status——
    # active = 在工作台（首页显示）；archived = 已归档；None/未建档 = 新文件夹。
    registered: bool = False
    status: str | None = None
    # 知识线程项目（无 Work 文件夹、纯 vault 档案）标记；仓库项目为 False。
    is_thread: bool = False
    # 档案 frontmatter 的 updated（实质更新：建档/激活/归档/改名/状态确认，YYYY-MM-DD）。
    # 停滞点名与「>14 天未更新」读它——日志/产物等机器活动不再刷新它（P1 语义拆分）。
    updated: str | None = None
    # 档案 frontmatter 的 activity_at（活动痕迹：日志/产物入库等，YYYY-MM-DD，可缺省）。
    # 首页「最近活跃」展示用，不代表实质状态更新。
    activity_at: str | None = None
    # 显示名（frontmatter `title`，可选）：UI 展示用，不影响规范 ID/别名解析与文件夹名。
    title: str | None = None


def count_inbox_pending(text: str) -> int:
    """统计 inbox 待处理条目数：以 ``- [ ] `` 开头的行（PRD 3.1.7 定义）。"""
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("- [ ] "))


def extract_next_step(body: str) -> str | None:
    """从项目主笔记正文取 ``## 下一步`` 区块下的第一条**实质**内容行。

    去掉列表符号/复选框前缀；跳过 HTML 注释占位（``<!-- ... -->``，模板未填时的占位行），
    避免把模板占位当成真实下一步。区块为空/只有占位/不存在时返回 None，区块以下一个 ``## `` 结束。
    """
    lines = body.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip() == "下一步"
            continue
        if in_section and stripped:
            if stripped.startswith("<!--"):
                continue  # 模板占位，非实质内容
            # 去掉 "- [ ] " / "- [x] " / "- " / "* " 前缀
            text = stripped
            for prefix in ("- [ ] ", "- [x] ", "- ", "* "):
                if text.startswith(prefix):
                    text = text[len(prefix) :]
                    break
            return text.strip() or None
    return None


def _project_inbox_pending(project_path: Path) -> int:
    """项目内 inbox 待处理数。兼容 ``input/inbox.md`` 与根 ``inbox.md`` 两种落点。"""
    for candidate in (project_path / "input" / "inbox.md", project_path / "inbox.md"):
        if candidate.is_file():
            return count_inbox_pending(candidate.read_text(encoding="utf-8"))
    return 0


def _project_registry_state(
    vault_dir: Path, name: str
) -> tuple[bool, str | None, str | None, str | None, str | None, str | None, str | None]:
    """一次读取项目档案，返回 ``(registered, status, next_step, next_step_ref, updated, title,
    activity_at)``。

    档案口径与 ``project_registry`` 一致（ADR 0023）：``_vault/projects/<name>.md``
    存在、无解析错误、``type: project-main`` 才算已建档（registered=False）；否则一律视为
    「新文件夹」。「下一步」只从有效档案正文取；``updated`` / ``title`` / ``activity_at`` 取
    档案 frontmatter（无则 None；日期字段兼容 YAML 未加引号的 date 对象形态）。
    """
    note_path = vault_dir / "projects" / f"{name}.md"
    if not note_path.is_file():
        return False, None, None, None, None, None, None
    note = load_note(note_path)
    if note.parse_error is not None or note.meta.get("type") != "project-main":
        return False, None, None, None, None, None, None
    status = note.meta.get("status")
    step = extract_next_step(note.body)
    ref = f"projects/{name}.md#下一步" if step else None
    updated = meta_date_iso(note.meta.get("updated"))
    title_raw = note.meta.get("title")
    title = title_raw if isinstance(title_raw, str) and title_raw else None
    activity_at = meta_date_iso(note.meta.get("activity_at"))
    return (
        True,
        status if isinstance(status, str) else None,
        step,
        ref,
        updated,
        title,
        activity_at,
    )


def _git_state(path: Path) -> tuple[bool, bool, int, int, bool, str | None]:
    """返回 (is_git, dirty, ahead, behind, has_upstream, git_error)，纯本地、不联网。"""
    repo = GitRepo(path)
    if not repo.is_git_repo():
        return False, False, 0, 0, False, None
    try:
        dirty = repo.is_dirty()
        has_upstream = repo.has_upstream()
        if has_upstream:
            ab = repo.ahead_behind()
            return True, dirty, ab.ahead, ab.behind, True, None
        return True, dirty, 0, 0, False, None
    except GitError as exc:
        return True, False, 0, 0, False, exc.stderr or str(exc)


def scan_project(path: Path, vault_dir: Path) -> ProjectState:
    """采集单个项目目录的离线状态。"""
    name = path.name
    is_git, dirty, ahead, behind, has_upstream, git_error = _git_state(path)
    (
        registered,
        status,
        next_step,
        next_step_ref,
        updated,
        title,
        activity_at,
    ) = _project_registry_state(vault_dir, name)
    return ProjectState(
        name=name,
        path=path,
        is_git=is_git,
        dirty=dirty,
        ahead=ahead,
        behind=behind,
        has_upstream=has_upstream,
        inbox_pending=_project_inbox_pending(path),
        next_step=next_step,
        next_step_ref=next_step_ref,
        git_error=git_error,
        registered=registered,
        status=status,
        is_thread=False,
        updated=updated,
        title=title,
        activity_at=activity_at,
    )


def scan_projects(work_root: Path, vault_dir: Path) -> list[ProjectState]:
    """扫描 ``work_root`` 下的直接子目录项目（跳过内部目录），按名排序。"""
    if not work_root.is_dir():
        return []
    projects = sorted(
        (p for p in work_root.iterdir() if p.is_dir() and not is_internal_dirname(p.name)),
        key=lambda p: p.name,
    )
    return [scan_project(p, vault_dir) for p in projects]


def thread_projects(vault_dir: Path, work_root: Path) -> list[ProjectState]:
    """列出「知识线程项目」：已建档但 Work 目录下没有同名文件夹的档案。

    知识线程（需求再梳理结论 R2-A+）：业务线程 = vault 内一等公民档案，不依赖 Work 目录
    文件夹与 git 仓库；数据源即 ``_vault/projects/*.md`` 中的有效 project-main 档案全集减去
    已由文件夹扫描覆盖的名字。
    """
    registry = load_project_registry(vault_dir)
    folder_names = (
        {p.name for p in work_root.iterdir() if p.is_dir() and not is_internal_dirname(p.name)}
        if work_root.is_dir()
        else set()
    )
    threads: list[ProjectState] = []
    for project_id in sorted(registry.canonical):
        if project_id in folder_names or is_internal_dirname(project_id):
            continue
        (
            registered,
            status,
            next_step,
            next_step_ref,
            updated,
            title,
            activity_at,
        ) = _project_registry_state(vault_dir, project_id)
        if not registered:
            continue
        threads.append(
            ProjectState(
                name=project_id,
                path=vault_dir / "projects" / f"{project_id}.md",
                is_git=False,
                dirty=False,
                ahead=0,
                behind=0,
                has_upstream=False,
                inbox_pending=0,
                next_step=next_step,
                next_step_ref=next_step_ref,
                registered=True,
                status=status,
                is_thread=True,
                updated=updated,
                title=title,
                activity_at=activity_at,
            )
        )
    return threads


def scan_all_projects(work_root: Path, vault_dir: Path) -> list[ProjectState]:
    """工作台项目全集：仓库项目（文件夹扫描）+ 知识线程项目（vault 档案），按名排序。"""
    if not work_root.is_dir():
        return thread_projects(vault_dir, work_root)
    merged = {p.name: p for p in scan_projects(work_root, vault_dir)}
    for thread in thread_projects(vault_dir, work_root):
        merged.setdefault(thread.name, thread)
    return [merged[name] for name in sorted(merged)]
