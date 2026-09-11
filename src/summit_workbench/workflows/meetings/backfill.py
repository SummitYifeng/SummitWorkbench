"""历史补导（PRD M1-7）：按显式日期范围补导本地逐字稿清单。

- 先证据后建议、幂等可续跑：已处理的会议按状态账本跳过。
- 默认只沉淀知识（结构化笔记）；``include_actions=True`` 才生成带 ``historical`` 标记的审批候选。
- 费用/预算预估与门槛判断在 :mod:`summit_workbench.domain.backfill`（纯规则）。

输入源为本地逐字稿目录（Note 兜底同链路），不依赖尚未确认的「按日期枚举全部会议」飞书 API。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

import httpx
from pydantic import SecretStr

from summit_workbench.domain.backfill import BackfillEstimate, estimate_backfill
from summit_workbench.domain.pipeline import (
    ProcessingState,
    SourceKind,
    local_idempotency_key,
)
from summit_workbench.domain.review import ReviewEntry
from summit_workbench.prompts import Prompt
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.repositories.meeting_archive import slugify, transcript_stem
from summit_workbench.repositories.meeting_state import latest_task
from summit_workbench.repositories.review_page import (
    RefreshOutcome,
    refresh_review_page,
    review_path,
)
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, LocalMutationResult
from summit_workbench.workflows.meetings.archive import (
    ArchiveReport,
    DiscoveredMeeting,
    archive_meeting,
)
from summit_workbench.workflows.meetings.process_archived import process_archived_transcript
from summit_workbench.workflows.meetings.processor import estimate_tokens
from summit_workbench.workflows.meetings.review_candidates import candidates_from_note

# 视为「已补导」的终态：结构化完成或已进入/走完审批。
_DONE_STATES = frozenset(
    {
        ProcessingState.PROCESSED,
        ProcessingState.PENDING_REVIEW,
        ProcessingState.APPLIED,
        ProcessingState.IGNORED,
    }
)
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class BackfillItem:
    path: Path
    title: str
    date: str
    idem_key: str
    input_tokens: int
    done: bool


@dataclass(frozen=True)
class BackfillItemResult:
    item: BackfillItem
    action: str  # processed | skipped-existing | failed
    note_path: Path | None = None
    candidates: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class BackfillRunReport:
    results: list[BackfillItemResult]
    processed: int
    skipped: int
    failed: int
    candidates: int
    operation_ids: tuple[str, ...] = ()


def _run_local[T](
    vault_dir: Path,
    action: str,
    mutation: Callable[[str], LocalMutationOutcome[T]],
    runner: Callable[..., object] | None,
) -> tuple[T, str | None]:
    if runner is None:
        return mutation("").business_return, None
    typed = cast(LocalMutationResult[T], runner(vault_dir, action, mutation))
    return typed.business_return, typed.operation_id


def _derive_date(meta: dict[str, object], path: Path) -> str | None:
    raw = meta.get("date")
    if isinstance(raw, str):
        try:
            date.fromisoformat(raw)
            return raw
        except ValueError:
            pass
    match = _DATE_PREFIX_RE.match(path.stem)
    return match.group(1) if match else None


def _derive_title(body: str, path: Path) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return _DATE_PREFIX_RE.sub("", path.stem).strip("-") or path.stem


_TRANSCRIPT_SUFFIXES = frozenset({".md", ".txt"})

# 逐字稿体积上限。这是**产品规则**，必须由 workflow 层统一负责：web 抽屉在流式上传时
# 就返回 413，但 CLI（`wb meeting import` / `backfill`）此前完全没有检查，能直接把一个
# 12 MiB 文件送进模型（实测预估 419 万 input token）。上限放在这里，两条路径共用同一数值，
# 不会再出现「抽屉拦住、CLI 放行」的口径分裂。
MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024


def _transcript_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if source.is_dir():
        return sorted(
            p for p in source.iterdir() if p.is_file() and p.suffix.lower() in _TRANSCRIPT_SUFFIXES
        )
    return []


def _is_oversized(path: Path) -> bool:
    try:
        return path.stat().st_size > MAX_TRANSCRIPT_BYTES
    except OSError:
        # 读不到大小时不在这里拦；后续读取会以真实错误暴露。
        return False


def oversized_transcripts(source: Path) -> list[Path]:
    """列出因超过 :data:`MAX_TRANSCRIPT_BYTES` 而被跳过的逐字稿。

    调用方（CLI）用它把「为什么少导了几份」显式告诉用户；静默跳过会让用户误以为已导入。
    """
    return [path for path in _transcript_files(source) if _is_oversized(path)]


def _mtime_date(path: Path) -> str:
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def scan_for_import(vault_dir: Path, source: Path) -> list[BackfillItem]:
    """扫描本地逐字稿用于按需导入：不做日期区间过滤，缺日期回退文件修改日期。

    面向「妙记按需 + 手动兜底」的常态工作流：把手动下载的逐字稿丢进一个文件夹，一条命令
    归档 + 结构化。``.md``/``.txt`` 均可；日期取 frontmatter/文件名前缀，缺失回退 mtime。
    """
    items: list[BackfillItem] = []
    for path in _transcript_files(source):
        if _is_oversized(path):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            continue
        meta, body, _error = _parsed(path, text)
        meeting_date = _derive_date(meta, path) or _mtime_date(path)
        idem_key = local_idempotency_key(text)
        prior = latest_task(vault_dir, idem_key)
        done = prior is not None and prior.state in _DONE_STATES
        items.append(
            BackfillItem(
                path=path,
                title=_derive_title(body, path),
                date=meeting_date,
                idem_key=idem_key,
                input_tokens=estimate_tokens(text),
                done=done,
            )
        )
    return items


def scan_local_transcripts(
    vault_dir: Path, source: Path, *, since: str, until: str
) -> list[BackfillItem]:
    """扫描本地逐字稿，按 ``[since, until]`` 过滤，标注是否已补导（可续跑）。"""
    items: list[BackfillItem] = []
    for path in _transcript_files(source):
        if _is_oversized(path):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            continue
        meta, body, _error = _parsed(path, text)
        meeting_date = _derive_date(meta, path)
        if meeting_date is None or not (since <= meeting_date <= until):
            continue
        idem_key = local_idempotency_key(text)
        prior = latest_task(vault_dir, idem_key)
        done = prior is not None and prior.state in _DONE_STATES
        items.append(
            BackfillItem(
                path=path,
                title=_derive_title(body, path),
                date=meeting_date,
                idem_key=idem_key,
                input_tokens=estimate_tokens(text),
                done=done,
            )
        )
    return items


def _parsed(path: Path, text: str) -> tuple[dict[str, object], str, str | None]:
    note = load_note(path)
    return note.meta, note.body, note.parse_error


def plan_backfill(
    items: list[BackfillItem],
    cfg: ModelConfig,
    *,
    month_spent: float,
    soft_limit: float | None,
) -> BackfillEstimate:
    """预估待补导会议数、token 与费用（输入 token 取本地文件实际长度）。"""
    pending = [item for item in items if not item.done]
    return estimate_backfill(
        pending_input_tokens=[item.input_tokens for item in pending],
        output_tokens_per_meeting=cfg.max_output_tokens,
        pricing=cfg.pricing,
        already_done=len(items) - len(pending),
        month_spent=month_spent,
        soft_limit=soft_limit,
    )


def run_backfill(
    vault_dir: Path,
    items: list[BackfillItem],
    cfg: ModelConfig,
    api_key: SecretStr,
    *,
    prompt: Prompt,
    merger_prompt: Prompt,
    include_actions: bool = False,
    now: datetime | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] | None = None,
    local_mutation: Callable[..., object] | None = None,
) -> BackfillRunReport:
    """逐场补导；已完成的跳过（可续跑）。默认只沉淀知识，不生成行动候选。"""
    results: list[BackfillItemResult] = []
    operation_ids: list[str] = []
    processed = skipped = failed = candidates_total = 0
    for item in items:
        if item.done:
            skipped += 1
            results.append(BackfillItemResult(item, "skipped-existing"))
            continue
        text = item.path.read_text(encoding="utf-8")
        meeting = DiscoveredMeeting(title=item.title, date=item.date, source=SourceKind.LOCAL_FILE)

        def _fetch(_meeting: DiscoveredMeeting, _text: str = text) -> str:
            return _text

        def save_archive(
            _operation_id: str,
            archive_meeting_item: DiscoveredMeeting = meeting,
            archive_item: BackfillItem = item,
            archive_fetch: Callable[[DiscoveredMeeting], str] = _fetch,
        ) -> LocalMutationOutcome[ArchiveReport]:
            return LocalMutationOutcome(
                archive_meeting(vault_dir, archive_meeting_item, archive_fetch, now=now),
                (
                    vault_dir / "_signals" / "meeting-state" / "log.jsonl",
                    vault_dir
                    / "meetings"
                    / "transcripts"
                    / f"{transcript_stem(archive_item.date, slugify(archive_item.title))}.md",
                ),
            )

        archived, operation_id = _run_local(
            vault_dir,
            "meetings/archive",
            save_archive,
            local_mutation,
        )
        if operation_id is not None:
            operation_ids.append(operation_id)
        if archived.path is None:
            failed += 1
            results.append(BackfillItemResult(item, "failed", reason="归档未产生逐字稿"))
            continue
        report = process_archived_transcript(
            vault_dir,
            archived.path,
            cfg,
            api_key,
            prompt=prompt,
            merger_prompt=merger_prompt,
            task_key=item.idem_key,
            client=client,
            sleep=sleep,
            now=now,
            local_mutation=local_mutation,  # type: ignore[arg-type]
        )
        if report.operation_id is not None:
            operation_ids.append(report.operation_id)
        if report.action == "failed":
            failed += 1
            results.append(BackfillItemResult(item, "failed", reason=report.reason))
            continue
        count = 0
        if include_actions and report.note_path is not None:
            entries = candidates_from_note(report.note_path, vault_dir, historical=True)
            if entries:

                def save_review(
                    _operation_id: str, review_entries: list[ReviewEntry] = entries
                ) -> LocalMutationOutcome[RefreshOutcome]:
                    return LocalMutationOutcome(
                        refresh_review_page(vault_dir, review_entries), (review_path(vault_dir),)
                    )

                _refresh, operation_id = _run_local(
                    vault_dir,
                    "meetings/review",
                    save_review,
                    local_mutation,
                )
                if operation_id is not None:
                    operation_ids.append(operation_id)
                count = len(entries)
        candidates_total += count
        if report.action == "skipped-existing":
            skipped += 1
        else:
            processed += 1
        results.append(
            BackfillItemResult(item, report.action, note_path=report.note_path, candidates=count)
        )
    return BackfillRunReport(
        results=results,
        processed=processed,
        skipped=skipped,
        failed=failed,
        candidates=candidates_total,
        operation_ids=tuple(operation_ids),
    )
