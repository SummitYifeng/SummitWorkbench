"""晨间简报的「默认输入装配 + 运行」，供 CLI 与 Web 面板共用（不依赖 typer）。

把「尽力构建飞书事实源 + 排序器、算待确认数、跑 generate_brief、记用量」收敛到一处：
飞书或模型不可用时降级而非失败（简报照常生成，健康度标注降级原因）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.brief import ActionSignal, fallback_ranking
from summit_workbench.observability.status import build_status
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.feishu import FeishuError
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import load_feishu_config
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.brief.brief import BriefResult, RankFn, generate_brief
from summit_workbench.workflows.brief.collect import FactsSource
from summit_workbench.workflows.brief.feishu_facts import FeishuFactsSource
from summit_workbench.workflows.brief.ranking import RankingResult, rank_actions


def today_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


def build_facts_source(day: str, timezone: str) -> tuple[FactsSource | None, str | None]:
    """尽力构建飞书事实源；不可用时返回 (None, 原因)。"""
    try:
        cfg = load_feishu_config()
        access = FeishuSession(cfg).access_token()
        client = FeishuClient(cfg, access)
    except (FeishuError, CredentialError, FileNotFoundError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return FeishuFactsSource(client, day=day, timezone=timezone), None


def build_ranker() -> tuple[RankFn, str | None]:
    """尽力构建模型排序器；不可用时返回确定性回退排序闭包。"""

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


def pending_review_count(vault_dir: Path) -> int:
    try:
        return build_status(vault_dir, config_file=default_config_file()).backlog.count
    except (OSError, ValueError):
        return 0


@dataclass(frozen=True)
class BriefRun:
    result: BriefResult
    feishu_unavailable: str | None


def run_brief(
    *, work_root: Path, vault_dir: Path, timezone: str, day: str, write: bool, notify: bool
) -> BriefRun:
    """装配默认输入并生成简报；记录排序模型用量。"""
    facts, feishu_note = build_facts_source(day, timezone)
    ranker, _ = build_ranker()
    result = generate_brief(
        work_root,
        vault_dir,
        day=day,
        timezone=timezone,
        facts_source=facts,
        rank=ranker,
        pending_review_count=pending_review_count(vault_dir),
        write=write,
        notify=notify,
    )
    if result.ranking.usage is not None:
        append_usage(vault_dir, result.ranking.usage)
    return BriefRun(result=result, feishu_unavailable=feishu_note)
