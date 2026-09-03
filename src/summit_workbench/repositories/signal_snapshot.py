"""当日信号快照持久化（M2-3）：``_vault/_signals/YYYY-MM-DD.json``。

每次生成简报落一份当日快照，用于北极星指标基线（信号从出现到消失的中位天数，PRD 2.4）
与幂等核对。按日期覆盖写：同一天重跑得到确定性的最新快照，不产生重复文件。
"""

from __future__ import annotations

import json
import re
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


def _task_guid_matches(item: object, guid: str) -> bool:
    """快照 task_list 条目（``{task_id: ...}``）是否匹配目标任务 guid（大小写不敏感）。"""
    return isinstance(item, dict) and str(item.get("task_id") or "").lower() == guid.lower()


def _action_links_task(item: object, guid: str) -> bool:
    """行动候选是否关联目标任务：source_ref ``feishu-task:{guid}`` 或 signal_id ``task-{guid}``。"""
    if not isinstance(item, dict):
        return False
    lower = guid.lower()
    source_ref = str(item.get("source_ref") or "")
    signal_id = str(item.get("signal_id") or "")
    source_match = re.search(r"feishu-task:([0-9a-zA-Z_-]+)", source_ref)
    signal_match = re.match(r"^task-([0-9a-zA-Z_-]+)$", signal_id)
    if source_match is not None and source_match.group(1).lower() == lower:
        return True
    return signal_match is not None and signal_match.group(1).lower() == lower


def mark_task_completed(vault_dir: Path, day: str, task_guid: str) -> str | None:
    """把当日快照中某飞书任务镜像为「已完成」，返回被移除的任务标题（无快照/不在其中 → None）。

    飞书是任务状态的唯一真源；Web「一键完成」在 PATCH 成功后调用本函数，让当日
    **渲染快照**与之一致化（快照只服务 Web 面板与北极星基线，vault 简报 Markdown 不动）：
    - ``task_list`` 移除该任务（按 ``task_id`` 匹配）；
    - 引用它的行动候选同步移除——否则会以「需要行动 · 任务清单之外」重新出现；
    - ``completion_list`` 追加 ``{text: 标题, source_ref: feishu-task:{guid}}``（同源去重）；
    - 旧计数键 ``tasks`` / ``completions`` 同步，保持附加演进的读者契约。
    任务不在快照中（如当日尚无简报）时不写盘、返回 None，调用方照常向用户报成功。
    """
    snapshot = read_snapshot(vault_dir, day)
    if snapshot is None:
        return None
    task_list = snapshot.get("task_list")
    if not isinstance(task_list, list):
        return None  # 旧格式快照（无明细）：无镜像目标

    idx = next(
        (i for i, item in enumerate(task_list) if _task_guid_matches(item, task_guid)),
        None,
    )
    if idx is None:
        return None
    removed = task_list.pop(idx)
    summary = str(removed.get("summary", "") if isinstance(removed, dict) else "")

    actions = snapshot.get("actions")
    if isinstance(actions, list):
        snapshot["actions"] = [a for a in actions if not _action_links_task(a, task_guid)]

    completion_list = snapshot.get("completion_list")
    if not isinstance(completion_list, list):
        completion_list = []
    entry = {"text": summary, "source_ref": f"feishu-task:{task_guid}"}
    existing_refs = {
        str(c.get("source_ref") or "").lower() for c in completion_list if isinstance(c, dict)
    }
    if entry["source_ref"].lower() not in existing_refs:
        completion_list.append(entry)
    snapshot["completion_list"] = completion_list

    snapshot["tasks"] = len(task_list)
    snapshot["completions"] = len(completion_list)
    write_snapshot(vault_dir, day, snapshot)
    return summary or None
