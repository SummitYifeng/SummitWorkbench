"""持久化读写层：vault Markdown、状态、错误队列、用量账本。

只负责读写与解析，不决定行动优先级、不绕过领域规则（见模块边界）。
"""

from summit_workbench.repositories.vault import (
    ParsedNote,
    check_vault,
    iter_markdown_files,
    parse_frontmatter,
)

__all__ = [
    "ParsedNote",
    "check_vault",
    "iter_markdown_files",
    "parse_frontmatter",
]
