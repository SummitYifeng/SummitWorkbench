"""兼容入口：知识正文规范化的唯一实现位于 :mod:`domain.knowledge_normalization`。"""

from __future__ import annotations

from summit_workbench.domain.knowledge_normalization import (
    NormalizedKnowledgeBody,
    format_normalization_error,
    normalize_generated_body,
)

__all__ = ["NormalizedKnowledgeBody", "format_normalization_error", "normalize_generated_body"]
