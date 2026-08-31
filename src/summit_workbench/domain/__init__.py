"""领域类型与规则。

纯逻辑层：定义稳定 schema、词表与校验规则，不访问文件系统或网络
（见开发计划模块边界）。
"""

from summit_workbench.domain.vault import (
    NOTE_TYPES,
    REQUIRED_FRONTMATTER,
    STATUS_VOCAB,
    ValidationIssue,
    validate_note,
)

__all__ = [
    "NOTE_TYPES",
    "REQUIRED_FRONTMATTER",
    "STATUS_VOCAB",
    "ValidationIssue",
    "validate_note",
]
