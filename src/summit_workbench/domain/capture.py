"""快速捕捉的分类 schema（M4 的 web 形态先行版）。

纯规则：kind 二分类（承诺/想法）+ 可选截止；#项目 标签由调用方本地解析
（:func:`summit_workbench.workflows.capture.extract_project_tags`），不经模型，避免臆造项目名。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CaptureKind(StrEnum):
    """快速捕捉的性质：承诺/待办 vs 想法/备忘。"""

    TASK = "task"
    IDEA = "idea"


class CaptureClassification(BaseModel):
    """模型对一行快速捕捉的分类结果；解析失败时整体回退为想法。"""

    kind: CaptureKind
    due_date: str | None = None
    involves_others: bool = False


def fallback_classification() -> CaptureClassification:
    """模型不可用 / 输出非法时的兜底：一律按想法归档，绝不丢数据。"""
    return CaptureClassification(kind=CaptureKind.IDEA)
