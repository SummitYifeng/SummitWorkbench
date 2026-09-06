"""中央日志/诊断脱敏器（P1-05）。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?:secret|token|password|authorization|cookie|credential|api[_-]?key|prompt|response|body)",
    re.IGNORECASE,
)
_AUTH = re.compile(r"(?i)(authorization|cookie|set-cookie|x-wb-session-token)\s*[:=]\s*[^,\n]+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_REMOTE_USERINFO = re.compile(r"(?i)(https?://)([^/\s:@]+):([^@\s]+)@")
_CANARY = re.compile(r"(?i)\b(?:canary[-_][a-z0-9_-]+|(?:secret|token|pat|api[_-]?key)=[^\s,;]+)\b")
_BODY = re.compile(r"(?is)\b(?:meeting|transcript|prompt|model response)\s+body\s*[:=]\s*[^\n]+")
_HOME_PATH = re.compile(r"/Users/[^/\s]+(?:/[^\s]*)?")


def redact_text(value: str) -> str:
    """脱敏任意可见文本；不承诺保留秘密的长度或形状。"""
    redacted = _REMOTE_USERINFO.sub(r"\1[redacted]@", value)
    redacted = _AUTH.sub(lambda match: f"{match.group(1)}: [redacted]", redacted)
    redacted = _BEARER.sub("Bearer [redacted]", redacted)
    redacted = _BODY.sub("[redacted body]", redacted)
    redacted = _CANARY.sub("[redacted]", redacted)
    return _HOME_PATH.sub("~/[redacted]", redacted)


def redact_fields(fields: Mapping[str, Any]) -> dict[str, str | int | float | bool | None]:
    """只保留诊断所需标量；敏感键和复杂正文统一丢弃/替换。"""
    result: dict[str, str | int | float | bool | None] = {}
    for key, value in fields.items():
        if _SENSITIVE_KEY.search(key):
            result[key] = "[redacted]"
        elif isinstance(value, str):
            result[key] = redact_text(value)
        elif isinstance(value, int | float | bool) or value is None:
            result[key] = value
        else:
            result[key] = "[redacted]"
    return result


__all__ = ["redact_fields", "redact_text"]
