"""知识来源白名单的机器守卫（来源面板与审批只读入口共用 ``KNOWLEDGE_SOURCE_ROOTS``）。

**为什么需要守卫**：白名单是「看得见的常量」（不做运行时派生，避免"库里多一个目录"
静默放行、也避免与 conventions 脱钩）。代价是它不会自动跟上库结构——2026-09-19 实测：
8 个主线项目目录全部不在白名单里，而白名单还留着 4 个已撤销的旧目录，于是全库约
612 条落在项目目录里的 ``路径#区块`` 引用点开会报 400「来源路径不在允许的知识范围内」。
守卫就是为这一类漂移存在的。

**两层**：

1. 常量层（始终运行）：conventions §3 的 8 个主线项目 ID 与 ``thinking`` 必须在白名单内，
   6 个已撤销 / 已迁出的死目录（``hii``/``it``/``community``/``hr``/``daily``/``reviews``）
   必须不在。
2. 真实库层（本机有可解析的工作库时运行）：遍历真实 ``_vault/projects/*.md`` 的项目 ID，
   逐一断言在白名单内。真实 home 用 ``pwd`` 取——``tests/conftest.py`` 把 ``$HOME`` 指向
   临时目录，用 ``Path.home()`` 会永远 skip，守卫就形同虚设。

**变异验证**：从 ``KNOWLEDGE_SOURCE_ROOTS`` 删掉任一项目目录（如 ``huoman-logistics``），
``test_canonical_projects_are_allowed`` 与 ``test_real_vault_project_dirs_are_all_allowed``
必须立刻变红。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from summit_workbench.webapp.knowledge_sources import (
    KNOWLEDGE_SOURCE_ROOTS,
    _is_knowledge_source,
)

# conventions §3 / §1：8 个主线项目页一一对应 8 个同名顶层目录。
CANONICAL_PROJECT_IDS = (
    "hii-royalty",
    "hii-ip-license",
    "hii-china-visit",
    "it-development",
    "finance-budget",
    "huoman-community",
    "huoman-logistics",
    "course-material-production",
)

# 已撤销的旧顶层目录（conventions §1：2026-09-16）与自本阶段起迁出 vault 的目录。
DEAD_ROOTS = ("hii", "it", "community", "hr", "daily", "reviews")


def test_canonical_projects_are_allowed() -> None:
    missing = [pid for pid in CANONICAL_PROJECT_IDS if pid not in KNOWLEDGE_SOURCE_ROOTS]
    assert missing == [], f"主线项目目录不在来源白名单内：{missing}"


def test_thinking_is_allowed_and_dead_roots_are_gone() -> None:
    assert "thinking" in KNOWLEDGE_SOURCE_ROOTS
    leftovers = [root for root in DEAD_ROOTS if root in KNOWLEDGE_SOURCE_ROOTS]
    assert leftovers == [], f"来源白名单还留着死目录：{leftovers}"
    for root in DEAD_ROOTS:
        assert not _is_knowledge_source(Path(root) / "x.md")


def test_project_paths_and_thinking_pass_the_predicate() -> None:
    for pid in CANONICAL_PROJECT_IDS:
        assert _is_knowledge_source(Path(pid) / "notes" / "x.md")
        assert _is_knowledge_source(Path(pid) / "sources" / "attachments" / "x.md")
    assert _is_knowledge_source(Path("thinking") / "x.md")
    # inbox.md 是文件级例外；库外路径仍然拒绝。
    assert _is_knowledge_source(Path("inbox.md"))
    assert not _is_knowledge_source(Path("README.md"))


def test_ai_native_acceptance_project_is_allowed() -> None:
    """样板验收中用户新增的 AI-Native 项目承接会议逐字稿审批。"""
    assert "AI-Native" in KNOWLEDGE_SOURCE_ROOTS
    assert _is_knowledge_source(Path("AI-Native") / "meeting-approval.md")


def test_compat_apps_reexport_the_same_whitelist() -> None:
    """legacy_app / restricted_app 的再导出必须仍指向同一份常量（保持导出有效）。"""
    from summit_workbench.webapp.legacy_app import (
        KNOWLEDGE_SOURCE_ROOTS as LEGACY_ROOTS,
    )
    from summit_workbench.webapp.restricted_app import (
        KNOWLEDGE_SOURCE_ROOTS as RESTRICTED_ROOTS,
    )

    assert LEGACY_ROOTS is KNOWLEDGE_SOURCE_ROOTS
    assert RESTRICTED_ROOTS is KNOWLEDGE_SOURCE_ROOTS


def _real_vault() -> Path | None:
    """本机真实工作库（绕过测试用临时 HOME）；不可解析时返回 None。"""
    try:
        import pwd
    except ImportError:  # pragma: no cover - 非 POSIX 平台
        return None
    try:
        real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):  # pragma: no cover - 查不到账户
        return None
    from summit_workbench.config.profiles import resolve_workspace

    resolution = resolve_workspace(home=real_home, allow_env_fallback=False)
    if resolution.paths is None:
        return None
    vault = resolution.paths.vault_dir
    return vault if (vault / "projects").is_dir() else None


def test_real_vault_project_dirs_are_all_allowed() -> None:
    vault = _real_vault()
    if vault is None:
        pytest.skip("本机没有可解析的真实工作库（注册表/项目目录缺失）")
    project_ids = sorted(path.stem for path in (vault / "projects").glob("*.md"))
    assert project_ids, f"真实工作库 projects/ 为空：{vault}"
    missing = [pid for pid in project_ids if pid not in KNOWLEDGE_SOURCE_ROOTS]
    assert missing == [], f"真实工作库里这些项目目录不在白名单内：{missing}"
