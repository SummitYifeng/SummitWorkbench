"""项目名（含自然语言别名）到规范项目 ID 的解析，以及项目主笔记的创建。

事实源是 ``_vault/projects/*.md``：每篇 ``project-main`` 笔记的 ``project`` frontmatter
是规范 ID，可选的 ``aliases: [...]`` 列出自然语言别名（如「网课系统」）。解析规则：

- 规范 ID 本身、笔记文件名、以及每个别名都能解析回该规范 ID（大小写/多余空白不敏感）；
- 解析不到时返回 ``None``。真实场景里多数会议未必对应已建项目：解析不到的候选会路由到
  全局 inbox 兜底捕获（见 :mod:`summit_workbench.domain.review`），而随着 workbench
  逐步梳理出新项目，用 :func:`create_project_note` 建档后即可被后续会议解析命中。

工作台精选语义（ADR 0023）：同一份 ``project-main`` 档案的 ``status`` 还驱动 Web 工作台
首页的「项目推进」显示——``active`` = 在工作台上；``archived`` = 已归档（不在首页但可在
「全部项目」页恢复）。本模块提供幂等的建档/激活/归档助手供 Web 端点与 CLI 共用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.review import UNRESOLVED
from summit_workbench.domain.vault import NOTE_TYPES, PROJECT_ID_RE
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.note_status import update_note_status
from summit_workbench.repositories.vault import load_note

# 规范项目 ID 的安全字符集：字母数字、下划线、连字符（用作文件名，禁空白/路径分隔符）。
# 项目 ID 字符集复用 schema 层的唯一真源（2026-09-14 起 `wb vault check` 也用它校验手写页面）。

# 档案目录名：_vault/projects/。
_PROJECTS_DIRNAME = "projects"


def _normalize(name: str) -> str:
    """大小写折叠并压缩空白，得到用于匹配的稳定键。"""
    return " ".join(name.strip().casefold().split())


@dataclass(frozen=True)
class ProjectRegistry:
    """规范项目 ID 集合 + 别名映射；一次构建、多次解析。"""

    canonical: frozenset[str] = frozenset()
    alias_map: dict[str, str] = field(default_factory=dict)
    aliases_by_project: dict[str, list[str]] = field(default_factory=dict)

    def resolve(self, name: str | None) -> str | None:
        """把项目名/别名解析为规范 ID。

        输入为空、为占位 ``unresolved``、或无法匹配任何已知项目时返回 ``None``。
        """
        if not name:
            return None
        key = _normalize(name)
        if not key or key == _normalize(UNRESOLVED):
            return None
        return self.alias_map.get(key)


def load_project_registry(vault_dir: Path) -> ProjectRegistry:
    """扫描 ``vault_dir/projects/*.md`` 建立解析器；无目录时返回空解析器。"""
    projects_dir = vault_dir / "projects"
    if not projects_dir.is_dir():
        return ProjectRegistry()
    canonical: set[str] = set()
    alias_map: dict[str, str] = {}
    aliases_by_project: dict[str, list[str]] = {}
    for path in sorted(projects_dir.glob("*.md")):
        note = load_note(path)
        if note.parse_error is not None or note.meta.get("type") != "project-main":
            continue
        project_id = note.meta.get("project")
        if not isinstance(project_id, str) or not project_id or project_id == "global":
            continue
        canonical.add(project_id)
        raw_aliases = note.meta.get("aliases")
        human_aliases = (
            [alias for alias in raw_aliases if isinstance(alias, str)]
            if isinstance(raw_aliases, list)
            else []
        )
        aliases_by_project[project_id] = human_aliases
        for name in [project_id, path.stem, *human_aliases]:
            key = _normalize(name)
            if key:
                # 同名别名冲突时保留先出现的（按文件名排序，结果稳定）。
                alias_map.setdefault(key, project_id)
    return ProjectRegistry(frozenset(canonical), alias_map, aliases_by_project)


def create_project_note(
    vault_dir: Path,
    project_id: str,
    *,
    aliases: list[str] | None = None,
    now: datetime | None = None,
) -> Path:
    """在 ``_vault/projects/`` 新建一篇符合 schema 的 project-main 笔记。

    只建第二大脑侧的项目档案（不碰任何 GitHub 仓库）。已存在则报错，避免覆盖历史。
    """
    if not PROJECT_ID_RE.match(project_id):
        raise ValueError(
            f"非法项目 ID {project_id!r}：只允许字母、数字、下划线和连字符（用作文件名）"
        )
    # 建档 = 检查存在 + 落盘：整体持锁避免并发建档竞态（重复建档/互相覆盖），落盘用原子写。
    with workspace_lock(vault_dir.parent):
        path = vault_dir / "projects" / f"{project_id}.md"
        if path.exists():
            raise FileExistsError(f"项目已存在：{path}")
        day = (now or datetime.now(UTC)).date().isoformat()
        clean_aliases = [alias.strip() for alias in (aliases or []) if alias.strip()]
        alias_line = f"aliases: [{', '.join(clean_aliases)}]\n" if clean_aliases else ""
        blocks = (*NOTE_TYPES["project-main"].required_blocks, "## 跟进事项")
        frontmatter = (
            f"---\nproject: {project_id}\ndate: {day}\ntype: project-main\n"
            f"status: active\nupdated: {day}\n{alias_line}---\n"
        )
        body = f"\n# {project_id}\n\n" + "\n\n".join(blocks) + "\n"
        atomic_write_text(path, frontmatter + body, ensure_parents=True)
        return path


def project_note_path(vault_dir: Path, project_id: str) -> Path:
    """``_vault/projects/<project_id>.md`` 的路径（不保证存在）。"""
    return vault_dir / _PROJECTS_DIRNAME / f"{project_id}.md"


def read_project_registration(vault_dir: Path, project_id: str) -> tuple[bool, str | None]:
    """读取一个项目的档案状态，返回 ``(registered, status)``。

    - ``registered``：``_vault/projects/<id>.md`` 存在且是**有效 project-main 档案**
      （与 :func:`load_project_registry` 同一过滤口径：无解析错误、``type: project-main``）；
    - ``status``：档案 frontmatter 的 ``status``（合法时），无档案/档案无效时为 ``None``。
    """
    path = project_note_path(vault_dir, project_id)
    if not path.is_file():
        return False, None
    note = load_note(path)
    if note.parse_error is not None or note.meta.get("type") != "project-main":
        return False, None
    status = note.meta.get("status")
    return True, status if isinstance(status, str) else None


def _set_status(vault_dir: Path, project_id: str, status: str, now: datetime | None) -> Path:
    """把已有档案的 status 与 updated 一并改写（保留正文，原子写）。"""
    path = project_note_path(vault_dir, project_id)
    day = (now or datetime.now(UTC)).date().isoformat()
    update_note_status(vault_dir, path, status, extra={"updated": day})
    return path


def ensure_project_active(vault_dir: Path, project_id: str, *, now: datetime | None = None) -> Path:
    """把项目置为「在工作台」（幂等）：无档案则建档（active），archived 则改回 active。

    - 同名文件存在但不是有效 project-main 档案时抛 :class:`ValueError`（不覆盖、不臆造）；
    - 已 active 时 no-op（不改文件，不刷新 updated）。
    """
    with workspace_lock(vault_dir.parent):
        path = project_note_path(vault_dir, project_id)
        if path.is_file():
            registered, status = read_project_registration(vault_dir, project_id)
            if not registered:
                raise ValueError(f"{project_id} 已有同名文件但不是有效项目笔记：{path}")
            if status == "active":
                return path
            return _set_status(vault_dir, project_id, "active", now)
        return create_project_note(vault_dir, project_id, now=now)


def archive_project(vault_dir: Path, project_id: str, *, now: datetime | None = None) -> Path:
    """把项目归档（幂等）：置 ``status: archived``，不在首页显示；可随时恢复。

    未建档的项目也会建一份档案再归档（处置「新文件夹」时落盘可循、不再重复提示）；
    同名文件存在但不是有效 project-main 档案时抛 :class:`ValueError`。
    """
    with workspace_lock(vault_dir.parent):
        path = project_note_path(vault_dir, project_id)
        if path.is_file():
            registered, status = read_project_registration(vault_dir, project_id)
            if not registered:
                raise ValueError(f"{project_id} 已有同名文件但不是有效项目笔记：{path}")
            if status == "archived":
                return path
            return _set_status(vault_dir, project_id, "archived", now)
        create_project_note(vault_dir, project_id, now=now)
        return _set_status(vault_dir, project_id, "archived", now)
