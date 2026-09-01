"""会议处理状态账本：把 :class:`MeetingTask` 的状态变迁落盘（防重 + 可审计）。

对应 PRD 3.1.9 L14 第 6 条：以 ``meeting_id + note_id``（本地导入用内容哈希）为幂等键，
「发现 vault 中已有成功记录即空转」。为此需要一处可按幂等键查询当前状态的持久层。

实现沿用用量账本的 append-only JSONL 思路：每次状态变迁追加一行，``latest_task`` 取
同一幂等键的最后一条即当前状态；整条日志本身就是审计轨迹。只做读写，防重判定交给上层
（workflow）。落盘位置 ``_vault/_signals/meeting-state/log.jsonl``。

读取走 :func:`repositories._jsonl.read_models` 的容错通道（LHF #2）：坏行（断电/被 kill
留下的半截行、缺键行）跳过 + 告警 + 隔离，而不再让整本读取崩溃。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from summit_workbench.domain.pipeline import MeetingTask, ProcessingState, SourceKind
from summit_workbench.repositories._jsonl import append_row, read_models
from summit_workbench.repositories._schema import (
    MEETING_STATE_VERSION,
    SCHEMA_VERSION_FIELD,
)

MEETING_STATE_SUBDIR = ("_signals", "meeting-state")
_LOG_NAME = "log.jsonl"


class MeetingStateRow(BaseModel):
    """状态日志一行的显式 schema。``extra="ignore"`` 容忍未来新增字段（schema 漂移）。

    ``source`` / ``state`` 由 Pydantic 直接校验成枚举——非法值即校验失败、该行被跳过，
    而不会污染防重判定。空字符串的可选字段归一为 ``None``。
    """

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1  # 引入版本机制前写的旧行不含此字段，缺失即视为 v1
    idem_key: str
    source: SourceKind
    state: ProcessingState
    meeting_id: str | None = None
    note_id: str | None = None
    reason: str | None = None

    def to_task(self) -> MeetingTask:
        return MeetingTask(
            idem_key=self.idem_key,
            source=self.source,
            state=self.state,
            meeting_id=self.meeting_id or None,
            note_id=self.note_id or None,
            reason=self.reason or None,
        )


def _state_log(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*MEETING_STATE_SUBDIR, _LOG_NAME)


def record_task(vault_dir: Path, task: MeetingTask, *, now: datetime | None = None) -> Path:
    """追加一条状态记录，返回日志文件路径。"""
    return append_row(
        _state_log(vault_dir),
        {
            SCHEMA_VERSION_FIELD: MEETING_STATE_VERSION,
            "timestamp": (now or datetime.now(UTC)).isoformat(),
            "idem_key": task.idem_key,
            "source": task.source.value,
            "state": task.state.value,
            "meeting_id": task.meeting_id,
            "note_id": task.note_id,
            "reason": task.reason,
        },
    )


def _iter_tasks(vault_dir: Path) -> list[MeetingTask]:
    return [row.to_task() for row in read_models(_state_log(vault_dir), MeetingStateRow)]


def latest_task(vault_dir: Path, idem_key: str) -> MeetingTask | None:
    """返回某幂等键的当前状态（日志中最后一条）；从未记录则 ``None``。"""
    latest: MeetingTask | None = None
    for task in _iter_tasks(vault_dir):
        if task.idem_key == idem_key:
            latest = task
    return latest


def all_latest(vault_dir: Path) -> dict[str, MeetingTask]:
    """返回每个幂等键的当前状态（供 ``wb status`` 汇总，M1-5）。"""
    latest: dict[str, MeetingTask] = {}
    for task in _iter_tasks(vault_dir):
        latest[task.idem_key] = task
    return latest
