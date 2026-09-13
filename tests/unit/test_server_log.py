"""G3：本机服务日志（同步失败落盘）的纪律测试。

重点不是"写了日志"，而是：
1. 位置与权限：``~/Library/Logs/summitworkbench-server.log``、0600；
2. 幂等：重复初始化只对应一个 logger，不会写出第二份；
3. 上限：单文件超过 max_bytes 后轮转出 ``.1``；
4. **绝不泄密**：URL、主机名、用户路径、凭据、异常正文都不许出现在日志文本里；
5. 与同步协调器接线：失败的同步真的会留下稳定原因码。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from summit_workbench.domain.sync import SyncState
from summit_workbench.observability import server_log


@pytest.fixture(autouse=True)
def _clean_logger_cache() -> Iterator[None]:
    server_log.reset_server_loggers()
    yield
    server_log.reset_server_loggers()


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_server_log_path_and_mode(tmp_path: Path) -> None:
    assert server_log.server_log_path(tmp_path) == (
        tmp_path / "Library" / "Logs" / "summitworkbench-server.log"
    )
    server_log.log_server_event("server_started", fields={"app_version": "0.4.7"}, home=tmp_path)
    path = server_log.server_log_path(tmp_path)
    assert path.is_file()
    assert (path.stat().st_mode & 0o777) == 0o600
    records = _lines(path)
    assert records and records[0]["event"] == "server_started"
    assert records[0]["component"] == "server"


def test_server_logger_is_idempotent(tmp_path: Path) -> None:
    first = server_log.server_logger(tmp_path)
    second = server_log.server_logger(tmp_path)
    assert first is second, "重复初始化必须复用同一个 logger（不产生第二份）"
    server_log.log_server_event("server_started", home=tmp_path)
    server_log.log_server_event("server_started", home=tmp_path)
    logs = sorted((tmp_path / "Library" / "Logs").glob("*"))
    assert logs == [server_log.server_log_path(tmp_path)], "只允许一个日志文件"
    assert len(_lines(server_log.server_log_path(tmp_path))) == 2


def test_server_log_rotates_at_the_cap(tmp_path: Path) -> None:
    server_log.server_logger(tmp_path, max_bytes=400)
    for _ in range(12):
        server_log.log_sync_outcome(
            state=SyncState.ERROR.value, reasons=[("vault", "unclassified")], home=tmp_path
        )
    path = server_log.server_log_path(tmp_path)
    rotated = path.with_name(path.name + ".1")
    assert rotated.is_file(), "超过 max_bytes 必须轮转出 .1"
    assert path.stat().st_size <= 400


def test_server_log_never_writes_secrets_or_paths(tmp_path: Path) -> None:
    class ExplodingNetworkError(Exception):
        """异常消息里塞满 URL/主机/凭据/路径，日志都不许出现。"""

    secret = "canary-secret-value-1234"
    error = ExplodingNetworkError(
        "https://alice:" + secret + "@github.com/acme/private.git"
        " failed at /Users/alice/Documents/Work/_vault"
    )
    server_log.log_sync_outcome(
        state=SyncState.ERROR.value,
        reasons=[("vault", "auth-rejected"), ("vault", f"https://github.com/{secret}")],
        error=error,
        home=tmp_path,
    )
    server_log.log_push_confirmed_fast_forward(branch="main", home=tmp_path)
    text = server_log.server_log_path(tmp_path).read_text(encoding="utf-8")
    assert secret not in text
    assert "github.com" not in text
    assert "https://" not in text
    assert "/Users/alice" not in text
    assert "failed at" not in text
    # 稳定原因码与异常类名仍在（排障价值不被脱敏吃掉）
    records = _lines(server_log.server_log_path(tmp_path))
    assert records[0]["error_code"] == "auth-rejected"
    assert records[0]["reasons"] == "auth-rejected"
    assert records[0]["error_class"] == "ExplodingNetworkError"
    assert records[0]["reason_count"] == 1
    assert records[0]["dropped_reasons"] == 1
    assert records[1]["error_code"] == "non-fast-forward-graph-verified"
    assert records[1]["branch"] == "main"


def test_safe_code_rejects_paths_and_urls() -> None:
    assert server_log.safe_code("auth-rejected") == "auth-rejected"
    assert server_log.safe_code("../etc/passwd") == "unknown"
    assert server_log.safe_code("https://github.com/a/b") == "unknown"
    assert server_log.safe_code("") == "unknown"
    assert server_log.safe_code(None) == "unknown"
    assert server_log.safe_class_name(RuntimeError("x")) == "RuntimeError"
    assert server_log.safe_class_name(None) == ""


def test_failed_sync_writes_a_stable_reason_code(tmp_path: Path) -> None:
    """接线检查：真正跑一次失败的同步（非 HTTPS 远端），日志里要留下原因码。"""
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend
    from summit_workbench.repositories.git_backend import CommitIdentity
    from summit_workbench.workflows.sync_coordinator import sync_workspace

    vault = tmp_path / "work" / "_vault"
    vault.mkdir(parents=True)
    backend = DulwichGitBackend(vault)
    backend.init()
    (vault / "f.txt").write_text("x", encoding="utf-8")
    backend.add(["f.txt"])
    backend.commit("wb: x", author=CommitIdentity("T", "t@example.com"))
    remote = tmp_path / "remote.git"
    DulwichGitBackend(remote).init(bare=True)
    # 本地路径远端：生产 dulwich 路径要求 HTTPS ⇒ remote-scheme-unsupported
    backend.add_remote("origin", str(remote))
    backend.set_upstream("origin")

    state, _outcomes, _snapshot = sync_workspace(
        vault, work_root=tmp_path / "work", home=tmp_path, backend_kind="dulwich"
    )
    assert state is SyncState.REMOTE_SCHEME_UNSUPPORTED
    records = _lines(server_log.server_log_path(tmp_path))
    assert [record["event"] for record in records] == ["sync_failed"]
    assert records[0]["error_code"] == "remote-scheme-unsupported"
    assert records[0]["state"] == SyncState.REMOTE_SCHEME_UNSUPPORTED.value
    assert "remote.git" not in server_log.server_log_path(tmp_path).read_text(encoding="utf-8")
