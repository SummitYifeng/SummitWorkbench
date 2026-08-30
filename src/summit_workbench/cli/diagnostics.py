"""``wb diagnose`` 的采集逻辑。

只读、无副作用：报告运行时、路径与外部工具可用性，帮助确认底座是否装好。
绝不打印任何秘密值（凭据只报告是否可解析）。
"""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import asdict, dataclass, field

from summit_workbench.config.settings import Settings, default_config_file

# M0-1 尚未接入飞书 / 模型，这里只探测底座运行必需的系统工具。
_REQUIRED_TOOLS = ("git", "launchctl", "security")


@dataclass
class Diagnostics:
    python_version: str
    python_ok: bool
    platform: str
    work_root: str
    work_root_exists: bool
    vault_dir: str
    vault_dir_exists: bool
    config_file: str
    config_file_found: bool
    tools: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """底座是否达到「可继续」状态：Python 版本达标且必需工具齐全。"""
        return self.python_ok and all(self.tools.values())

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def collect(settings: Settings) -> Diagnostics:
    paths = settings.work_paths()
    cfg = default_config_file()
    return Diagnostics(
        python_version=platform.python_version(),
        python_ok=sys.version_info >= (3, 12),
        platform=platform.platform(),
        work_root=str(paths.work_root),
        work_root_exists=paths.work_root.is_dir(),
        vault_dir=str(paths.vault_dir),
        vault_dir_exists=paths.vault_dir.is_dir(),
        config_file=str(cfg),
        config_file_found=cfg.is_file(),
        tools={name: shutil.which(name) is not None for name in _REQUIRED_TOOLS},
    )
