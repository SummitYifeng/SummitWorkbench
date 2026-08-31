"""第二大脑问答的稳定 schema（供应商无关，PRD M1-6 / L23）。

模型只能引用实际进入上下文的 Markdown：每条事实/冲突立场都带 ``source_id``，指向召回时
提供给模型的来源标识。事实与建议严格分区（``facts`` vs ``suggestions``），证据冲突并列
（``conflicts``）。是否越界引用未提供来源，由 workflow 在解析后核验。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QaFact(BaseModel):
    """一条有来源支撑的事实。``source_id`` 必须是召回时提供的来源之一。"""

    text: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class QaConflictSide(BaseModel):
    """证据冲突中的一个立场及其来源。"""

    position: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class QaConflict(BaseModel):
    """并列展示的证据冲突：同一话题下至少两个互相矛盾的立场。"""

    topic: str = Field(min_length=1)
    sides: list[QaConflictSide] = Field(min_length=2)


class QaAnswer(BaseModel):
    """一次问答的结构化回答。"""

    summary: str = Field(description="对问题的直接回答；无法回答时留简短说明")
    facts: list[QaFact] = Field(default_factory=list, description="有来源支撑的事实")
    suggestions: list[str] = Field(default_factory=list, description="模型建议，与事实分区")
    conflicts: list[QaConflict] = Field(default_factory=list, description="并列的证据冲突")
    unanswerable: bool = Field(default=False, description="提供的来源不足以回答时为真")

    model_config = {"extra": "ignore"}

    def cited_source_ids(self) -> set[str]:
        """回答中引用到的全部来源 ID（供 workflow 核验是否越界引用）。"""
        cited = {fact.source_id for fact in self.facts}
        for conflict in self.conflicts:
            cited.update(side.source_id for side in conflict.sides)
        return cited
