"""飞书 OpenAPI 适配器：身份授权、会话/令牌、已鉴权客户端与会议逐字稿来源。

只做飞书身份、会议、纪要、日历与任务的 API 适配，不写 vault（见模块边界）。
"""

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
    TranscriptResult,
    import_local_transcript,
    verify_identity,
)
from summit_workbench.providers.feishu.session import FeishuSession

__all__ = [
    "DEFAULT_SCOPES",
    "FeishuAPIError",
    "FeishuAuthError",
    "FeishuClient",
    "FeishuConfig",
    "FeishuConfigError",
    "FeishuError",
    "FeishuNoteSource",
    "FeishuSession",
    "TranscriptResult",
    "import_local_transcript",
    "load_feishu_config",
    "verify_identity",
]
