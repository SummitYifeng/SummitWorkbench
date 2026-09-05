"""飞书适配层的显式错误类型（NFR-6：任何失败都必须可见，禁止静默吞错）。"""

from __future__ import annotations


class FeishuError(RuntimeError):
    """飞书交互的基类错误。错误信息中不得包含任何凭据。"""


class FeishuConfigError(FeishuError):
    """配置缺失或非法（如未设置 app_id、缺少凭据引用）。"""


class FeishuAuthError(FeishuError):
    """身份授权 / token 刷新失败。

    ``needs_reauthorize`` 为真时表示 refresh_token 已失效，需要用户重新走一次授权，
    不应静默重试（对应 R5 / NFR-4 的「失败时显式告警，不静默重试」）。

    ``retryable`` / ``retry_after`` 供退避层判断：仅瞬时基础设施故障（超时 / 429 / 5xx）
    可重试；``needs_reauthorize`` 一类语义失败绝不重试。
    """

    def __init__(
        self,
        message: str,
        *,
        needs_reauthorize: bool = False,
        retryable: bool = False,
        retry_after: float | None = None,
        result_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.needs_reauthorize = needs_reauthorize
        self.retryable = retryable
        self.retry_after = retry_after
        self.result_unknown = result_unknown


class FeishuAPIError(FeishuError):
    """飞书 API 返回非零 code 或 HTTP 错误。

    保留 ``code`` 与 ``status`` 以便审计与降级判断，但不保留响应中可能的敏感正文。
    ``retryable`` / ``retry_after`` 供退避层判断瞬时故障（超时 / 429 / 5xx）与其等待时长。
    """

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        result_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after
        self.result_unknown = result_unknown
