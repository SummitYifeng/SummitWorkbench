"""会议处理状态账本：把 :class:`MeetingTask` 的状态变迁落盘（防重 + 可审计）。

对应 PRD 3.1.9 L14 第 6 条：以 ``meeting_id + note_id``（本地导入用内容哈希）为幂等键，
「发现 vault 中已有成功记录即空转」。为此需要一处可按幂等键查询当前状态的持久层。

实现沿用用量账本的 append-only JSONL 思路：每次状态变迁追加一行，``latest_task`` 取
同一幂等键的最后一条即当前状态；整条日志本身就是审计轨迹。只做读写，防重判定交给上层
（workflow）。落盘位置 ``_vault/_signals/meeting-state/log.jsonl``。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState, SourceKind

MEETING_STATE_SUBDIR = ("_signals", "meeting-state")
_LOG_NAME = "log.jsonl"


def _state_log(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*MEETING_STATE_SUBDIR, _LOG_NAME)


def record_task(vault_dir: Path, task: MeetingTask, *, now: datetime | None = None) -> Path:
    """追加一条状态记录，返回日志文件路径。"""
    log = _state_log(vault_dir)
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": (now or datetime.now(UTC)).isoformat(),
        "idem_key": task.idem_key,
        "source": task.source.value,
        "state": task.state.value,
        "meeting_id": task.meeting_id,
        "note_id": task.note_id,
        "reason": task.reason,
    }
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return log


def _task_from_row(row: dict[str, object]) -> MeetingTask:
    return MeetingTask(
        idem_key=str(row["idem_key"]),
        source=SourceKind(str(row["source"])),
        state=ProcessingState(str(row["state"])),
        meeting_id=(str(row["meeting_id"]) if row.get("meeting_id") else None),
        note_id=(str(row["note_id"]) if row.get("note_id") else None),
        reason=(str(row["reason"]) if row.get("reason") else None),
    )


def _iter_rows(vault_dir: Path) -> list[dict[str, object]]:
    log = _state_log(vault_dir)
    if not log.is_file():
        return []
    rows: list[dict[str, object]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_task(vault_dir: Path, idem_key: str) -> MeetingTask | None:
    """返回某幂等键的当前状态（日志中最后一条）；从未记录则 ``None``。"""
    latest: MeetingTask | None = None
    for row in _iter_rows(vault_dir):
        if str(row.get("idem_key")) == idem_key:
            latest = _task_from_row(row)
    return latest


def all_latest(vault_dir: Path) -> dict[str, MeetingTask]:
    """返回每个幂等键的当前状态（供 ``wb status`` 汇总，M1-5）。"""
    latest: dict[str, MeetingTask] = {}
    for row in _iter_rows(vault_dir):
        task = _task_from_row(row)
        latest[task.idem_key] = task
    return latest
