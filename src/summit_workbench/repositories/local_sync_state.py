"""本机 workspace 同步状态持久化（P0-10）。

状态落在 ``profiles/<workspace_id>/sync-state.json``（P0-07 布局，不同步），
本机文件 0600、目录 0700、原子写（P0-06 原语）。
**仅 ACTIVE profile 场景落盘**；env-compat（未建档的旧开发形态）不写盘，
由调用方以内存快照处理（避免在无 profile 时触碰真实 Application Support）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from summit_workbench.config.app_support import (
    PROFILE_DIR_MODE,
    PROFILE_FILE_MODE,
    app_support_dir,
    profile_dir,
)
from summit_workbench.domain.sync import SyncSnapshot
from summit_workbench.repositories._atomic import atomic_write_text

_SYNC_STATE_FILENAME = "sync-state.json"


def sync_state_path(workspace_id: str, home: Path | None = None) -> Path:
    """某 workspace 的本机同步状态文件路径。"""
    return profile_dir(workspace_id, home) / _SYNC_STATE_FILENAME


def load_sync_state(workspace_id: str, home: Path | None = None) -> SyncSnapshot | None:
    """读本机同步状态；文件缺失返回 None，损坏抛 ValueError（可见，不静默）。"""
    path = sync_state_path(workspace_id, home)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SyncSnapshot.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"sync-state.json 损坏：{path}") from exc


def save_sync_state(snapshot: SyncSnapshot, home: Path | None = None) -> Path:
    """原子写本机同步状态（目录 0700、文件 0600）。"""
    root = app_support_dir(home)
    root.mkdir(mode=PROFILE_DIR_MODE, parents=True, exist_ok=True)
    os.chmod(root, PROFILE_DIR_MODE)
    directory = profile_dir(snapshot.workspace_id, home)
    directory.mkdir(mode=PROFILE_DIR_MODE, parents=True, exist_ok=True)
    os.chmod(directory, PROFILE_DIR_MODE)
    path = sync_state_path(snapshot.workspace_id, home)
    text = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, new_mode=PROFILE_FILE_MODE)
    return path
