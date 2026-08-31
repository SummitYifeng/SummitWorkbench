"""项目名（含自然语言别名）到规范项目 ID 的解析。

事实源是 ``_vault/projects/*.md``：每篇 ``project-main`` 笔记的 ``project`` frontmatter
是规范 ID，可选的 ``aliases: [...]`` 列出自然语言别名（如「网课系统」）。解析规则：

- 规范 ID 本身、笔记文件名、以及每个别名都能解析回该规范 ID（大小写/多余空白不敏感）；
- 解析不到时返回 ``None``，调用方据此维持「留在审批页标 error 等人工裁决」的安全行为，
  **绝不猜错目标、绝不自行造新项目名**（对齐 PRD L22）。

本层只读文件、建映射；不写盘、不生成 Markdown。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from summit_workbench.domain.review import UNRESOLVED
from summit_workbench.repositories.vault import load_note


def _normalize(name: str) -> str:
    """大小写折叠并压缩空白，得到用于匹配的稳定键。"""
    return " ".join(name.strip().casefold().split())


@dataclass(frozen=True)
class ProjectRegistry:
    """规范项目 ID 集合 + 别名映射；一次构建、多次解析。"""

    canonical: frozenset[str] = frozenset()
    alias_map: dict[str, str] = field(default_factory=dict)

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
    for path in sorted(projects_dir.glob("*.md")):
        note = load_note(path)
        if note.parse_error is not None or note.meta.get("type") != "project-main":
            continue
        project_id = note.meta.get("project")
        if not isinstance(project_id, str) or not project_id or project_id == "global":
            continue
        canonical.add(project_id)
        names = [project_id, path.stem]
        raw_aliases = note.meta.get("aliases")
        if isinstance(raw_aliases, list):
            names.extend(alias for alias in raw_aliases if isinstance(alias, str))
        for name in names:
            key = _normalize(name)
            if key:
                # 同名别名冲突时保留先出现的（按文件名排序，结果稳定）。
                alias_map.setdefault(key, project_id)
    return ProjectRegistry(frozenset(canonical), alias_map)
