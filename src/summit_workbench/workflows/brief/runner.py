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
from summit_workbench.providers.feishu.errors import FeishuAuthError
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.feishu_auth_state import write_auth_state
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.brief.brief import BriefResult, RankFn, generate_brief
from summit_workbench.workflows.brief.collect import FactsSource
from summit_workbench.workflows.brief.feishu_facts import FeishuFactsSource
from summit_workbench.workflows.brief.ranking import RankingResult, rank_actions


def today_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


@dataclass(frozen=True)
class FeishuOutcome:
    """构建飞书事实源的结局：不可用原因 + 是否属于「需重新授权」。"""

    reason: str | None = None  # None 表示可用
    needs_reauthorize: bool = False


def build_facts_source(day: str, timezone: str) -> tuple[FactsSource | None, FeishuOutcome]:
    """尽力构建飞书事实源；不可用时返回 (None, 原因)。

    token 失效（refresh_token 过期/被吊销）会被识别为 ``needs_reauthorize``，供上层
    降级出简报的同时把「请重新授权」这件事持久化并推到 ``wb status``（加固 #4）。
    """
    try:
        cfg = load_feishu_config()
        access = FeishuSession(cfg).access_token()
        client = FeishuClient(cfg, access)
    except FeishuAuthError as exc:
        return None, FeishuOutcome(f"{type(exc).__name__}: {exc}", exc.needs_reauthorize)
    except (FeishuError, CredentialError, FileNotFoundError, ValueError) as exc:
        return None, FeishuOutcome(f"{type(exc).__name__}: {exc}")
    return FeishuFactsSource(client, day=day, timezone=timezone), FeishuOutcome()


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
    feishu_needs_reauthorize: bool = False


def run_brief(
    *, work_root: Path, vault_dir: Path, timezone: str, day: str, write: bool, notify: bool
) -> BriefRun:
    """装配默认输入并生成简报；记录排序模型用量与飞书授权健康度。"""
    facts, feishu = build_facts_source(day, timezone)
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
    # 持久化飞书授权健康度（仅真实运行）：token 失效时 wb status 会据此提示重新授权。
    # 只有明确「拿到过飞书结论」时才更新——配置缺失等模糊情形不误标为需重新授权。
    if write and (facts is not None or feishu.needs_reauthorize):
        write_auth_state(
            vault_dir,
            needs_reauthorize=feishu.needs_reauthorize,
            day=day,
            detail=feishu.reason,
        )
    return BriefRun(
        result=result,
        feishu_unavailable=feishu.reason,
        feishu_needs_reauthorize=feishu.needs_reauthorize,
    )
