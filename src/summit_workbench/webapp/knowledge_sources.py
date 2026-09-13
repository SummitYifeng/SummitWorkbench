"""只读「知识来源」白名单与正文展示预算（LEGACY-APP-SPLIT-PLAN Step 1 / B11）。

这三个符号被两个不同入口共用，**必须只有一份白名单**，否则会出现一条更宽的旁路：

- 审批页的来源只读入口（`/api/review/source`）；
- 问答页的来源面板（`/api/sources/read`）。

它们既不属于某一个 router（两边都要用），也不该继续留在 `legacy_app.py` 里随
那个 3457 行的兼容文件一起漂移，因此作为第一个 seam 抽出。

**兼容层**：`webapp/legacy_app.py` 继续再导出这三个名字（`tests/unit/test_webapi.py`
直接从 `legacy_app` import `SOURCE_BODY_DISPLAY_CHARS`），迁移期保持该引用有效；
待蓝图 Step 16 收尾时再统一摘除。
"""

from __future__ import annotations

from pathlib import Path

# 允许作为「知识来源」只读打开的 vault 顶层目录；审批来源只读入口与问答来源面板
# 共用同一份白名单，避免出现一个更宽的旁路。
KNOWLEDGE_SOURCE_ROOTS = frozenset(
    {
        "projects",
        "meetings",
        "logs",
        "artifacts",
        "inboxes",
        "daily",
        "reviews",
        "insights",
        # ---- 工作知识库（方案 A：工作线主线）新增根 ----
        # 不加这些根，`路径#区块` 引用点开会 404（来源面板与审批只读入口共用本白名单）。
        "hii",
        "it",
        "community",
        "hr",
        "decisions",
        "index",
    }
)

# 单次只读来源返回的正文展示预算（字符）：超过则截断并置 ``truncated=true``，
# 避免把超长正文整段塞进面板；文件字节数超过 256 KiB 仍然直接拒绝。
SOURCE_BODY_DISPLAY_CHARS = 100_000


def _is_knowledge_source(relative: Path) -> bool:
    """相对路径是否落在允许只读打开的知识来源白名单内。"""
    if relative.as_posix() == "inbox.md":
        return True
    return bool(relative.parts) and relative.parts[0] in KNOWLEDGE_SOURCE_ROOTS


__all__ = [
    "KNOWLEDGE_SOURCE_ROOTS",
    "SOURCE_BODY_DISPLAY_CHARS",
]
