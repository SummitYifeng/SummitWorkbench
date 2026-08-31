"""云端模型适配器：供应商无关的 chat 客户端、配置、用量与错误。

领域逻辑不感知具体供应商；prompt 与输出 schema 不写死模型名称（见模块边界）。
"""

from summit_workbench.providers.llm.client import CompletionResult, ModelClient, Usage
from summit_workbench.providers.llm.config import (
    CAPABILITIES,
    ModelConfig,
    ModelPricing,
    load_model_config,
)
from summit_workbench.providers.llm.errors import (
    LLMAPIError,
    LLMConfigError,
    LLMError,
    LLMSchemaError,
    LLMTimeoutError,
)
from summit_workbench.providers.llm.usage import UsageRecord, record_from_result

__all__ = [
    "CAPABILITIES",
    "CompletionResult",
    "LLMAPIError",
    "LLMConfigError",
    "LLMError",
    "LLMSchemaError",
    "LLMTimeoutError",
    "ModelClient",
    "ModelConfig",
    "ModelPricing",
    "Usage",
    "UsageRecord",
    "load_model_config",
    "record_from_result",
]
