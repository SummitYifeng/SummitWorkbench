"""运行心跳的「最佳努力」记录：记心跳绝不能反过来搞垮任务本身。

无人值守任务在 CLI 边界前后各记一次心跳（成功/降级/失败）。但落盘可能失败（磁盘满、
权限）——那时 **不应** 让「记录失败」掩盖或替换任务本身的真实结局。故这里把记录包一层
吞掉异常：宁可少一条心跳，也不制造一个来自日志器的假错误。
"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.domain.run_health import RunStatus
from summit_workbench.repositories.run_heartbeat import record_run


def record_run_safely(
    vault_dir: Path,
    *,
    job: str,
    status: RunStatus,
    day: str,
    detail: str | None = None,
) -> None:
    """尽力记录一条运行心跳；任何落盘异常被吞（不反向搞垮任务）。"""
    try:
        record_run(vault_dir, job=job, status=status, day=day, detail=detail)
    except Exception:  # 记录心跳失败绝不能令任务失败——刻意吞掉
        pass
