"""``wb model`` 子命令：云端会议模型冒烟。

联网命令只有在 [models.*] 配置齐全且 Keychain 已存 api key 时才实际调用；
凭据由用户自行存入 Keychain，本 CLI 只引用，绝不打印 api key。
"""

from __future__ import annotations

from pathlib import Path

import typer

from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import load_settings
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.meetings import process_transcript

model_app = typer.Typer(
    name="model",
    help="云端模型接入（M0-6：smoke）。",
    no_args_is_help=True,
    add_completion=False,
)


@model_app.command("smoke")
def smoke(
    transcript_file: Path = typer.Argument(..., help="真实长逐字稿文件路径。"),
    capability: str = typer.Option(
        "meeting", "--capability", help="能力：meeting/qa/review/ranking。"
    ),
    save_usage: bool = typer.Option(
        True, "--save-usage/--no-save-usage", help="是否把用量记录写入 vault 账本。"
    ),
) -> None:
    """用配置的会议模型把一份真实逐字稿结构化，并记录 token 与费用。

    验证长文本、严格 JSON、schema 服从、用量与费用、超时与错误可见性（M0-11）。
    """
    if not transcript_file.is_file():
        typer.echo(f"逐字稿文件不存在：{transcript_file}")
        raise typer.Exit(code=2)

    try:
        cfg = load_model_config(capability)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"配置/凭据错误：{exc}")
        raise typer.Exit(code=2) from exc

    transcript = transcript_file.read_text(encoding="utf-8")
    task_key = f"smoke:{capability}:{transcript_file.name}"

    try:
        processed = process_transcript(
            cfg,
            api_key,
            transcript,
            prompt=prompt,
            merger_prompt=merger_prompt,
            task_key=task_key,
        )
    except LLMError as exc:
        typer.echo(f"✗ 模型冒烟失败：{exc}")
        raise typer.Exit(code=1) from exc

    ex = processed.extraction
    u = processed.usage
    typer.echo("✓ 模型冒烟通过：输出符合会议 schema")
    typer.echo(f"  模型：{u.model_id}  prompt：{processed.prompt_version}  调用次数：{u.attempts}")
    typer.echo(
        f"  token：输入 {u.input_tokens} / 输出 {u.output_tokens}  "
        f"估算费用：{u.estimated_cost} {u.currency}"
    )
    typer.echo(
        f"  提取：事实 {len(ex.facts)} / 决策 {len(ex.decisions)} / "
        f"行动项 {len(ex.action_items)} / 未决 {len(ex.open_questions)} / "
        f"建议 {len(ex.ai_suggestions)}"
    )
    typer.echo(f"  一分钟摘要：{ex.one_minute_summary[:80]}")

    if save_usage:
        ledger = append_usage(load_settings().work_paths().vault_dir, u)
        typer.echo(f"  用量已记入：{ledger}")
