"""线程知识录入的 AI 结构化 schema（P1：推进日志消化 + AI 产物索引）。

延续快速捕捉的韧性约定：模型不可用 / 输出非法时整体回退为「无摘要」，原文绝不丢；
关联线程由调用方在 UI 选定并本地解析（registry），不经模型臆造。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class LogTag(StrEnum):
    """推进日志的类型标签（R3：进展 / 决策 / 行动 / 待办 / 阻塞）。"""

    PROGRESS = "进展"
    DECISION = "决策"
    ACTION = "行动"
    TODO = "待办"
    BLOCKED = "阻塞"


class LogDigest(BaseModel):
    """模型对一段推进日志的消化结果；解析失败时回退为空摘要。"""

    summary: str = ""
    involved: list[str] = []
    tags: list[LogTag] = []
    next_step: str | None = None
    decision: str | None = None


def fallback_log_digest() -> LogDigest:
    """模型不可用 / 输出非法时的兜底：原文照存，仅无摘要。"""
    return LogDigest()


class ArtifactKind(StrEnum):
    """AI 产物（阶段总结/PRD/背景包/timeline 等）的分类。"""

    SUMMARY = "summary"
    PRD = "prd"
    BACKGROUND_PACK = "background-pack"
    TIMELINE = "timeline"
    OTHER = "other"


class ArtifactIndex(BaseModel):
    """模型对一段产物文本的索引结果（命名 + 摘要 + 分类）。"""

    title: str = ""
    summary: str = ""
    kind: ArtifactKind = ArtifactKind.OTHER


def fallback_artifact_index(title_hint: str | None = None) -> ArtifactIndex:
    """模型不可用 / 输出非法时的兜底：标题取用户提示或首行，无摘要。"""
    return ArtifactIndex(title=title_hint or "")
