"""安装级 onboarding 草稿（P0-11A）。

草稿只保存可恢复向导所需的非秘密字段；凭据、token、workspace id 和任意未知字段
都不能进入该文件。文件位于 Application Support 根而非某个 workspace profile，
因为空安装时尚未有 workspace。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from summit_workbench.config.app_support import PROFILE_FILE_MODE, app_support_dir
from summit_workbench.repositories._atomic import atomic_write_text

_DRAFT_FILENAME = "onboarding-draft.json"


class OnboardingDraft(BaseModel):
    """可安全恢复的非秘密向导进度。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    flow: Literal["create-new", "connect-existing", "upgrade-existing", "model", "feishu"] = (
        "create-new"
    )
    step: str = Field(default="welcome", min_length=1, max_length=64)
    work_root: str | None = Field(default=None, max_length=2_048)
    vault_dir: str | None = Field(default=None, max_length=2_048)
    display_name: str | None = Field(default=None, max_length=200)
    device_name: str | None = Field(default=None, max_length=200)
    git_mode: Literal["local", "remote", "skipped"] | None = None
    remote_url: str | None = Field(default=None, max_length=2_048)
    expected_workspace_id: str | None = Field(default=None, max_length=200)
    git_username: str | None = Field(default=None, max_length=200)
    model_provider: str | None = Field(default=None, max_length=100)
    model_id: str | None = Field(default=None, max_length=200)
    model_base_url: str | None = Field(default=None, max_length=2_048)
    model_credential_account: str | None = Field(default=None, max_length=200)
    feishu_app_id: str | None = Field(default=None, max_length=200)
    feishu_redirect_uri: str | None = Field(default=None, max_length=2_048)
    provider_status: Literal["pending", "skipped", "ready"] = "pending"
    automation_role: Literal["primary", "secondary"] = "secondary"
    workspace_id: None = None
    updated_at: str | None = None


class OnboardingDraftError(RuntimeError):
    """草稿损坏或不符合安全契约。"""


def onboarding_draft_path(home: Path | None = None) -> Path:
    return app_support_dir(home) / _DRAFT_FILENAME


def load_onboarding_draft(home: Path | None = None) -> OnboardingDraft | None:
    path = onboarding_draft_path(home)
    if not path.is_file():
        return None
    try:
        return OnboardingDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError) as exc:
        raise OnboardingDraftError("onboarding 草稿损坏，请重新开始") from exc


def save_onboarding_draft(draft: OnboardingDraft, *, home: Path | None = None) -> Path:
    """原子保存安装级草稿，强制移除 workspace id 并写入 0600 文件。"""
    safe = draft.model_copy(
        update={"workspace_id": None, "updated_at": datetime.now(UTC).isoformat()}
    )
    path = onboarding_draft_path(home)
    atomic_write_text(
        path,
        json.dumps(safe.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        ensure_parents=True,
        new_mode=PROFILE_FILE_MODE,
    )
    return path


def clear_onboarding_draft(home: Path | None = None) -> None:
    path = onboarding_draft_path(home)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
