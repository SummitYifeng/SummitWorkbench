"""G3：本机服务日志（同步失败的落盘线索）。

现状：``~/Library/Logs/summitworkbench-panel.log`` 里只有 Swift launcher 与少量 webapp
的 JSON 行，Python 侧的同步/推送/拉取失败**从不落盘**——"昨晚为什么没同步"只能看内存
快照或重启 App。

这里复用既有 :class:`~summit_workbench.observability.structured_logging.StructuredLogger`
（JSONL + 轮转 + 脱敏 + 进程锁），另开一个**服务自有**的文件
``~/Library/Logs/summitworkbench-server.log``（0600），与 launcher 的 panel 日志互不干扰。

写入纪律（与 ``scripts/secret_scan.py`` 的取向一致）：

- 只写**稳定原因码**（``credentials-missing`` / ``auth-rejected`` / ``non-fast-forward`` …）、
  状态名、计数与异常**类名**；
- 绝不写 URL、主机名、文件路径、凭据、正文，也绝不 ``str(exc)``——异常消息里可能有 URL
  或 Keychain 细节。落盘前用白名单正则再挡一道，不合形状的值替换为占位符。

**绝不写进 vault**：vault 的内容会被同步、会被提交（P0-10 的 logs/ 是工作台内容，
不是机器日志）。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from summit_workbench.observability.structured_logging import StructuredLogger

SERVER_LOG_FILENAME = "summitworkbench-server.log"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
FILE_MODE = 0o600
COMPONENT = "server"

# 稳定原因码：小写 kebab-case（domain.sync 的既有词汇表）。不合形状一律替换。
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# 事件名：小写 snake_case（本模块自己定义的事件词汇表）。
_SAFE_EVENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
# 异常类名：Python 标识符形状。只写类名，绝不写异常文本。
_SAFE_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

_loggers: dict[Path, StructuredLogger] = {}
_loggers_lock = threading.Lock()


def _write(logger: StructuredLogger, event: str, **kwargs: Any) -> bool:
    """best-effort 写一行：日志设施绝不能让调用方（同步/推送）失败。

    只吞磁盘/权限类错误（``OSError``）；真正的编程错误照常抛出，避免把 bug 藏起来。
    返回是否真的写成功，便于测试与上层自检。
    """
    try:
        logger.log(event, **kwargs)
    except OSError:
        return False
    return True


def server_log_path(home: Path | None = None) -> Path:
    """``<home>/Library/Logs/summitworkbench-server.log``（与 panel 日志同目录）。"""
    base = Path(home) if home is not None else Path.home()
    return base / "Library" / "Logs" / SERVER_LOG_FILENAME


def server_logger(home: Path | None = None, *, max_bytes: int | None = None) -> StructuredLogger:
    """取（或建）该 home 的服务 logger；重复调用是幂等的，不会产生第二个文件句柄。

    ``StructuredLogger`` 本身无缓冲、每次写入都 open/close，所以"幂等"在这里的含义是
    **同一个路径只对应一个 logger 实例**：已存在的实例绝不被替换（``max_bytes`` 只在
    首次创建时生效），重复初始化不会写出两份或产生额外文件。
    """
    path = server_log_path(home)
    with _loggers_lock:
        logger = _loggers.get(path)
        if logger is None:
            logger = StructuredLogger(
                path,
                component=COMPONENT,
                max_bytes=max_bytes if max_bytes is not None else DEFAULT_MAX_BYTES,
                new_mode=FILE_MODE,
            )
            _loggers[path] = logger
        return logger


def safe_code(value: str | None, *, fallback: str = "unknown") -> str:
    """白名单化稳定原因码；不合形状（含任何路径/URL 形状）一律替换为 fallback。"""
    if value and _SAFE_CODE.fullmatch(value):
        return value
    return fallback


def safe_class_name(error: BaseException | None) -> str:
    """异常类名（只写类名，绝不写异常消息）。"""
    if error is None:
        return ""
    name = type(error).__name__
    return name if _SAFE_CLASS.fullmatch(name) else "unknown"


def safe_event(value: str | None, *, fallback: str = "unknown-event") -> str:
    """白名单化事件名（snake_case）；不合形状一律替换。"""
    if value and _SAFE_EVENT.fullmatch(value):
        return value
    return fallback


def log_server_event(
    event: str,
    *,
    error_code: str | None = None,
    level: str = "info",
    fields: dict[str, Any] | None = None,
    home: Path | None = None,
) -> None:
    """写一行服务日志；事件名与原因码都经白名单化。"""
    _write(
        server_logger(home),
        safe_event(event),
        level=level,
        error_code=safe_code(error_code, fallback="") if error_code else "",
        fields=fields,
    )


def log_sync_outcome(
    *,
    state: str,
    reasons: Sequence[tuple[str, str]] = (),
    error: BaseException | None = None,
    home: Path | None = None,
) -> None:
    """同步/推送失败落一行：稳定原因码 + 计数 + 异常类名（绝无 URL/路径/凭据/正文）。"""
    raw_codes = [code for _, code in reasons if code]
    codes = sorted({code for code in raw_codes if _SAFE_CODE.fullmatch(code)})
    dropped = len(raw_codes) - len([code for code in raw_codes if _SAFE_CODE.fullmatch(code)])
    if not codes and error is not None:
        codes = ["unclassified"]
    primary = codes[0] if codes else "unspecified"
    fields: dict[str, Any] = {
        "state": safe_code(state),
        "reason_count": len(codes),
    }
    if codes:
        fields["reasons"] = ",".join(codes)
    if dropped:
        # 只报"有几条没通过白名单"，绝不写被丢弃的原值（那正是可能含 URL/路径的东西）。
        fields["dropped_reasons"] = dropped
    error_class = safe_class_name(error)
    if error_class:
        fields["error_class"] = error_class
    server_logger(home).log("sync_failed", level="warning", error_code=primary, fields=fields)


def log_push_confirmed_fast_forward(*, branch: str | None = None, home: Path | None = None) -> None:
    """D9：把"dulwich 误报分叉、图复核确认是真快进后强推成功"写进日志。"""
    fields: dict[str, Any] = {"reason": "dulwich-timestamp-lag"}
    if branch:
        fields["branch"] = branch
    _write(
        server_logger(home),
        "push_confirmed_fast_forward",
        level="warning",
        error_code="non-fast-forward-graph-verified",
        fields=fields,
    )


def reset_server_loggers() -> None:
    """测试辅助：清空 logger 缓存（不改磁盘内容）。"""
    with _loggers_lock:
        _loggers.clear()


__all__ = [
    "DEFAULT_MAX_BYTES",
    "SERVER_LOG_FILENAME",
    "log_push_confirmed_fast_forward",
    "log_server_event",
    "log_sync_outcome",
    "reset_server_loggers",
    "safe_class_name",
    "safe_code",
    "safe_event",
    "server_log_path",
    "server_logger",
]
