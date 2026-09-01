"""定时任务运行健康度：从心跳事件推导「上次何时跑、跑成没、连续失败几次」（纯领域）。

**要解决的问题**：`wb brief` / `wb weekly` 由 launchd 无人值守定时运行（每日 08:00 /
周一 07:30）。一旦某天失败——飞书 token 过期、模型耗尽、磁盘满、异常崩溃——目前只会落在
launchd 的 stderr 日志文件里，用户不会主动去看，于是 **静默失联**：可能连续多天没出简报而
毫不知情。

对策：每次运行落一条 **心跳**（成功 / 降级 / 失败），再由这里的纯规则推导每个任务的健康度，
供 ``wb status`` 醒目呈现、并在连续失败跨阈值时告警一次。本模块不碰 IO——输入一串按时间
顺序排列的 :class:`RunEvent`，输出每个任务的 :class:`JobHealth`。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

#: 产品已知的定时任务标识（``wb status`` 即便某任务从未运行也照常显示其一行）。
KNOWN_JOBS: tuple[str, ...] = ("brief", "weekly")

#: 连续失败达到该次数即视为需要告警（memory：连续 3 天失败告警）。
CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3


class RunStatus(StrEnum):
    """一次定时运行的结局。"""

    SUCCESS = "success"  # 正常产出
    DEGRADED = "degraded"  # 产出了，但事实源/排序降级（飞书不可用、排序回退）
    FAILED = "failed"  # 未产出（抛异常/写盘失败）


@dataclass(frozen=True)
class RunEvent:
    """一条心跳事件（由持久层的行映射而来）。"""

    job: str
    status: RunStatus
    at: str  # ISO 时间戳
    day: str  # YYYY-MM-DD（运行针对的业务日）


@dataclass(frozen=True)
class JobHealth:
    """某个定时任务的当前健康度快照。"""

    job: str
    last_status: RunStatus | None = None
    last_at: str | None = None
    last_day: str | None = None
    consecutive_failures: int = 0
    total_runs: int = 0

    @property
    def ever_ran(self) -> bool:
        return self.total_runs > 0

    @property
    def ok(self) -> bool:
        """最近一次是否产出了（成功或降级都算跑出来了；仅 FAILED 视为没跑出）。"""
        return self.last_status in (RunStatus.SUCCESS, RunStatus.DEGRADED)

    def ran_on(self, day: str) -> bool:
        """最近一次运行是否针对 ``day``（用于「今日是否已跑」判断）。"""
        return self.last_day == day

    def as_dict(self) -> dict[str, object]:
        return {
            "job": self.job,
            "last_status": self.last_status.value if self.last_status else None,
            "last_at": self.last_at,
            "last_day": self.last_day,
            "consecutive_failures": self.consecutive_failures,
            "total_runs": self.total_runs,
        }


def _evaluate_one(job: str, events: Sequence[RunEvent]) -> JobHealth:
    if not events:
        return JobHealth(job=job)
    last = events[-1]
    # 当前失败连击：从最近一条往回数连续 FAILED，遇到任何非失败即中断。
    streak = 0
    for event in reversed(events):
        if event.status is RunStatus.FAILED:
            streak += 1
        else:
            break
    return JobHealth(
        job=job,
        last_status=last.status,
        last_at=last.at,
        last_day=last.day,
        consecutive_failures=streak,
        total_runs=len(events),
    )


def evaluate_runs(
    events: Iterable[RunEvent],
    *,
    jobs: Sequence[str] = KNOWN_JOBS,
) -> dict[str, JobHealth]:
    """把按时间顺序排列的心跳事件汇总成每个任务的健康度。

    ``jobs`` 里列出的任务即便从未运行也会得到一个 ``total_runs=0`` 的条目（便于
    ``wb status`` 呈现「从未运行」而非默默缺席）。事件里出现的其它任务同样纳入。
    """
    grouped: dict[str, list[RunEvent]] = {job: [] for job in jobs}
    for event in events:
        grouped.setdefault(event.job, []).append(event)
    return {job: _evaluate_one(job, evs) for job, evs in grouped.items()}
