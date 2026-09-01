"""当日信号快照持久化（M2-3）：``_vault/_signals/YYYY-MM-DD.json``。

每次生成简报落一份当日快照，用于北极星指标基线（信号从出现到消失的中位天数，PRD 2.4）
与幂等核对。按日期覆盖写：同一天重跑得到确定性的最新快照，不产生重复文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories._schema import (
    SCHEMA_VERSION_FIELD,
    SIGNAL_SNAPSHOT_VERSION,
)

SIGNALS_SUBDIR = "_signals"


def snapshot_path(vault_dir: Path, day: str) -> Path:
    """当日快照文件路径（``day`` 为 ISO ``YYYY-MM-DD``）。"""
    return vault_dir / SIGNALS_SUBDIR / f"{day}.json"


def write_snapshot(vault_dir: Path, day: str, payload: dict[str, object]) -> Path:
    """覆盖写当日快照，返回文件路径。

    快照顶层打上 ``schema_version`` 便于将来格式演进的兼容读；落盘走原子写
    （写 ``.tmp`` 再换名），断电/被 kill 不会留下半截 JSON 污染当日快照。
    """
    path = snapshot_path(vault_dir, day)
    versioned = {SCHEMA_VERSION_FIELD: SIGNAL_SNAPSHOT_VERSION, **payload}
    atomic_write_text(
        path,
        json.dumps(versioned, ensure_ascii=False, indent=2) + "\n",
        ensure_parents=True,
    )
    return path


def read_snapshot(vault_dir: Path, day: str) -> dict[str, object] | None:
    """读回当日快照；不存在返回 None。"""
    path = snapshot_path(vault_dir, day)
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None
