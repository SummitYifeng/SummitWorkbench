"""晨间简报的「默认输入装配 + 运行」，供 CLI 与 Web 面板共用（不依赖 typer）。

把「尽力构建飞书事实源 + 排序器、算待确认数、跑 generate_brief、记用量」收敛到一处：
飞书或模型不可用时降级而非失败（简报照常生成，健康度标注降级原因）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.config.paths import resolve_work_paths
from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import default_config_file
from summit_workbench.domain.brief import ActionSignal, fallback_ranking
from summit_workbench.domain.time import business_date
from summit_workbench.observability.status import build_status
from summit_workbench.prompts import load_prompt
from summit_workbench.providers.feishu import FeishuError
from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.config import load_feishu_config
from summit_workbench.providers.feishu.errors import FeishuAuthError
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import LLMError
from summit_workbench.repositories.feishu_auth_state import write_auth_state
from summit_workbench.repositories.usage_ledger import append_usage
from summit_workbench.workflows.brief.brief import BriefResult, RankFn, generate_brief
from summit_workbench.workflows.brief.collect import FactsSource
from summit_workbench.workflows.brief.feishu_facts import FeishuFactsSource
from summit_workbench.workflows.brief.ranking import RankingResult, rank_actions


def today_iso(timezone: str) -> str:
    return business_date(datetime.now(UTC))


@dataclass(frozen=True)
class FeishuOutcome:
    """构建飞书事实源的结局：不可用原因 + 是否属于「需重新授权」。"""

    reason: str | None = None  # None 表示可用
    needs_reauthorize: bool = False


def build_facts_source(
    day: str,
    timezone: str,
    *,
    lock_root: Path | None = None,
    config_file: Path | None = None,
    workspace_id: str | None = None,
) -> tuple[FactsSource | None, FeishuOutcome]:
    """尽力构建飞书事实源；不可用时返回 (None, 原因)。

    token 失效（refresh_token 过期/被吊销）会被识别为 ``needs_reauthorize``，供上层
    降级出简报的同时把「请重新授权」这件事持久化并推到 ``wb status``（加固 #4）。

    :param lock_root: 工作区锁根（``WorkspacePaths.lock_root``）。Feishu refresh 的
        token 轮换临界区锁在这里，与同 workspace 的写者共用同一 ``.wb.lock``（P0-06）。
    """
    try:
        if config_file is None and workspace_id is None:
            cfg = load_feishu_config()
        else:
            cfg = load_feishu_config(config_file, workspace_id=workspace_id)
        access = FeishuSession(cfg, lock_root=lock_root).access_token()
        client = FeishuClient(cfg, access)
    except FeishuAuthError as exc:
        return None, FeishuOutcome(f"{type(exc).__name__}: {exc}", exc.needs_reauthorize)
    except (FeishuError, CredentialError, FileNotFoundError, ValueError) as exc:
        return None, FeishuOutcome(f"{type(exc).__name__}: {exc}")
    return FeishuFactsSource(client, day=day, timezone=timezone), FeishuOutcome()


def build_ranker(
    *, config_file: Path | None = None, workspace_id: str | None = None
) -> tuple[RankFn, str | None]:
    """尽力构建模型排序器；不可用时返回确定性回退排序闭包。"""

    def fallback(candidates: list[ActionSignal]) -> RankingResult:
        return RankingResult(order=fallback_ranking(candidates), degraded=True)

    try:
        if workspace_id is not None:
            from summit_workbench.workflows.settings_connections import model_config

            cfg = model_config(
                capability="ranking",
                config_file=config_file or default_config_file(),
                workspace_id=workspace_id,
            )
        else:
            from summit_workbench.providers.llm import load_model_config

            cfg = load_model_config("ranking", config_file)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("brief-ranker")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return fallback, f"{type(exc).__name__}: {exc}"

    def rank(candidates: list[ActionSignal]) -> RankingResult:
        return rank_actions(candidates, cfg, api_key, prompt=prompt)

    return rank, None


def pending_review_count(vault_dir: Path, *, config_file: Path | None = None) -> int:
    try:
        return build_status(
            vault_dir, config_file=config_file or default_config_file()
        ).backlog.count
    except (OSError, ValueError):
        return 0


@dataclass(frozen=True)
class BriefRun:
    result: BriefResult
    feishu_unavailable: str | None
    feishu_needs_reauthorize: bool = False
    persisted_paths: tuple[Path, ...] = ()


def run_brief(
    *,
    work_root: Path,
    vault_dir: Path,
    timezone: str,
    day: str,
    write: bool,
    notify: bool,
    config_file: Path | None = None,
    workspace_id: str | None = None,
) -> BriefRun:
    """装配默认输入并生成简报；记录排序模型用量与飞书授权健康度。"""
    # P0-06：Feishu refresh 的锁根来自单一解析入口（默认形态 = vault 容器 = work_root）。
    lock_root = resolve_work_paths(work_root=work_root, vault_dir=vault_dir).lock_root
    facts, feishu = build_facts_source(
        day,
        timezone,
        lock_root=lock_root,
        config_file=config_file,
        workspace_id=workspace_id,
    )
    ranker, _ = build_ranker(config_file=config_file, workspace_id=workspace_id)
    result = generate_brief(
        work_root,
        vault_dir,
        day=day,
        timezone=timezone,
        facts_source=facts,
        rank=ranker,
        pending_review_count=pending_review_count(vault_dir, config_file=config_file),
        write=write,
        notify=notify,
    )
    persisted_paths: list[Path] = []
    if result.snapshot_path is not None:
        persisted_paths.append(result.snapshot_path)
    if result.note_path is not None:
        persisted_paths.append(result.note_path)
    if result.ranking.usage is not None:
        usage_path = append_usage(vault_dir, result.ranking.usage)
        persisted_paths.append(usage_path)
    # 持久化飞书授权健康度（仅真实运行）：token 失效时 wb status 会据此提示重新授权。
    # 只有明确「拿到过飞书结论」时才更新——配置缺失等模糊情形不误标为需重新授权。
    if write and (facts is not None or feishu.needs_reauthorize):
        auth_state_path = write_auth_state(
            vault_dir,
            needs_reauthorize=feishu.needs_reauthorize,
            day=day,
            detail=feishu.reason,
        )
        persisted_paths.append(auth_state_path)
    return BriefRun(
        result=result,
        feishu_unavailable=feishu.reason,
        feishu_needs_reauthorize=feishu.needs_reauthorize,
        persisted_paths=tuple(dict.fromkeys(persisted_paths)),
    )
