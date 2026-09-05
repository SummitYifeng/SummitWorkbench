"""路径解析：单一权威入口。

硬约束（NFR-3）：禁止硬编码 ``/Users/<name>/``，一律基于 ``$HOME`` 或
``WORK_ROOT`` 环境变量派生。所有派生路径集中在此，方便未来 Mac Air 接入。

P0-06 起提供 :class:`WorkspacePaths` 作为**唯一解析对象**，明确 ``work_root``、
``vault_dir`` 与 ``lock_root``；web、brief、Feishu refresh、sync 及所有写者都从
它取得锁根，杜绝「自定义 vault 导致锁分裂」。profile 级本机状态（config、Keychain、
device/心跳）由 P0-07 的 profile/device 域管理，本模块只负责路径解析。
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
class WorkspacePaths:
    """单一权威路径解析结果：work_root / vault_dir / lock_root。

    - ``work_root``：工作项目根（env/显式；默认 ``$HOME/Documents/Work``）。
    - ``vault_dir``：vault 目录（默认 ``<work_root>/_vault``）。
    - ``lock_root``：工作区锁根 = vault 的容器目录；``.wb.lock`` 落在这里。
      默认形态（vault = ``<work_root>/_vault``）下它就是 ``work_root``；vault 被
      显式指到 work_root 下其它位置时锁根跟随 vault 容器。所有写者（web、brief、
      Feishu refresh、sync、CLI、仓库层）都以它为锁根，同一 workspace 共用同一把
      ``.wb.lock``，不因自定义 vault 路径分裂（P0-06）。

    vault 内部子目录（daily/projects/meetings/...）在各自 workflow 首次使用时按需派生，
    不在此预置未被使用的路径。
    """

    work_root: Path
    vault_dir: Path
    lock_root: Path

    @property
    def lock_file(self) -> Path:
        """本工作区的锁文件路径（``<lock_root>/.wb.lock``，不创建文件）。"""
        return self.lock_root / ".wb.lock"


# 兼容别名：早期调用方以 WorkPaths 引用旧 dataclass（含 settings 类型注解）。
WorkPaths = WorkspacePaths


def resolve_work_paths(
    work_root: str | os.PathLike[str] | None = None,
    vault_dir: str | os.PathLike[str] | None = None,
) -> WorkspacePaths:
    """派生 :class:`WorkspacePaths`（唯一的路径解析入口）。

    ``vault_dir`` 默认是 ``<work_root>/_vault``（PRD 3.1.5），可被显式覆盖；
    ``lock_root`` 恒为 vault 容器目录（默认形态下即 work_root），供所有锁调用取根。
    """
    root = resolve_work_root(work_root)
    vault = Path(vault_dir).expanduser() if vault_dir else root / "_vault"
    return WorkspacePaths(work_root=root, vault_dir=vault, lock_root=vault.parent)
