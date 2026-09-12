"""会议逐字稿导入链路（LEGACY-APP-SPLIT-PLAN Step 14 / S5）。

从 ``legacy_app`` 抽出 ``_run_web_import``：把一份本地逐字稿归档 + 结构化 + 生成审批
候选，复用 backfill 链路与集中式写入门。函数体逐字保留。

模型配置入口来自 ``webapp.model_config``。``routers/meetings.py``（R11）导入本符号后
调用，迁移后测试 patch 的是
``summit_workbench.webapp.routers.meetings._run_web_import``（§6-R3）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.model_config import _load_model_config_for_context
from summit_workbench.workflows.local_mutation import run_local_mutation


def _run_web_import(
    ctx: WebContext,
    transcript_path: Path,
    *,
    local_mutation: Callable[..., object] | None = None,
) -> dict[str, object]:
    """把一份本地逐字稿全自动归档 + 结构化 + 生成审批候选（复用 backfill 链路）。

    与 wb meeting import 同一套幂等逻辑；Web 侧按产品约定走全自动（不二次确认），
    软预算只报告不阻断（PRD：预算是提醒线，不是停机线）。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.observability.status import load_budget_settings
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError
    from summit_workbench.repositories.usage_ledger import monthly_totals
    from summit_workbench.workflows.meetings.backfill import (
        plan_backfill,
        run_backfill,
        scan_for_import,
    )

    items = scan_for_import(ctx.vault_dir, transcript_path)
    if not items:
        return {"ok": False, "message": "未识别为可导入的逐字稿（需要 .md/.txt 且内容非空）"}

    # 先检查幂等账本：重复导入已经完成的逐字稿不应因为当前模型凭据不可用而
    # 被误报为“模型未配置”，也不应再次调用模型或写入归档。
    if all(item.done for item in items):
        skipped = len(items)
        lines = [f"处理 0、跳过 {skipped}、失败 0、生成候选 0"]
        return {
            "ok": True,
            "status": "success",
            "message": "导入完成：" + "；".join(lines) + "（幂等，未重复调用模型）",
            "details": lines,
            "operation_ids": [],
            "estimate": {
                "pending": 0,
                "already_done": skipped,
                "est_input_tokens": 0,
                "est_output_tokens": 0,
                "est_cost": 0,
                "currency": "—",
                "projected_month_cost": 0,
                "soft_limit": None,
                "crosses_soft_budget": False,
            },
        }

    try:
        cfg = _load_model_config_for_context(ctx, "meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return {"ok": False, "status": "failed", "message": f"导入未启动（模型未配置？）：{exc}"}

    month = datetime.now(ZoneInfo(ctx.timezone)).strftime("%Y-%m")
    month_spent = monthly_totals(ctx.vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(ctx.provider_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)

    report = run_backfill(
        ctx.vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=True,
        local_mutation=local_mutation or run_local_mutation,
    )
    lines = [
        f"处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}、"
        f"生成候选 {report.candidates}"
    ]
    for result in report.results:
        if result.action == "failed":
            lines.append(f"✗ {result.item.date} {result.item.title}：{result.reason}")
    operation_ids = list(report.operation_ids)
    operation_note = f" · operation_id：{operation_ids[-1]}" if operation_ids else ""
    status = (
        "success"
        if report.failed == 0
        else ("partial" if report.processed or report.skipped else "failed")
    )
    message_prefix = {
        "success": "导入完成：",
        "partial": "导入部分完成：",
        "failed": "导入失败：",
    }[status]
    return {
        "ok": report.failed == 0,
        "status": status,
        "message": message_prefix + "；".join(lines) + operation_note,
        "details": lines,
        "operation_ids": operation_ids,
        "estimate": {
            "pending": est.pending,
            "already_done": est.already_done,
            "est_input_tokens": est.est_input_tokens,
            "est_output_tokens": est.est_output_tokens,
            "est_cost": est.est_cost,
            "currency": est.currency,
            "projected_month_cost": est.projected_month_cost,
            "soft_limit": soft_limit,
            "crosses_soft_budget": est.crosses_soft_budget,
        },
    }


__all__ = ["_run_web_import"]
