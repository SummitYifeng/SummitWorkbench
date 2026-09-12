"""本地写运行时：切换守卫 + 同步门 + 写回留痕（LEGACY-APP-SPLIT-PLAN Step 3 / P + B4）。

这些逻辑原来散在 ``legacy_app.create_app`` 的闭包里（``_current_sync_snapshot`` /
``_run_web_mutation`` / ``_sync_blocked`` / ``_mutation_blocked`` / ``_commit_suffix``
以及 ``profile_switch_in_progress`` 局部变量），抽成一个**每 app 一个实例**的运行时对象：

- ``profile_switch_in_progress``：切换工作台期间拒绝写入（原来是闭包变量 + ``nonlocal``）；
- ``run(...)``：把一次本地写包装成 ``run_local_mutation``，带上同步快照与 push 后置动作；
- ``sync_blocked`` / ``mutation_blocked``：automation 角色门与 diverged/dirty 保护态；
- ``commit_suffix``：写回成功后自动留痕（``wb:`` 前缀，非 git / 内容未变时静默）。

**per-app 语义（§6-R8）**：严禁把它做成模块级单例——同进程会创建多个 app（测试大量如此），
单例会让它们共享切换态与快照，造成跨测试污染与并发串扰。

**monkeypatch 契约（§6-R3）**：``_commit_suffix`` 保持**模块级函数**（不是方法），
``tests/unit/test_webapi_sync.py`` 直接 patch 本模块的这个属性来观察留痕调用；因此
``MutationRuntime.commit_suffix`` 必须经模块 global 调用它，不能把逻辑内联进方法。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from summit_workbench.config.git_credentials import profile_identity
from summit_workbench.domain.sync import AutomationOutcome, SyncSnapshot
from summit_workbench.repositories.autocommit import CommitStatus, commit_paths
from summit_workbench.repositories.automation_primary import load_automation_primary
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.errors import error_payload
from summit_workbench.webapp.mutation_response import _commit_note
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
    LocalMutationResult,
    MutationBlocked,
    run_local_mutation,
)


def _commit_suffix(ctx: WebContext, paths: Sequence[Path | str], summary: str) -> str:
    """系统写回成功后自动留痕（消息带 ``wb:`` 前缀，P0'）。

    返回需要追加进响应 ``message`` 的可见说明：非 git 仓库 / 内容未变是正常态（静默，
    撤销面板会提示 not-git）；commit 失败或锁忙返回说明，但绝不阻断业务写回。
    """
    result = commit_paths(
        ctx.vault_dir,
        [Path(p) for p in paths if p],
        message=f"wb: {summary}",
        backend_kind=ctx.git_backend_kind,
        author=(
            profile_identity(ctx.active_workspace.profile)
            if ctx.active_workspace is not None and ctx.active_workspace.profile is not None
            else None
        ),
    )
    if result.status is CommitStatus.COMMITTED and ctx.active_workspace is not None:
        from summit_workbench.workflows import sync_coordinator

        sync_coordinator.push_after_commit(
            ctx.vault_dir,
            home=ctx.active_workspace.home,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )
    return _commit_note(result)


class MutationRuntime:
    """本地事务 + 同步守卫的唯一运行时；由 ``create_app`` 构造并向下注入。"""

    def __init__(self, context: WebContext, *, operation_id: Callable[[Request], str]) -> None:
        self._ctx = context
        self._operation_id = operation_id
        self._profile_switch_in_progress = False

    @property
    def profile_switch_in_progress(self) -> bool:
        return self._profile_switch_in_progress

    def begin_profile_switch(self) -> None:
        self._profile_switch_in_progress = True

    def end_profile_switch(self) -> None:
        self._profile_switch_in_progress = False

    def snapshot(self) -> SyncSnapshot:
        from summit_workbench.workflows import sync_coordinator

        ctx = self._ctx
        return sync_coordinator.current_snapshot(
            ctx.vault_dir,
            home=ctx.active_workspace.home if ctx.active_workspace else None,
            workspace_id=ctx.workspace_id,
            backend_kind=ctx.git_backend_kind,
            context=ctx.active_workspace,
        )

    def run[T](
        self, action: str, mutation: Callable[[str], LocalMutationOutcome[T]]
    ) -> LocalMutationResult[T]:
        from summit_workbench.workflows import sync_coordinator

        ctx = self._ctx
        if self._profile_switch_in_progress:
            raise MutationBlocked("工作台正在切换，请等待本机服务重启后再修改")
        profile = ctx.active_workspace.profile if ctx.active_workspace else None
        return run_local_mutation(
            ctx.vault_dir,
            action,
            mutation,
            sync_snapshot=self.snapshot() if ctx.active_workspace else None,
            sync_snapshot_provider=self.snapshot if ctx.active_workspace else None,
            compatibility=ctx.compatibility,
            backend_kind=ctx.git_backend_kind,
            author=profile_identity(profile) if profile is not None else None,
            push_after_commit=(
                lambda: sync_coordinator.push_after_commit(
                    ctx.vault_dir,
                    home=ctx.active_workspace.home if ctx.active_workspace else None,
                    workspace_id=ctx.workspace_id,
                    backend_kind=ctx.git_backend_kind,
                    context=ctx.active_workspace,
                )
            )
            if ctx.active_workspace
            else None,
        )

    def sync_blocked(self, request: Request) -> JSONResponse | None:
        """automation 角色门：secondary 上定时 writer 不执行（env-compat 放行）。"""
        from summit_workbench.workflows import sync_coordinator

        ctx = self._ctx
        profile = ctx.active_workspace.profile if ctx.active_workspace else None
        if ctx.active_workspace is None:
            # 保留直接注入 WebContext 的 development/test 兼容语义：这些调用方
            # 可能在 app 创建后才准备临时 profile。production 入口始终传入冻结
            # 的 ActiveWorkspaceContext，不会走这条动态回退。
            from summit_workbench.config.profiles import resolve_active_workspace

            profile = resolve_active_workspace(allow_env_fallback=True).profile
        claim = None
        device_id = None
        if ctx.active_workspace is not None:
            claim = load_automation_primary(ctx.vault_dir)
            device_id = ctx.active_workspace.device_id
        if (
            sync_coordinator.automation_gate(
                profile,
                claim=claim,
                device_id=device_id,
                require_claim=ctx.active_workspace is not None,
            )
            is AutomationOutcome.NOT_PRIMARY
        ):
            # P1-07D：secondary 上的手动/定时写入是预期跳过，不是错误。返回 200 友好
            # 提示（前端以普通提示而非红色 ApiError 呈现），写入本身仍被门控跳过。
            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "skipped": True,
                    "code": "not_automation_primary",
                    "message": "本机不是该 workspace 的主设备，本次操作已跳过",
                },
            )
        return None

    def mutation_blocked(self, request: Request) -> JSONResponse | None:
        """diverged/dirty 保护态：修改共享 vault 的写被拒（读照常）。"""
        from summit_workbench.workflows import sync_coordinator

        snapshot = self.snapshot()
        ok, reason = sync_coordinator.mutation_guard(snapshot)
        if ok:
            return None
        state = snapshot.state.value if snapshot is not None else "protected"
        return JSONResponse(
            status_code=409,
            content=error_payload(
                code="sync_diverged",
                message=reason,
                operation_id=self._operation_id(request),
                details={"state": state},
            ),
        )

    def commit_suffix(self, paths: Sequence[Path | str], summary: str) -> str:
        """经模块 global 调用 ``_commit_suffix``，保留测试的 patch 契约。"""
        return _commit_suffix(self._ctx, paths, summary)
