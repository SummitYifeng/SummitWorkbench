"""只读「知识来源」白名单与正文展示预算（LEGACY-APP-SPLIT-PLAN Step 1 / B11）。

这三个符号被两个不同入口共用，**必须只有一份白名单**，否则会出现一条更宽的旁路：

- 审批页的来源只读入口（`/api/review/source`）；
- 来源查看器（`/api/sources/read`）。

它们既不属于某一个 router（两边都要用），也不该继续留在 `legacy_app.py` 里随
那个 3457 行的兼容文件一起漂移，因此作为第一个 seam 抽出。

**兼容层**：`webapp/legacy_app.py` 继续再导出这三个名字（`tests/unit/test_webapi.py`
直接从 `legacy_app` import `SOURCE_BODY_DISPLAY_CHARS`），迁移期保持该引用有效；
待蓝图 Step 16 收尾时再统一摘除。
"""

from __future__ import annotations

from pathlib import Path

# 允许作为「知识来源」只读打开的 vault 顶层目录；审批来源入口与来源查看器
# 共用同一份白名单，避免出现一个更宽的旁路。
#
# ⚠️ 这是**看得见的常量**，不做运行时派生（派生会让"库里多一个目录"静默放行，也会让
# 白名单与约定脱钩）。因此必须由 `tests/unit/test_knowledge_sources.py` 的机器守卫兜住
# 一致性：conventions §3 的 8 个主线项目目录 + `thinking`，且不得残留死目录。
#
# 2026-09-19 修正：此前是「工作线主线」时代的旧根（`hii`/`it`/`community`/`hr`）加上
# `daily`/`reviews`，8 个项目目录全部缺失 ⇒ 全库约 612 条落在项目目录里的 `路径#区块`
# 引用点开会报 400「来源路径不在允许的知识范围内」。`daily`/`reviews` 自本阶段起也不再
# 是库内目录（简报/周报已迁到本机程序目录）。
KNOWLEDGE_SOURCE_ROOTS = frozenset(
    {
        "projects",
        "meetings",
        "logs",
        "artifacts",
        "inboxes",
        "insights",
        "decisions",
        "index",
        # ---- 主线项目目录（目录名＝项目 ID，conventions §1）----
        "hii-royalty",
        "hii-ip-license",
        "hii-china-visit",
        "it-development",
        "finance-budget",
        "huoman-community",
        "huoman-logistics",
        "course-material-production",
        # ---- 工作思考（跨项目长文，conventions §1.1）----
        "thinking",
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
