"""模型失败队列：每个会议任务一个可覆盖的最新错误记录。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

MODEL_ERRORS_SUBDIR = ("_signals", "model-errors")


@dataclass(frozen=True)
class ModelErrorRecord:
    timestamp: str
    task_key: str
    model_id: str
    prompt_version: str
    stage: str
    attempts: int
    reason: str
    transcript_path: str


def _error_path(vault_dir: Path, task_key: str) -> Path:
    digest = hashlib.sha256(task_key.encode("utf-8")).hexdigest()[:24]
    return vault_dir.joinpath(*MODEL_ERRORS_SUBDIR, f"{digest}.json")


def record_model_error(
    vault_dir: Path,
    *,
    task_key: str,
    model_id: str,
    prompt_version: str,
    stage: str,
    attempts: int,
    reason: str,
    transcript_path: Path,
    now: datetime | None = None,
) -> Path:
    path = _error_path(vault_dir, task_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = ModelErrorRecord(
        timestamp=(now or datetime.now(UTC)).isoformat(),
        task_key=task_key,
        model_id=model_id,
        prompt_version=prompt_version,
        stage=stage,
        attempts=attempts,
        reason=reason,
        transcript_path=str(transcript_path),
    )
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def clear_model_error(vault_dir: Path, task_key: str) -> None:
    """显式重跑成功后移除该任务的活动错误；状态日志仍保留失败审计。"""
    path = _error_path(vault_dir, task_key)
    if path.exists():
        path.unlink()
