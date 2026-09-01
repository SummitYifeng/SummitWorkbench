"""飞书授权健康度：记住「当前是否需要重新授权」，让 token 失效对用户可见（加固 #4）。

**要解决的问题**：飞书 refresh_token 会过期/被吊销。一旦失效，无人值守的 `wb brief` 会
**优雅降级**（飞书事实源缺失，简报照常出）——这是对的，但如果只是降级而不留痕，用户可能
连续多天不知道飞书那半边已经瞎了，直到某天想起来才发现要重新授权。

对策：每次简报运行把飞书授权结局落一个单文件状态（需重新授权 / 正常），`wb status` 据此
醒目提示「请 wb feishu login」。落盘单 JSON、带 `schema_version`（ADR 0019）、原子写。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories._schema import (
    FEISHU_AUTH_STATE_VERSION,
    SCHEMA_VERSION_FIELD,
)

FEISHU_AUTH_SUBDIR = "_signals"
_STATE_NAME = "feishu-auth.json"


@dataclass(frozen=True)
class FeishuAuthState:
    """当前飞书授权健康度。``needs_reauthorize`` 为真即需用户重新走一次 ``wb feishu login``。"""

    needs_reauthorize: bool = False
    detail: str | None = None
    since_day: str | None = None  # 首次检测到需重新授权的业务日（恢复正常即清空）


def _state_path(vault_dir: Path) -> Path:
    return vault_dir / FEISHU_AUTH_SUBDIR / _STATE_NAME


def read_auth_state(vault_dir: Path) -> FeishuAuthState:
    """读回飞书授权健康度；缺失或损坏则视为正常（不误报）。"""
    path = _state_path(vault_dir)
    if not path.is_file():
        return FeishuAuthState()
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return FeishuAuthState()
    if not isinstance(row, dict):
        return FeishuAuthState()
    return FeishuAuthState(
        needs_reauthorize=bool(row.get("needs_reauthorize", False)),
        detail=row.get("detail") or None,
        since_day=row.get("since_day") or None,
    )


def write_auth_state(
    vault_dir: Path,
    *,
    needs_reauthorize: bool,
    day: str,
    detail: str | None = None,
) -> Path:
    """幂等写飞书授权健康度。

    ``needs_reauthorize`` 为真时保留最早的 ``since_day``（连续需授权不刷新起点）；
    转为正常时清空 detail/since_day。
    """
    path = _state_path(vault_dir)
    since_day: str | None = None
    if needs_reauthorize:
        prior = read_auth_state(vault_dir)
        since_day = prior.since_day if prior.needs_reauthorize and prior.since_day else day
    row = {
        SCHEMA_VERSION_FIELD: FEISHU_AUTH_STATE_VERSION,
        "needs_reauthorize": needs_reauthorize,
        "detail": detail if needs_reauthorize else None,
        "since_day": since_day,
    }
    text = json.dumps(row, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, ensure_parents=True)
    return path
