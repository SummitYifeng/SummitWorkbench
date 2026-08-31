"""``wb ask``：本地召回 + 云端模型带来源问答（M1-6）。"""

from __future__ import annotations

import typer

from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import load_settings
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.qa_insight import (
    QaInsightInput,
    qa_insight_date,
    save_qa_insight,
)
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.ask.ask import AskResult, answer_question


def ask_command(
    question: str = typer.Argument(..., help="要向第二大脑提出的问题。"),
    save: bool = typer.Option(False, "--save", help="把回答存为 qa-insight（默认不保存）。"),
    project: str | None = typer.Option(
        None, "--project", help="仅在指定项目相关的笔记中召回。"
    ),
    limit: int = typer.Option(6, "--limit", min=1, max=20, help="最多召回的来源笔记数。"),
) -> None:
    """带来源地回答问题；模型只能引用实际召回进上下文的本地 Markdown。"""
    vault_dir = load_settings().work_paths().vault_dir
    try:
        cfg = load_model_config("qa")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"✗ 问答未启动：{exc}")
        raise typer.Exit(code=2) from exc

    try:
        result = answer_question(
            vault_dir, question, cfg, api_key, prompt=prompt, project=project, limit=limit
        )
    except (LLMError, ValueError) as exc:
        typer.echo(f"✗ 问答失败：{exc}")
        raise typer.Exit(code=1) from exc

    if result.usage is not None:
        append_usage(vault_dir, result.usage)

    saved_path = None
    if save and not result.answer.unanswerable and result.sources:
        outcome = save_qa_insight(
            vault_dir,
            QaInsightInput(
                question=result.question,
                answer=result.answer,
                source_ids=[c.source_id for c in result.sources],
                model_id=cfg.model_id,
                prompt_version=prompt.version_label,
                date=qa_insight_date(),
            ),
        )
        saved_path = outcome.path

    _print(result, saved_path)


def _print(result: AskResult, saved_path: object) -> None:
    answer = result.answer
    typer.echo(answer.summary)

    if answer.facts:
        typer.echo("\n事实（带来源）：")
        for fact in answer.facts:
            typer.echo(f"  • {fact.text}  ← [[{fact.source_id}]]")
    if answer.suggestions:
        typer.echo("\n建议（模型推断）：")
        for suggestion in answer.suggestions:
            typer.echo(f"  • {suggestion}")
    if answer.conflicts:
        typer.echo("\n证据冲突（并列）：")
        for conflict in answer.conflicts:
            typer.echo(f"  ▸ {conflict.topic}")
            for side in conflict.sides:
                typer.echo(f"      - {side.position}  ← [[{side.source_id}]]")

    if result.sources:
        typer.echo("\n召回来源：" + "、".join(f"[[{c.source_id}]]" for c in result.sources))
    if result.dropped_sources:
        typer.echo(
            "⚠ 已剔除越界引用（未进入上下文的来源）：" + "、".join(result.dropped_sources)
        )
    if saved_path is not None:
        typer.echo(f"\n✓ 已保存 qa-insight：{saved_path}")
