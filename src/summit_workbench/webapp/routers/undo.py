"""Git 撤销路由（LEGACY-APP-SPLIT-PLAN Step 14 / R12）。

承载原 ``legacy_app`` 的 3 条撤销路由：最近自动提交列表、提交 diff、按提交还原。
``_undo_error_response`` 随迁（撤销错误码 → HTTP 状态映射）。

``/api/undo/diff`` 与 ``/api/undo/revert`` 的快照 ``error_codes`` 本就是空的——code 写在
``_undo_error_response`` 体内，``inspect.getsource`` 看不到（§6-R1 反例），随迁后仍应为空。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from summit_workbench.repositories.autocommit import (
    CommitStatus,
    commit_diff_text,
    list_wb_commits,
    revert_commit,
    undo_error_code,
)
from summit_workbench.webapp.api import UndoRevertPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.security import error_payload


def _undo_error_response(code: str, message: str, *, operation_id: str = "unknown") -> JSONResponse:
    """返回撤销 API 的稳定 4xx 错误 envelope。"""
    status_code = {
        "undo_invalid_commit": 422,
        "undo_target_dirty": 409,
        "undo_not_git": 409,
        "undo_busy": 423,
    }.get(code, 409)
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code=code, message=message, operation_id=operation_id),
    )


def register_undo_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册 Git 撤销路由（原 ``legacy_app`` 483–542）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context
    _operation_id = dependencies.operation_id

    @app.get("/api/undo/history")
    def api_undo_history() -> dict[str, object]:
        """最近 ``wb:`` 自动提交列表（含每提交触碰文件与仓库状态）。"""
        commits, error = list_wb_commits(ctx.vault_dir, limit=20)
        if error == "not-git":
            return {
                "ok": True,
                "commits": [],
                "note": "vault 不是 git 仓库：系统写回不会自动留痕，也无法撤销",
            }
        if error is not None:
            return {"ok": False, "message": f"读取提交历史失败：{error}"}
        return {"ok": True, "commits": [c.as_dict() for c in commits], "note": None}

    @app.get("/api/undo/diff", response_model=None)
    def api_undo_diff(request: Request, sha: str) -> dict[str, object] | JSONResponse:
        """某次 wb 提交的 before/after 差异（git show 输出），供撤销前预览。"""
        text, error = commit_diff_text(ctx.vault_dir, sha)
        if error is not None:
            code = undo_error_code(error)
            return _undo_error_response(
                code, f"无法读取差异：{error}", operation_id=_operation_id(request)
            )
        return {"ok": True, "diff": text}

    @app.post("/api/undo/revert", response_model=None)
    def api_undo_revert(
        request: Request, payload: UndoRevertPayload
    ) -> dict[str, object] | JSONResponse:
        """还原一次 wb 自动提交（等价 git revert；只作用于 vault 文件）。"""
        blocked = runtime.mutation_blocked(request)
        if blocked is not None:
            return blocked
        sha = payload.sha.strip()
        if not sha:
            return _undo_error_response(
                "undo_invalid_commit", "缺少提交 sha", operation_id=_operation_id(request)
            )
        result = revert_commit(ctx.vault_dir, sha)
        if result.status is CommitStatus.REVERTED:
            # 明示边界：飞书侧副作用（已建任务/会议、已完成状态）不可撤销。
            return {
                "ok": True,
                "message": "已还原 vault 文件。注意：飞书侧已产生的副作用（已建任务/会议、"
                "已完成状态）不可撤销、不受本次还原影响。" + (result.detail or ""),
            }
        if result.status is CommitStatus.NOT_GIT:
            return _undo_error_response(
                "undo_not_git", "vault 不是 git 仓库，无法撤销", operation_id=_operation_id(request)
            )
        code = {
            "invalid-wb-commit": "undo_invalid_commit",
            "undo-target-dirty": "undo_target_dirty",
            "workspace-locked": "undo_busy",
        }.get(result.error_code or "", "undo_failed")
        return _undo_error_response(
            code,
            f"还原失败：{result.detail or result.status.value}",
            operation_id=_operation_id(request),
        )


__all__ = ["register_undo_routes"]
