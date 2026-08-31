"""模型用量记录（NFR-8）。

逐次记录时间、能力类型、模型 ID、输入/输出 token、重试次数与按当期单价估算的费用。
估算用配置快照，单价或模型变更不改写历史记录——因此费用与单价随记录一起落盘。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from summit_workbench.providers.llm.client import CompletionResult
from summit_workbench.providers.llm.config import ModelConfig


@dataclass(frozen=True)
class UsageRecord:
    timestamp: str
    capability: str
    model_id: str
    input_tokens: int
    output_tokens: int
    attempts: int
    task_key: str
    estimated_cost: float
    currency: str
    price_input_per_mtok: float
    price_output_per_mtok: float
    extra: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def record_from_result(
    cfg: ModelConfig,
    result: CompletionResult,
    *,
    task_key: str,
    now: datetime | None = None,
) -> UsageRecord:
    """由一次调用结果构造用量记录，含按 ``cfg.pricing`` 估算的费用快照。"""
    ts = (now or datetime.now(UTC)).isoformat()
    cost = cfg.pricing.estimate(result.usage.input_tokens, result.usage.output_tokens)
    return UsageRecord(
        timestamp=ts,
        capability=cfg.capability,
        model_id=cfg.model_id,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        attempts=result.attempts,
        task_key=task_key,
        estimated_cost=round(cost, 6),
        currency=cfg.pricing.currency,
        price_input_per_mtok=cfg.pricing.input_per_mtok,
        price_output_per_mtok=cfg.pricing.output_per_mtok,
    )
