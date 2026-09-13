"""``wb ask``：本地召回 + 云端模型带来源问答（M1-6）。"""

from __future__ import annotations

from pathlib import Path

import typer

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import default_config_file, load_settings
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.kb_index import default_index_path
from summit_workbench.repositories.qa_insight import (
    QaInsightInput,
    qa_insight_date,
    save_qa_insight,
)
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.ask.ask import AskResult, answer_question


def _qa_targets(config_file: Path | None) -> tuple[Path, Path, str | None]:
    """解析 ``(vault_dir, config_file, workspace_id)``。

    优先级：显式 ``--config-file`` > 旧的默认配置 ``~/.config/summit_workbench/config.toml`` >
    **本机 active workspace 的 profile**。

    最后一条是必要的：App 把 provider 配置存在
    ``Application Support/SummitWorkbench/profiles/<workspace_id>/config.toml``，CLI 过去完全
    看不到它，于是「App 里配好了模型、命令行却用不了」。
    """
    if config_file is not None:
        return load_settings().work_paths().vault_dir, config_file.expanduser(), None
    default = default_config_file()
    if default.is_file():
        return load_settings().work_paths().vault_dir, default, None
    active = resolve_active_workspace()
    if active.config_file is not None and active.paths is not None:
        return active.paths.vault_dir, active.config_file, active.workspace_id
    return load_settings().work_paths().vault_dir, default, None


def ask_command(
    question: str = typer.Argument(..., help="要向第二大脑提出的问题。"),
    save: bool = typer.Option(False, "--save", help="把回答存为 qa-insight（默认不保存）。"),
    project: str | None = typer.Option(None, "--project", help="仅在指定项目相关的笔记中召回。"),
    limit: int = typer.Option(8, "--limit", min=1, max=32, help="最多召回的来源块数。"),
    trace: bool = typer.Option(True, "--trace/--no-trace", help="打印检索轨迹。"),
    use_index: bool = typer.Option(
        True,
        "--index/--no-index",
        help="用检索索引（块级 FTS5 + 多信号融合）；--no-index 走旧版子串扫描。",
    ),
    config_file: Path | None = typer.Option(
        None, "--config-file", help="provider 配置；默认取本机 active workspace 的 profile。"
    ),
) -> None:
    """带来源地回答问题；模型只能引用实际召回进上下文的本地 Markdown。"""
    vault_dir, resolved_config, workspace_id = _qa_targets(config_file)
    try:
        cfg = load_model_config("qa", resolved_config, workspace_id=workspace_id)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"✗ 问答未启动：{exc}")
        raise typer.Exit(code=2) from exc

    try:
        result = answer_question(
            vault_dir,
            question,
            cfg,
            api_key,
            prompt=prompt,
            project=project,
            limit=limit,
            index_path=default_index_path() if use_index else None,
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

    _print(result, saved_path, show_trace=trace)


def _print(result: AskResult, saved_path: object, *, show_trace: bool = False) -> None:
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

    if show_trace and result.trace is not None:
        typer.echo("\n—— 检索轨迹 ——")
        typer.echo(result.trace.summary())
    if result.sources:
        typer.echo("\n召回来源：" + "、".join(f"[[{c.source_id}]]" for c in result.sources))
    if result.dropped_sources:
        typer.echo("⚠ 已剔除越界引用（未进入上下文的来源）：" + "、".join(result.dropped_sources))
    if saved_path is not None:
        typer.echo(f"\n✓ 已保存 qa-insight：{saved_path}")
