"""模型用量账本持久化：JSONL 落盘到 ``_vault/_signals/model-usage/``。

按月一个 ``YYYY-MM.jsonl`` 文件，每次调用追加一行，便于按日/月汇总（NFR-8）。
只做读写与汇总，不决定预算是否触发告警（那是 observability 的职责）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from summit_workbench.providers.llm.usage import UsageRecord

MODEL_USAGE_SUBDIR = ("_signals", "model-usage")


def _usage_dir(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*MODEL_USAGE_SUBDIR)


def append_usage(vault_dir: Path, record: UsageRecord) -> Path:
    """把一条用量记录追加到当月账本，返回账本文件路径。"""
    month = record.timestamp[:7]  # YYYY-MM
    ledger_dir = _usage_dir(vault_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger_dir / f"{month}.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")
    return ledger


@dataclass(frozen=True)
class UsageTotals:
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    currency: str


def monthly_totals(vault_dir: Path, year_month: str) -> UsageTotals:
    """汇总某月（``YYYY-MM``）的调用数、token 与估算费用。"""
    ledger = _usage_dir(vault_dir) / f"{year_month}.jsonl"
    calls = input_toks = output_toks = 0
    cost = 0.0
    currency = "CNY"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            calls += 1
            input_toks += int(row.get("input_tokens", 0))
            output_toks += int(row.get("output_tokens", 0))
            cost += float(row.get("estimated_cost", 0.0))
            currency = row.get("currency", currency)
    return UsageTotals(
        calls=calls,
        input_tokens=input_toks,
        output_tokens=output_toks,
        estimated_cost=round(cost, 6),
        currency=currency,
    )
