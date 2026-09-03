"""飞书 OpenAPI 适配器：身份授权、会话/令牌、已鉴权客户端与会议逐字稿来源。

只做飞书身份、会议、纪要、日历与任务的 API 适配，不写 vault（见模块边界）。
"""

from summit_workbench.providers.feishu.calendar import (
    CalendarEvent,
    create_event,
    list_events_between,
    update_event,
)
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import (
    DEFAULT_SCOPES,
    FeishuConfig,
    load_feishu_config,
)
from summit_workbench.providers.feishu.errors import (
    FeishuAPIError,
    FeishuAuthError,
    FeishuConfigError,
    FeishuError,
)
from summit_workbench.providers.feishu.meetings import (
    FeishuNoteSource,
    MeetingSummary,
    TranscriptResult,
    import_local_transcript,
    list_meetings_by_no,
    verify_identity,
)
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.feishu.tasks import (
    CreatedTask,
    complete_task,
    create_task,
    update_task,
)

__all__ = [
    "CalendarEvent",
    "CreatedTask",
    "DEFAULT_SCOPES",
    "FeishuAPIError",
    "FeishuAuthError",
    "FeishuClient",
    "FeishuConfig",
    "FeishuConfigError",
    "FeishuError",
    "FeishuNoteSource",
    "FeishuSession",
    "MeetingSummary",
    "TranscriptResult",
    "complete_task",
    "create_event",
    "create_task",
    "import_local_transcript",
    "list_events_between",
    "list_meetings_by_no",
    "load_feishu_config",
    "update_event",
    "update_task",
    "verify_identity",
]
