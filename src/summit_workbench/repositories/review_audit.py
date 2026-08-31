"""审批写回的幂等账本与人类可读审计归档。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from summit_workbench.domain.review import CandidateDecision, ReviewEntry

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


def _ledger(vault_dir: Path) -> Path:
    return vault_dir.joinpath(*REVIEW_ACTIONS_SUBDIR, "log.jsonl")


def completed_ids(vault_dir: Path) -> set[str]:
    path = _ledger(vault_dir)
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("result") in {"applied", "rejected"}:
                ids.add(str(row["candidate_id"]))
    return ids


def completed_decisions(vault_dir: Path, task_key: str) -> set[CandidateDecision]:
    """读取某会议已完成候选的历史裁决，供部分成功后的最终状态收口。"""
    path = _ledger(vault_dir)
    if not path.is_file():
        return set()
    decisions: set[CandidateDecision] = set()
    prefix = f"{task_key}#"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("candidate_id", "")).startswith(prefix) and row.get("result") in {
            "applied",
            "rejected",
        }:
            decisions.add(CandidateDecision(str(row["decision"])))
    return decisions


def make_execution_record(
    entry: ReviewEntry,
    *,
    destination: str,
    result: str,
    external_id: str | None = None,
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
    )


def append_execution(vault_dir: Path, record: ExecutionRecord) -> Path:
    ledger = _ledger(vault_dir)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return ledger


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
                    f"- 目标：{record.destination}",
                    f"- 结果：{record.result}",
                    f"- external_id：{record.external_id or ''}",
                ]
            )
        )
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm}\n---\n\n# 会议审批审计\n\n" + "\n\n".join(blocks) + "\n"
    path.write_text(content, encoding="utf-8")
    return path
