"""配置分层加载。

优先级（高 → 低）：
1. 显式传入的初始化参数（测试 / 调用方覆盖）
2. 环境变量（``WORK_ROOT``，以及 ``WB_`` 前缀的其余项）
3. 本机配置文件（TOML，默认 ``$HOME/.config/summit_workbench/config.toml``）
4. 代码内置默认值

配置文件只存放非敏感项；凭据一律以引用形式指向 Keychain（见
:mod:`summit_workbench.config.secrets`），配置里不出现秘密值。
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from summit_workbench.config.paths import WorkPaths, resolve_work_paths

_CONFIG_FILE_ENV = "WB_CONFIG_FILE"


def default_config_file() -> Path:
    """本机配置文件默认路径，可用 ``WB_CONFIG_FILE`` 覆盖。"""
    override = os.environ.get(_CONFIG_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "summit_workbench" / "config.toml"


class Settings(BaseSettings):
    """全局最小配置（work_root / vault / 时区 / 日志级别）。

    飞书与模型的配置各自独立（`[feishu]` / `[models.*]`，见对应 provider），不混入此处。
    """

    model_config = SettingsConfigDict(
        env_prefix="WB_",
        extra="ignore",
        # ``WORK_ROOT`` 是 PRD 约定的裸变量名（非 WB_ 前缀），单独声明别名。
    )

    work_root: Path | None = Field(default=None, validation_alias="WORK_ROOT")
    vault_dir: Path | None = Field(default=None)
    timezone: str = Field(default="Asia/Shanghai")
    log_level: str = Field(default="INFO")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 返回顺序即优先级：靠前者胜出。
        toml_source = TomlConfigSettingsSource(settings_cls, toml_file=default_config_file())
        return (init_settings, env_settings, toml_source)

    def work_paths(self) -> WorkPaths:
        """基于当前配置派生稳定路径集合。"""
        return resolve_work_paths(work_root=self.work_root, vault_dir=self.vault_dir)


def load_settings(**overrides: object) -> Settings:
    """加载配置，``overrides`` 具有最高优先级（主要供测试与诊断使用）。"""
    # pydantic-settings 生成的 __init__ 只接受具体字段类型，这里刻意保留灵活的
    # 关键字覆盖入口（init 源优先级最高），因此局部忽略 kwargs 的静态类型检查。
    return Settings(**overrides)  # type: ignore[arg-type]
