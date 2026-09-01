"""``wb brief``：手动生成晨间简报（M2-8）。

采集飞书日历/任务 + 本地项目状态 → 模型排序（失败走确定性回退）→ 渲染写入当日笔记。
飞书或模型不可用时**降级**而非失败：简报照常生成，健康度首行标注降级原因。
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import default_config_file, load_settings
from summit_workbench.domain.brief import ActionSignal, fallback_ranking
from summit_workbench.observability.status import build_status
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.feishu import FeishuError
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import load_feishu_config
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.brief.brief import generate_brief
from summit_workbench.workflows.brief.collect import FactsSource
from summit_workbench.workflows.brief.feishu_facts import FeishuFactsSource
from summit_workbench.workflows.brief.publish import PublishResult, publish_brief
from summit_workbench.workflows.brief.ranking import RankingResult, rank_actions


def _today(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


def _build_facts_source(day: str, timezone: str) -> tuple[FactsSource | None, str | None]:
    """尽力构建飞书事实源；不可用时返回 (None, 原因)，由简报降级处理。"""
    try:
        cfg = load_feishu_config()
        access = FeishuSession(cfg).access_token()
        client = FeishuClient(cfg, access)
    except (FeishuError, CredentialError, FileNotFoundError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return FeishuFactsSource(client, day=day, timezone=timezone), None


def _build_ranker() -> tuple[object, str | None]:
    """尽力构建模型排序器；不可用时返回一个确定性回退排序闭包。"""

    def fallback(candidates: list[ActionSignal]) -> RankingResult:
        return RankingResult(order=fallback_ranking(candidates), degraded=True)

    try:
        cfg = load_model_config("ranking")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("brief-ranker")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return fallback, f"{type(exc).__name__}: {exc}"

    def rank(candidates: list[ActionSignal]) -> RankingResult:
        return rank_actions(candidates, cfg, api_key, prompt=prompt)

    return rank, None


def brief_command(
    date: str | None = typer.Option(None, "--date", help="指定日期 YYYY-MM-DD（默认今天）。"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="只渲染打印，不写笔记/快照、不发通知。"
    ),
    commit: bool = typer.Option(
        False, "--commit", help="把当日笔记+快照提交到 vault（只暂存简报文件，供 launchd）。"
    ),
    push: bool = typer.Option(
        False, "--push", help="提交后推送到远端（需 --commit；落后 upstream 时不推）。"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出结构化结果（便于脚本）。"),
) -> None:
    """生成今日晨间简报并幂等写入 ``_vault/daily/YYYY-MM-DD.md``。"""
    settings = load_settings()
    paths = settings.work_paths()
    timezone = settings.timezone
    day = date or _today(timezone)

    facts_source, feishu_note = _build_facts_source(day, timezone)
    ranker, _ranker_note = _build_ranker()

    try:
        pending_review = build_status(
            paths.vault_dir, config_file=default_config_file()
        ).backlog.count
    except (OSError, ValueError):
        pending_review = 0

    result = generate_brief(
        paths.work_root,
        paths.vault_dir,
        day=day,
        timezone=timezone,
        facts_source=facts_source,
        rank=ranker,  # type: ignore[arg-type]
        pending_review_count=pending_review,
        write=not dry_run,
        notify=not dry_run,
    )

    if result.ranking.usage is not None:
        append_usage(paths.vault_dir, result.ranking.usage)

    published: PublishResult | None = None
    if commit and not dry_run and result.note_path and result.snapshot_path:
        published = publish_brief(
            paths.vault_dir,
            [result.note_path, result.snapshot_path],
            message=f"chore(brief): 晨间简报 {day}",
            push=push,
        )

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "date": day,
                    "health": result.brief.health.level,
                    "actions": len(result.brief.actions),
                    "meetings": len(result.brief.meetings),
                    "tasks": len(result.brief.tasks),
                    "ranking_degraded": result.ranking.degraded,
                    "note_path": str(result.note_path) if result.note_path else None,
                    "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
                    "feishu_unavailable": feishu_note,
                    "publish": published.status.value if published else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(result.markdown)
    typer.echo("")
    if feishu_note:
        typer.echo(f"ℹ 飞书事实源不可用，已降级：{feishu_note}")
    if result.note_path:
        typer.echo(f"✓ 已写入 {result.note_path}")
        typer.echo(f"✓ 快照 {result.snapshot_path}")
    else:
        typer.echo("（--dry-run：未写入任何文件）")
    if published is not None:
        mark = "✓" if published.status.value.startswith("committed") else "ℹ"
        detail = f"（{published.detail}）" if published.detail else ""
        typer.echo(f"{mark} git：{published.status.value}{detail}")
