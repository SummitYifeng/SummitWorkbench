"""把已鉴权的 :class:`FeishuClient` 适配成简报采集所需的 :class:`FactsSource`。

只做「取原始事实」：今日会议、未完成任务、近期已完成任务。时间窗换算是确定性的。
真机端点由 provider 层（calendar/tasks）负责；确切端点待真机冒烟核实（见 ADR 0015）。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from summit_workbench.providers.feishu.calendar import CalendarEvent, list_events_between
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.tasks import TaskItem, list_tasks

# 「最近完成」的回看窗口（天）。
COMPLETED_LOOKBACK_DAYS = 3


class FeishuFactsSource:
    """基于用户身份 access_token 的事实来源。"""

    def __init__(self, client: FeishuClient, *, day: str, timezone: str) -> None:
        self.client = client
        self.timezone = timezone
        self._day = datetime.fromisoformat(day).date()

    def _day_window_unix(self) -> tuple[int, int]:
        tz = ZoneInfo(self.timezone)
        start = datetime.combine(self._day, time.min, tzinfo=tz)
        end = datetime.combine(self._day, time.max, tzinfo=tz)
        return int(start.timestamp()), int(end.timestamp())

    def meetings(self) -> list[CalendarEvent]:
        start, end = self._day_window_unix()
        return list_events_between(self.client, start, end)

    def open_tasks(self) -> list[TaskItem]:
        return list_tasks(self.client, timezone=self.timezone, completed=False)

    def completed_tasks(self) -> list[TaskItem]:
        done = list_tasks(self.client, timezone=self.timezone, completed=True)
        cutoff = (self._day - timedelta(days=COMPLETED_LOOKBACK_DAYS)).isoformat()
        # 仅保留回看窗内完成的；completed_at 缺失时保守保留。
        return [t for t in done if _completed_recently(t, cutoff, self.timezone)]


def _completed_recently(task: TaskItem, cutoff_iso: str, timezone: str) -> bool:
    if not task.completed_at:
        return True
    try:
        moment = datetime.fromtimestamp(int(task.completed_at) / 1000, tz=ZoneInfo(timezone))
    except (ValueError, OSError):
        return True
    return moment.date().isoformat() >= cutoff_iso
