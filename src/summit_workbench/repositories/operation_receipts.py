"""工作台写操作的本机回执与请求去重。"""

from __future__ import annotations

import fcntl
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.config.app_support import runtime_dir
from summit_workbench.repositories._atomic import atomic_write_text


@dataclass(frozen=True)
class OperationResult:
    response: dict[str, object]
    replayed: bool = False
    status_code: int = 200


class OperationConflict(ValueError):
    """请求标识已用于不同内容。"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class OperationReceiptStore:
    """每个 workspace 一份本机回执；正文只留摘要，不保存用户输入。"""

    def __init__(self, workspace_id: str, *, home: Path | None = None) -> None:
        self.directory = runtime_dir(workspace_id, home) / "operations"

    @staticmethod
    def _key(request_id: str) -> str:
        if (
            not request_id
            or len(request_id) > 128
            or not all(char.isalnum() or char in "-_" for char in request_id)
        ):
            raise ValueError("X-WB-Request-Id 格式无效")
        return hashlib.sha256(request_id.encode("utf-8")).hexdigest()

    @contextmanager
    def _locked(self, key: str) -> Iterator[Path]:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        path = self.directory / f"{key}.json"
        lock_path = self.directory / f"{key}.lock"
        with lock_path.open("a+b") as lock:
            lock_path.chmod(0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield path
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read(path: Path) -> dict[str, object] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(data, dict):
            return None
        return data

    @staticmethod
    def _write(path: Path, data: dict[str, object]) -> None:
        atomic_write_text(
            path,
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            ensure_parents=True,
            new_mode=0o600,
        )

    def run(
        self,
        request_id: str,
        payload: object,
        action: Callable[[], dict[str, object]],
    ) -> OperationResult:
        """先登记 processing，再执行一次；中断留下 unknown，后续请求绝不重放动作。"""
        key = self._key(request_id)
        request_digest = _digest(payload)
        with self._locked(key) as path:
            record = self._read(path)
            if record is not None:
                if record.get("request_digest") != request_digest:
                    raise OperationConflict("该操作标识已用于不同内容，请刷新页面后再试")
                if record.get("status") == "completed":
                    response = record.get("response")
                    if isinstance(response, dict):
                        return OperationResult(response=response, replayed=True)
                return OperationResult(
                    response={
                        "ok": False,
                        "operation_id": request_id,
                        "status": "unknown",
                        "message": "本次操作结果暂时无法确认；请先查看操作回执，不要重复提交。",
                    },
                    replayed=True,
                    status_code=202,
                )

            started = datetime.now(UTC).isoformat()
            self._write(
                path,
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "request_digest": request_digest,
                    "status": "processing",
                    "stage": "registered",
                    "started_at": started,
                    "updated_at": started,
                },
            )
            response = action()
            completed = datetime.now(UTC).isoformat()
            commit = response.get("commit")
            commit_status = commit.get("status") if isinstance(commit, dict) else None
            push = response.get("push")
            push_status = push.get("status") if isinstance(push, dict) else None
            self._write(
                path,
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "request_digest": request_digest,
                    "status": "completed",
                    "stage": "response_recorded",
                    "business_write": (
                        "succeeded" if response.get("ok") is True else "not_confirmed"
                    ),
                    "commit_status": commit_status,
                    "push_status": push_status,
                    "started_at": started,
                    "updated_at": completed,
                    "response": response,
                },
            )
            return OperationResult(response=response)

    def get(self, request_id: str) -> dict[str, object] | None:
        key = self._key(request_id)
        with self._locked(key) as path:
            record = self._read(path)
        if record is None:
            return None
        status = record.get("status", "unknown")
        if status == "processing":
            # 只有取得同一请求锁后才会读到 processing；若操作仍活着，读者会等到锁释放。
            # 因此遗留 processing 表示进程中断，证据不足以确认业务写入结果。
            status = "unknown"
        return {
            "ok": True,
            "operation_id": request_id,
            "status": status,
            "stage": record.get("stage", "unknown"),
            "business_write": record.get("business_write", "unknown"),
            "commit_status": record.get("commit_status"),
            "push_status": record.get("push_status"),
            "started_at": record.get("started_at"),
            "updated_at": record.get("updated_at"),
            "response": record.get("response"),
        }


__all__ = ["OperationConflict", "OperationReceiptStore", "OperationResult"]
