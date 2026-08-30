"""路径解析。

硬约束（NFR-3）：禁止硬编码 ``/Users/<name>/``，一律基于 ``$HOME`` 或
``WORK_ROOT`` 环境变量派生。所有派生路径集中在此，方便未来 Mac Air 接入。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def home_dir() -> Path:
    """当前用户 home 目录，绝不硬编码用户名。"""
    return Path.home()


def resolve_work_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """解析工作项目根目录 ``~/Documents/Work``（L9）。

    优先级：显式参数 > 环境变量 ``WORK_ROOT`` > 默认 ``$HOME/Documents/Work``。
    返回 ``expanduser`` 展开后的路径，但不要求其已存在（M0-1 不创建目录）。
    """
    candidate = explicit or os.environ.get("WORK_ROOT")
    if candidate:
        return Path(candidate).expanduser()
    return home_dir() / "Documents" / "Work"


@dataclass(frozen=True)
class WorkPaths:
    """从工作根目录派生的稳定路径集合。"""

    work_root: Path
    vault_dir: Path

    @property
    def daily_dir(self) -> Path:
        return self.vault_dir / "daily"

    @property
    def projects_dir(self) -> Path:
        return self.vault_dir / "projects"

    @property
    def meetings_dir(self) -> Path:
        return self.vault_dir / "meetings"

    @property
    def review_dir(self) -> Path:
        return self.vault_dir / "review"

    @property
    def signals_dir(self) -> Path:
        return self.vault_dir / "_signals"

    @property
    def inbox_file(self) -> Path:
        return self.vault_dir / "inbox.md"


def resolve_work_paths(
    work_root: str | os.PathLike[str] | None = None,
    vault_dir: str | os.PathLike[str] | None = None,
) -> WorkPaths:
    """派生 :class:`WorkPaths`。

    ``vault_dir`` 默认是 ``<work_root>/_vault``（PRD 3.1.5），可被显式覆盖。
    """
    root = resolve_work_root(work_root)
    vault = Path(vault_dir).expanduser() if vault_dir else root / "_vault"
    return WorkPaths(work_root=root, vault_dir=vault)
