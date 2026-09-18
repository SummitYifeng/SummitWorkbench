"""审批写回的幂等账本与人类可读审计归档。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from summit_workbench.domain.review import CandidateDecision, ReviewEntry
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories._jsonl import append_row, read_models

REVIEW_ACTIONS_SUBDIR = ("_signals", "review-actions")


@dataclass(frozen=True)
class ExecutionRecord:
    timestamp: str
    candidate_id: str
    decision: str
    ai_original: str
    final_description: str
    target_project: str | None
    route: str | None
    due_date: str | None
    destination: str
    result: str
    external_id: str | None = None
    operation_id: str | None = None
    start_at: str | None = None


class ExecutionRecordRow(BaseModel):
    """幂等账本的一行（显式 schema，``extra=\"ignore\"`` 容忍漂移，ADR 0017 语义）。

    读侧经 :func:`read_models` 逐行校验：一条半截/缺键坏行只跳过并隔离进
    ``.quarantine``，不再让 apply 的幂等判定整体崩溃（P0-3）。
    """

    model_config = ConfigDict(extra="ignore")

    timestamp: str
    candidate_id: str
    decision: str
    ai_original: str
    final_description: str
    target_project: str | None = None
    route: str | None = None
    due_date: str | None = None
    destination: str
    result: str
    external_id: str | None = None
    operation_id: str | None = None
    start_at: str | None = None


def _ledger(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*REVIEW_ACTIONS_SUBDIR, "log.jsonl")


def completed_ids(vault_dir: Path) -> set[str]:
    rows = read_models(_ledger(vault_dir), ExecutionRecordRow)
    return {row.candidate_id for row in rows if row.result in {"applied", "rejected"}}


def completed_decisions(vault_dir: Path, task_key: str) -> set[CandidateDecision]:
    """读取某会议已完成候选的历史裁决，供部分成功后的最终状态收口。"""
    prefix = f"{task_key}#"
    decisions: set[CandidateDecision] = set()
    for row in read_models(_ledger(vault_dir), ExecutionRecordRow):
        if row.candidate_id.startswith(prefix) and row.result in {"applied", "rejected"}:
            decisions.add(CandidateDecision(row.decision))
    return decisions


def make_execution_record(
    entry: ReviewEntry,
    *,
    destination: str,
    result: str,
    external_id: str | None = None,
    operation_id: str | None = None,
    now: datetime | None = None,
) -> ExecutionRecord:
    item = entry.candidate
    return ExecutionRecord(
        timestamp=(now or datetime.now(UTC)).isoformat(),
        candidate_id=item.candidate_id,
        decision=item.decision.value,
        ai_original=entry.ai_original,
        final_description=item.description,
        target_project=item.target_project,
        route=item.route.value if item.route else None,
        due_date=item.due_date,
        destination=destination,
        result=result,
        external_id=external_id,
        operation_id=operation_id,
        start_at=item.start_at,
    )


def append_execution(vault_dir: Path, record: ExecutionRecord) -> Path:
    """追加一条执行记录（与其它 JSONL 日志同一套 append 写法）。"""
    return append_row(_ledger(vault_dir), asdict(record))


def archive_executions(
    vault_dir: Path, records: list[ExecutionRecord], *, now: datetime | None = None
) -> Path:
    timestamp = now or datetime.now(UTC)
    path = vault_dir / "review" / "archive" / f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {
        "date": timestamp.date().isoformat(),
        "type": "approval-page",
        "status": "archived",
        "project": "global",
    }
    blocks: list[str] = []
    for record in records:
        decision = CandidateDecision(record.decision)
        blocks.append(
            "\n".join(
                [
                    f"## {record.candidate_id}",
                    "",
                    f"- 裁决：{decision.value}",
                    f"- AI 原值：{record.ai_original}",
                    f"- 用户最终值：{record.final_description}",
                    f"- target_project：{record.target_project or ''}",
                    f"- route：{record.route or ''}",
                    f"- due_date：{record.due_date or ''}",
                    f"- start_at：{record.start_at or ''}",
                    f"- 目标：{record.destination}",
                    f"- 结果：{record.result}",
                    f"- external_id：{record.external_id or ''}",
                    f"- operation_id：{record.operation_id or ''}",
                ]
            )
        )
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm}\n---\n\n# 会议审批审计\n\n" + "\n\n".join(blocks) + "\n"
    # P0-06：持久化审计归档走原子写（唯一临时文件 + fsync + replace），不留半截文件。
    atomic_write_text(path, content)
    return path
