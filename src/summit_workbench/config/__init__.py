"""配置分层、路径解析与凭据引用。

本包只负责「读取配置、解析路径、引用凭据」，绝不输出任何秘密值
（见 NFR-4 与开发计划模块边界）。
"""

from summit_workbench.config.paths import WorkPaths, resolve_work_paths
from summit_workbench.config.secrets import CredentialRef, resolve_credential
from summit_workbench.config.settings import Settings, load_settings

__all__ = [
    "CredentialRef",
    "Settings",
    "WorkPaths",
    "load_settings",
    "resolve_credential",
    "resolve_work_paths",
]
