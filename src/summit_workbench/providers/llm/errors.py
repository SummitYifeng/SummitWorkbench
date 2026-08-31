"""云端模型适配层的显式错误（NFR-6：失败必须可见，禁止静默吞错）。"""

from __future__ import annotations


class LLMError(RuntimeError):
    """模型交互基类错误。信息中不得含 api key。"""


class LLMConfigError(LLMError):
    """模型配置缺失或非法。"""


class LLMTimeoutError(LLMError):
    """请求超时。属可重试的瞬时故障。"""


class LLMAPIError(LLMError):
    """模型服务返回 HTTP 错误或异常响应。``status`` 便于审计与重试判断。"""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class LLMSchemaError(LLMError):
    """模型输出不符合约定 schema（JSON 非法或字段缺失）。"""
