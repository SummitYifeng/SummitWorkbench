"""P1-01 本机自动化设置持久化。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from summit_workbench.config.app_support import PROFILE_FILE_MODE, profile_dir
from summit_workbench.domain.automation import AutomationSettings
from summit_workbench.repositories._atomic import atomic_write_text

_FILE_NAME = "automation.json"


def automation_settings_file(workspace_id: str, *, home: Path | None = None) -> Path:
    return profile_dir(workspace_id, home=home) / _FILE_NAME


def load_automation_settings(workspace_id: str, *, home: Path | None = None) -> AutomationSettings:
    """读取 workspace 自动化设置；缺失时返回内存默认值，不创建文件。"""
    path = automation_settings_file(workspace_id, home=home)
    if not path.is_file():
        return AutomationSettings.defaults(workspace_id)
    try:
        settings = AutomationSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"自动化设置损坏，请检查 {path}") from exc
    if settings.workspace_id != workspace_id:
        raise ValueError("自动化设置 workspace_id 不匹配")
    return settings


def save_automation_settings(settings: AutomationSettings, *, home: Path | None = None) -> Path:
    path = automation_settings_file(settings.workspace_id, home=home)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, new_mode=PROFILE_FILE_MODE)
    return path
