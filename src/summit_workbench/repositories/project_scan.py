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
from summit_workbench.repositories.vault import load_note

# work vault 自身不是「工作项目」，项目扫描应跳过它。
_VAULT_DIRNAME = "_vault"


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


def count_inbox_pending(text: str) -> int:
    """统计 inbox 待处理条目数：以 ``- [ ] `` 开头的行（PRD 3.1.7 定义）。"""
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("- [ ] "))


def extract_next_step(body: str) -> str | None:
    """从项目主笔记正文取 ``## 下一步`` 区块下的第一条非空内容行。

    去掉列表符号/复选框前缀；区块为空或不存在时返回 None。区块以下一个 ``## `` 结束。
    """
    lines = body.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip() == "下一步"
            continue
        if in_section and stripped:
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


def _next_step_for(vault_dir: Path, name: str) -> tuple[str | None, str | None]:
    """从 ``_vault/projects/<name>.md`` 主笔记取「下一步」及其来源引用。"""
    note_path = vault_dir / "projects" / f"{name}.md"
    if not note_path.is_file():
        return None, None
    note = load_note(note_path)
    if note.parse_error is not None:
        return None, None
    step = extract_next_step(note.body)
    ref = f"projects/{name}.md#下一步" if step else None
    return step, ref


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
    next_step, next_step_ref = _next_step_for(vault_dir, name)
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
    )


def scan_projects(work_root: Path, vault_dir: Path) -> list[ProjectState]:
    """扫描 ``work_root`` 下的直接子目录项目（跳过 ``_vault``），按名排序。"""
    if not work_root.is_dir():
        return []
    projects = sorted(
        (p for p in work_root.iterdir() if p.is_dir() and p.name != _VAULT_DIRNAME),
        key=lambda p: p.name,
    )
    return [scan_project(p, vault_dir) for p in projects]
