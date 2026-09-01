"""用量记录、费用估算与账本读写测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from summit_workbench.providers.llm.client import CompletionResult, Usage
from summit_workbench.providers.llm.config import ModelConfig, ModelPricing
from summit_workbench.providers.llm.usage import record_from_result
from summit_workbench.repositories.usage_ledger import append_usage, monthly_totals

CFG = ModelConfig(
    capability="meeting",
    model_id="m1",
    base_url="https://x/v1",
    credential_account="shared",
    pricing=ModelPricing(currency="CNY", input_per_mtok=2.0, output_per_mtok=6.0),
)


def _result(inp, out):
    return CompletionResult(text="{}", usage=Usage(inp, out), model_id="m1", attempts=2)


def test_record_from_result_computes_cost():
    now = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    rec = record_from_result(CFG, _result(1_000_000, 500_000), task_key="t1", now=now)
    assert rec.capability == "meeting"
    assert rec.attempts == 2
    assert rec.task_key == "t1"
    # 1e6*2 + 5e5*6 = 2e6 + 3e6 = 5e6 → /1e6 = 5.0
    assert rec.estimated_cost == 5.0
    assert rec.currency == "CNY"
    assert rec.timestamp.startswith("2026-08-31")


def test_ledger_append_and_totals(tmp_path):
    vault = tmp_path / "_vault"
    now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    r1 = record_from_result(CFG, _result(1000, 200), task_key="a", now=now)
    r2 = record_from_result(CFG, _result(3000, 400), task_key="b", now=now)
    ledger = append_usage(vault, r1)
    append_usage(vault, r2)
    assert ledger.name == "2026-08.jsonl"

    totals = monthly_totals(vault, "2026-08")
    assert totals.calls == 2
    assert totals.input_tokens == 4000
    assert totals.output_tokens == 600


def test_written_usage_row_carries_schema_version(tmp_path):
    """用量行落盘时打上 schema_version，便于将来账本格式迁移（正式使用前加固）。"""
    import json

    from summit_workbench.repositories._schema import USAGE_LEDGER_VERSION

    vault = tmp_path / "_vault"
    now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    ledger = append_usage(vault, record_from_result(CFG, _result(1000, 200), task_key="a", now=now))
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert row["schema_version"] == USAGE_LEDGER_VERSION
    # 版本字段不干扰既有汇总。
    assert monthly_totals(vault, "2026-08").calls == 1


def test_totals_empty_month(tmp_path):
    totals = monthly_totals(tmp_path / "_vault", "2026-01")
    assert totals.calls == 0
    assert totals.estimated_cost == 0.0


def test_corrupt_tail_line_does_not_break_totals(tmp_path):
    """半截末行不再让整月费用汇总崩溃：好行照常计入（LHF #2）。"""
    import warnings

    from summit_workbench.repositories._jsonl import CorruptLogLine

    vault = tmp_path / "_vault"
    now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    ledger = append_usage(vault, record_from_result(CFG, _result(1000, 200), task_key="a", now=now))
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"input_tokens": 5, "estimated')  # 半截行
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CorruptLogLine)
        totals = monthly_totals(vault, "2026-08")
    assert totals.calls == 1
    assert totals.input_tokens == 1000
