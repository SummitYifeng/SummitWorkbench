"""待确认积压阈值规则（PRD M1-5 / L44）。

达到 5 条或最老超过 3 天即进入告警；「只在跨越阈值或升级时重复通知」。
纯规则：给定当前积压量与已通知等级，判定是否应再次通知。
"""

from __future__ import annotations

from dataclasses import dataclass

# 阈值（PRD L21/M1-5）。
BACKLOG_COUNT_THRESHOLD = 5
BACKLOG_AGE_DAYS = 3


@dataclass(frozen=True)
class BacklogState:
    """待确认积压快照：条数与最老条目已等待天数。"""

    count: int
    oldest_age_days: int | None  # 无积压时为 None

    @property
    def count_triggered(self) -> bool:
        return self.count >= BACKLOG_COUNT_THRESHOLD

    @property
    def age_triggered(self) -> bool:
        return self.oldest_age_days is not None and self.oldest_age_days > BACKLOG_AGE_DAYS

    @property
    def severity(self) -> int:
        """触发的阈值个数（0/1/2）：升级即 severity 增大。"""
        return int(self.count_triggered) + int(self.age_triggered)

    @property
    def active(self) -> bool:
        return self.severity > 0

    def reason(self) -> str:
        parts: list[str] = []
        if self.count_triggered:
            parts.append(f"待确认 {self.count} 条（≥{BACKLOG_COUNT_THRESHOLD}）")
        if self.age_triggered:
            parts.append(f"最老已等待 {self.oldest_age_days} 天（>{BACKLOG_AGE_DAYS}）")
        return "；".join(parts)


def should_notify_backlog(current_severity: int, last_notified_severity: int) -> bool:
    """仅在严重度较上次通知升高时再次通知（跨越阈值或升级）。

    严重度回落时不通知；调用方应把最新严重度写回状态，使日后再次跨越阈值能重新通知。
    """
    return current_severity > last_notified_severity
