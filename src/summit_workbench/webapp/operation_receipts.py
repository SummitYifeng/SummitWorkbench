"""把可恢复回执接入 HTTP 写请求。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from summit_workbench.repositories.operation_receipts import (
    OperationReceiptStore,
)
from summit_workbench.webapp.context import WebContext


def store_for_context(context: WebContext) -> OperationReceiptStore:
    workspace_id = context.workspace_id
    if not workspace_id:
        # 兼容直接注入 WebContext 的开发/测试入口；生产按 profile.workspace_id 隔离。
        workspace_id = (
            "local-"
            + hashlib.sha256(
                str(context.vault_dir.expanduser().resolve()).encode("utf-8")
            ).hexdigest()[:24]
        )
    home = context.active_workspace.home if context.active_workspace else context.work_root
    return OperationReceiptStore(workspace_id, home=home)


def run_with_receipt(
    context: WebContext,
    request: Request,
    payload: object,
    action: Callable[[], dict[str, object]],
) -> dict[str, object] | JSONResponse:
    request_id = request.headers.get("X-WB-Request-Id")
    if request_id is None:
        return action()
    try:
        result = store_for_context(context).run(request_id, payload, action)
    except ValueError as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "status": "conflict", "message": str(exc)},
        )
    return JSONResponse(status_code=result.status_code, content=result.response)


def register_operation_receipt_routes(app: FastAPI, context: WebContext) -> None:
    @app.get("/api/workspace/operations", response_model=None)
    def api_workspace_operations() -> dict[str, object]:
        from summit_workbench.repositories.local_mutation_journal import list_mutation_records

        records = list_mutation_records(context.vault_dir)
        pending = [
            record
            for record in records
            if record.get("state") in {"running", "interrupted", "corrupt"}
        ]
        return {"ok": True, "operations": pending}

    @app.get("/api/operations/{request_id}", response_model=None)
    def api_operation_receipt(request_id: str) -> dict[str, object] | JSONResponse:
        try:
            receipt = store_for_context(context).get(request_id)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "message": str(exc)})
        if receipt is None:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "operation_id": request_id,
                    "status": "not_found",
                    "message": "未找到本机操作回执；请核对工作区后再决定是否重新提交。",
                },
            )
        return receipt


__all__ = ["register_operation_receipt_routes", "run_with_receipt", "store_for_context"]
