"""公共重试/退避与 Retry-After 解析测试（LHF #3，上游无关）。"""

from __future__ import annotations

from email.utils import format_datetime

import httpx
import pytest

from summit_workbench.providers._resilient import (
    build_client,
    parse_retry_after,
    send_with_retry,
)


class Transient(Exception):
    def __init__(self, retryable: bool = True, retry_after: float | None = None) -> None:
        super().__init__("transient")
        self.retryable = retryable
        self.retry_after = retry_after


def _run(attempt, *, sleep=None, max_retries=3):
    slept: list[float] = []
    send = sleep if sleep is not None else slept.append
    result = send_with_retry(
        attempt,
        retry_on=(Transient,),
        is_retryable=lambda exc: isinstance(exc, Transient) and exc.retryable,
        retry_after=lambda exc: getattr(exc, "retry_after", None),
        max_retries=max_retries,
        base_backoff=0.5,
        sleep=send,
    )
    return result, slept


def test_success_first_try_no_sleep():
    result, slept = _run(lambda n: f"ok-{n}")
    assert result == "ok-1"
    assert slept == []


def test_retries_then_succeeds_exponential_backoff():
    calls = {"n": 0}

    def attempt(n: int) -> str:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise Transient()
        return "done"

    result, slept = _run(attempt)
    assert result == "done"
    assert calls["n"] == 3
    assert slept == [0.5, 1.0]  # 0.5 * 2**0, 0.5 * 2**1


def test_exhausts_and_raises_last():
    def attempt(n: int) -> str:
        raise Transient()

    with pytest.raises(Transient):
        _run(attempt)


def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    def attempt(n: int) -> str:
        calls["n"] += 1
        raise Transient(retryable=False)

    with pytest.raises(Transient):
        _run(attempt)
    assert calls["n"] == 1


def test_unlisted_exception_propagates():
    def attempt(n: int) -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _run(attempt)


def test_retry_after_overrides_backoff():
    calls = {"n": 0}

    def attempt(n: int) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise Transient(retry_after=12.0)
        return "ok"

    result, slept = _run(attempt)
    assert result == "ok"
    assert slept == [12.0]


def test_parse_retry_after_seconds():
    resp = httpx.Response(429, headers={"Retry-After": "5"})
    assert parse_retry_after(resp) == 5.0


def test_parse_retry_after_missing():
    assert parse_retry_after(httpx.Response(429)) is None


def test_parse_retry_after_invalid():
    resp = httpx.Response(429, headers={"Retry-After": "soon"})
    assert parse_retry_after(resp) is None


def test_parse_retry_after_http_date_future():
    from datetime import UTC, datetime, timedelta

    future = datetime.now(UTC) + timedelta(seconds=30)
    resp = httpx.Response(429, headers={"Retry-After": format_datetime(future)})
    val = parse_retry_after(resp)
    assert val is not None and 20 <= val <= 31


def test_parse_retry_after_http_date_past_is_zero():
    from datetime import UTC, datetime, timedelta

    past = datetime.now(UTC) - timedelta(seconds=30)
    resp = httpx.Response(429, headers={"Retry-After": format_datetime(past)})
    assert parse_retry_after(resp) == 0.0


def test_build_client_sets_keepalive_expiry():
    client = build_client(10.0, keepalive_expiry=15.0)
    try:
        assert client.timeout.read == 10.0
    finally:
        client.close()
