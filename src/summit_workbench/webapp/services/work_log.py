"""work-log / 产物写入的共享 seam：活动迁移上下文 + 「本次触碰了哪些 vault 路径」。

**缺陷教训（2026-09-19，第七阶段，真实使用当场暴露）**：``/api/journal/log`` 曾只把日志页
自己交给 ``LocalMutationOutcome.changed_paths``，而 ``append_work_log`` 还会刷新每个关联
项目页的 ``activity_at``（``_touch_projects_activity``）⇒ 项目页留在未提交的 ``M`` 状态，
违反 S-1(a)「写入后工作树干净」。旧路径 ``/api/threads/logs`` 一直是对的，新路径漏抄了。

所以「一次日志写入实际触碰的全部路径」在这里收敛成**唯一**实现，两条写路径共用——
路径集合一旦只存在于某个 router 里，下一条新入口就会再漏一次。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from summit_workbench.webapp.context import WebContext
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.thread_activity_migration import ThreadActivityMigration


def thread_activity_migration(ctx: WebContext) -> ThreadActivityMigration | None:
    """Create the P2-01B seam only for a frozen production workspace context."""
    if ctx.active_workspace is None or not ctx.workspace_id or not ctx.active_workspace.device_id:
        return None
    return ThreadActivityMigration.from_environment(
        ctx.vault_dir,
        workspace_id=ctx.workspace_id,
        device_id=ctx.active_workspace.device_id,
    )


def work_log_outcome(
    vault_dir: Path,
    *,
    path: Path,
    projects: Sequence[str],
    migration: ThreadActivityMigration | None,
) -> LocalMutationOutcome[Path]:
    """一次 ``append_work_log`` / ``save_thread_artifact`` 实际触碰的**全部** vault 路径。

    三部分缺一不可，否则「落盘成功但留下未提交改动」：

    1. ``path``：目标页（日志页 / 产物页）本身；
    2. 每个关联项目页 ``projects/<id>.md``：``_touch_projects_activity`` 刷新
       ``activity_at`` 会重写这些页的 frontmatter；
    3. 活动迁移投影（``_events/``）：仅 DUAL_WRITE 模式会写；LEGACY 模式下为空。
    """
    archives = [vault_dir / "projects" / f"{project}.md" for project in projects]
    changed = (path, *archives, *(migration.last_write_paths if migration else ()))
    report = migration.last_report.as_dict() if migration else None
    return LocalMutationOutcome(changed[0], changed[1:], report)


__all__ = ["thread_activity_migration", "work_log_outcome"]
