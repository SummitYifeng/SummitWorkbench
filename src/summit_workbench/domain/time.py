"""Shared business-time rules."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def business_date(now: datetime) -> str:
    """Return the Beijing business date; naive datetimes are not guessable."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("业务日期需要带时区的 datetime")
    return now.astimezone(BUSINESS_TIMEZONE).date().isoformat()


__all__ = ["BUSINESS_TIMEZONE", "business_date"]
