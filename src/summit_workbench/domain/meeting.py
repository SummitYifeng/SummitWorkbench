"""会议结构化提取的稳定 schema（供应商无关）。

对应 PRD 3.1.9 结构化会议笔记的机器可读区块。此 schema 不含任何供应商专属字段；
更换模型不改变数据形状。会议明确形成的行动项进 ``action_items``，模型推断的下一步进
``ai_suggestions``，两者不得混写。
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

_ANCHOR_RE = re.compile(
    r"(?:\d{1,2}:)?\d{1,2}:\d{2}|(?:段落|第)\s*\d+|(?:line|paragraph)\s*\d+", re.I
)


def _validate_evidence(value: str) -> str:
    """证据必须含时间戳或稳定段落锚点，只有泛泛描述不算可追溯引用。"""
    cleaned = value.strip()
    if not cleaned or _ANCHOR_RE.search(cleaned) is None:
        raise ValueError("evidence 必须包含逐字稿时间戳或稳定段落锚点")
    return cleaned


class SourcedStatement(BaseModel):
    """一条带原文定位的事实或未决问题。"""

    text: str = Field(min_length=1)
    evidence: str

    _evidence_anchor = field_validator("evidence")(_validate_evidence)


class Decision(BaseModel):
    """一条已形成决策；项目不确定时留空，不猜测。"""

    description: str = Field(min_length=1)
    target_project: str | None = None
    evidence: str

    _evidence_anchor = field_validator("evidence")(_validate_evidence)


class ActionItem(BaseModel):
    """一条明确行动项。target_project 不确定时留空并标 unresolved，不猜测。"""

    description: str = Field(min_length=1)
    target_project: str | None = None
    due_date: str | None = None  # YYYY-MM-DD；无期限留空
    evidence: str  # 逐字稿说话人 + 时间戳/锚点

    _evidence_anchor = field_validator("evidence")(_validate_evidence)

    @field_validator("due_date")
    @classmethod
    def _valid_due_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("due_date 必须是有效的 YYYY-MM-DD") from exc
        return value


class MeetingExtraction(BaseModel):
    """一次会议逐字稿的结构化提取结果。"""

    one_minute_summary: str = Field(description="一分钟摘要：结论、重要变化、最需注意事项")
    facts: list[SourcedStatement] = Field(default_factory=list, description="事实与进展")
    decisions: list[Decision] = Field(default_factory=list, description="已形成决策")
    action_items: list[ActionItem] = Field(default_factory=list, description="明确行动项")
    open_questions: list[SourcedStatement] = Field(default_factory=list, description="未决问题")
    ai_suggestions: list[str] = Field(default_factory=list, description="AI 建议（模型推断）")

    model_config = {"extra": "ignore"}
