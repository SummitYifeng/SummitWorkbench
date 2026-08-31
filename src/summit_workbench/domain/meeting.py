"""会议结构化提取的稳定 schema（供应商无关）。

对应 PRD 3.1.9 结构化会议笔记的机器可读区块。此 schema 不含任何供应商专属字段；
更换模型不改变数据形状。会议明确形成的行动项进 ``action_items``，模型推断的下一步进
``ai_suggestions``，两者不得混写。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """一条明确行动项。target_project 不确定时留空并标 unresolved，不猜测。"""

    description: str
    target_project: str | None = None
    due_date: str | None = None  # YYYY-MM-DD；无期限留空
    evidence: str | None = None  # 逐字稿说话人 + 时间戳/锚点


class MeetingExtraction(BaseModel):
    """一次会议逐字稿的结构化提取结果。"""

    one_minute_summary: str = Field(description="一分钟摘要：结论、重要变化、最需注意事项")
    facts: list[str] = Field(default_factory=list, description="事实与进展")
    decisions: list[str] = Field(default_factory=list, description="已形成决策")
    action_items: list[ActionItem] = Field(default_factory=list, description="明确行动项")
    open_questions: list[str] = Field(default_factory=list, description="未决问题")
    ai_suggestions: list[str] = Field(default_factory=list, description="AI 建议（模型推断）")

    model_config = {"extra": "ignore"}
