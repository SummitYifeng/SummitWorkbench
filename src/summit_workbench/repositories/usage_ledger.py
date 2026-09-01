"""模型用量账本持久化：JSONL 落盘到 ``_vault/_signals/model-usage/``。

按月一个 ``YYYY-MM.jsonl`` 文件，每次调用追加一行，便于按日/月汇总（NFR-8）。
只做读写与汇总，不决定预算是否触发告警（那是 observability 的职责）。

读取走 :func:`repositories._jsonl.read_models` 的容错通道（LHF #2）：断电/被 kill 留下的
半截行不再让整月费用汇总崩溃，坏行跳过 + 告警 + 隔离。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from summit_workbench.providers.llm.usage import UsageRecord
from summit_workbench.repositories._jsonl import append_row, read_models
from summit_workbench.repositories._schema import (
    SCHEMA_VERSION_FIELD,
    USAGE_LEDGER_VERSION,
)

MODEL_USAGE_SUBDIR = ("_signals", "model-usage")


class UsageRow(BaseModel):
    """用量日志一行里参与汇总的字段。``extra="ignore"`` 容忍其余字段与 schema 漂移。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1  # 引入版本机制前写的旧行不含此字段，缺失即视为 v1
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"


def _usage_dir(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*MODEL_USAGE_SUBDIR)


def _ledger(vault_dir: Path, year_month: str) -> Path:
    return _usage_dir(vault_dir) / f"{year_month}.jsonl"


def append_usage(vault_dir: Path, record: UsageRecord) -> Path:
    """把一条用量记录追加到当月账本，返回账本文件路径。"""
    month = record.timestamp[:7]  # YYYY-MM
    row = {SCHEMA_VERSION_FIELD: USAGE_LEDGER_VERSION, **record.as_dict()}
    return append_row(_ledger(vault_dir, month), row)


@dataclass(frozen=True)
class UsageTotals:
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    currency: str


def monthly_totals(vault_dir: Path, year_month: str) -> UsageTotals:
    """汇总某月（``YYYY-MM``）的调用数、token 与估算费用。"""
    calls = input_toks = output_toks = 0
    cost = 0.0
    currency = "CNY"
    for row in read_models(_ledger(vault_dir, year_month), UsageRow):
        calls += 1
        input_toks += row.input_tokens
        output_toks += row.output_tokens
        cost += row.estimated_cost
        currency = row.currency
    return UsageTotals(
        calls=calls,
        input_tokens=input_toks,
        output_tokens=output_toks,
        estimated_cost=round(cost, 6),
        currency=currency,
    )
