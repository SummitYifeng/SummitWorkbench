"""上游无关的 HTTP 重试/退避与长驻客户端构造（韧性加固 LHF #3）。

**根治的故障类**：``providers/llm/client.py`` 早已有指数退避重试（超时 / 429 / 5xx，
区分可重试与否，L41）；而 ``providers/feishu/{client,auth}.py`` 仍是 **单发**——一次
瞬时网络抖动（连接重置、网关 502、限流 429）就让整趟拉取报废、无谓地把失败上抛到
用户面前。两处退避循环本可共用，且都漏了尊重 ``Retry-After`` 头。

对策：把退避循环抽成 :func:`send_with_retry`，飞书与 LLM 共用；识别 ``Retry-After``
（:func:`parse_retry_after`，秒数或 HTTP 日期），限流时按服务端指定时长而非盲目退避。
长驻客户端用 :func:`build_client` 统一构造，带 ``keepalive_expiry`` 防复用半开连接
（连接在池里静置过久、对端早已关闭，复用即触发一次必然失败的首请求）。

保持既有语义（NFR-6）：非重试类错误立即上抛、绝不静默吞错；重试仅覆盖瞬时故障。
"""

from __future__ import annotations

import email.utils
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

_DEFAULT_MAX_RETRIES = 3  # 初次失败后最多再重试 3 次（共 4 次调用）
_DEFAULT_BASE_BACKOFF = 0.5
# 长驻客户端连接的存活上限：静置超过此秒数的 keep-alive 连接不再复用，避免半开连接。
_DEFAULT_KEEPALIVE_EXPIRY = 30.0


def build_client(
    timeout: float, *, keepalive_expiry: float = _DEFAULT_KEEPALIVE_EXPIRY
) -> httpx.Client:
    """构造长驻 :class:`httpx.Client`：统一超时与连接存活上限。

    ``keepalive_expiry`` 限制 keep-alive 连接在池中的静置时长，超时的连接下次不复用而是
    重建，规避「对端早已关闭、本地池仍握着」的半开连接在首个请求上必然失败的问题。
    """
    limits = httpx.Limits(keepalive_expiry=keepalive_expiry)
    return httpx.Client(timeout=timeout, limits=limits)


def parse_retry_after(response: httpx.Response) -> float | None:
    """解析 ``Retry-After`` 头为「还需等待的秒数」；缺失/非法返回 ``None``。

    该头有两种合法形式：非负整数秒数，或 HTTP 日期（RFC 7231）。日期形式换算成相对当下的
    剩余秒数（已过期则视为 0）。解析不了就当作没有此头，交给调用方回退到指数退避。
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def send_with_retry[T](
    attempt: Callable[[int], T],
    *,
    retry_on: tuple[type[Exception], ...],
    is_retryable: Callable[[Exception], bool],
    retry_after: Callable[[Exception], float | None] = lambda _exc: None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_backoff: float = _DEFAULT_BASE_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """带指数退避的重试执行器（上游无关）。

    :param attempt: 单次尝试；入参为第几次（从 1 计），成功返回结果、失败抛异常。
    :param retry_on: 参与重试判定的异常类型；其余异常直接上抛。
    :param is_retryable: 判定某个被捕获的异常是否属于可重试的瞬时故障。
    :param retry_after: 从异常取服务端指定的等待秒数（如 429 的 ``Retry-After``）；返回
        ``None`` 表示未指定，回退到指数退避。
    :param max_retries: 初次失败后最多再重试几次。
    :param base_backoff: 指数退避基数；第 n 次失败后等 ``base_backoff * 2**(n-1)`` 秒。
    :param sleep: 休眠函数，便于测试注入。

    非重试类错误、或已耗尽重试次数时，原样上抛最后一次的异常（NFR-6：失败必须可见）。
    """
    for n in range(1, max_retries + 2):
        try:
            return attempt(n)
        except retry_on as exc:
            if n <= max_retries and is_retryable(exc):
                delay = retry_after(exc)
                if delay is None:
                    delay = base_backoff * (2 ** (n - 1))
                sleep(delay)
                continue
            raise
    raise AssertionError("unreachable")  # 循环要么 return 要么 raise
