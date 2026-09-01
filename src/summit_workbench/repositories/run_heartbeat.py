"""定时任务运行心跳账本：把每次 ``wb brief`` / ``wb weekly`` 的结局落盘（无人值守可见性）。

append-only JSONL（``_vault/_signals/run-heartbeat/log.jsonl``），沿用状态账本的写法：
每次运行追加一行结局（成功 / 降级 / 失败），整条日志即运行史。健康度推导（上次何时跑、
连续失败几次）交给纯领域 :mod:`summit_workbench.domain.run_health`。

读取走 :func:`repositories._jsonl.read_models` 容错通道（LHF #2）：坏行跳过 + 隔离，
不让半截末行拖垮健康度汇总。写入带 ``schema_version``（ADR 0019）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from summit_workbench.domain.run_health import RunEvent, RunStatus
from summit_workbench.repositories._jsonl import append_row, read_models
from summit_workbench.repositories._schema import (
    RUN_HEARTBEAT_VERSION,
    SCHEMA_VERSION_FIELD,
)

RUN_HEARTBEAT_SUBDIR = ("_signals", "run-heartbeat")
_LOG_NAME = "log.jsonl"


class RunHeartbeatRow(BaseModel):
    """心跳日志一行的显式 schema。``extra="ignore"`` 容忍 schema 漂移；``status`` 非法即跳过。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1  # 引入版本机制前写的旧行不含此字段，缺失即视为 v1
    job: str
    status: RunStatus
    timestamp: str
    day: str | None = None
    detail: str | None = None

    def to_event(self) -> RunEvent:
        return RunEvent(job=self.job, status=self.status, at=self.timestamp, day=self.day or "")


def _log(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*RUN_HEARTBEAT_SUBDIR, _LOG_NAME)


def record_run(
    vault_dir: Path,
    *,
    job: str,
    status: RunStatus,
    day: str,
    detail: str | None = None,
    now: datetime | None = None,
) -> Path:
    """追加一条运行心跳，返回日志路径。"""
    return append_row(
        _log(vault_dir),
        {
            SCHEMA_VERSION_FIELD: RUN_HEARTBEAT_VERSION,
            "timestamp": (now or datetime.now(UTC)).isoformat(),
            "job": job,
            "status": status.value,
            "day": day,
            "detail": detail,
        },
    )


def read_events(vault_dir: Path) -> list[RunEvent]:
    """容错读全部心跳事件（按追加顺序，即时间顺序）。"""
    return [row.to_event() for row in read_models(_log(vault_dir), RunHeartbeatRow)]
