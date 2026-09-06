"""本机诊断包预览与导出路由（P1-05）。"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from summit_workbench.observability.structured_logging import StructuredLogger
from summit_workbench.observability.support_bundle import bundle_bytes, diagnostic_snapshot
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload


def register_diagnostics_routes(
    dependencies: RouteDependencies,
    *,
    static_dir: Path,
    log_path: Path | None,
) -> None:
    """注册只读诊断预览和本机 zip 导出。"""
    app: FastAPI = dependencies.app
    context = dependencies.context
    logger = StructuredLogger(log_path, component="webapp")

    def snapshot(request: Request) -> dict[str, object] | JSONResponse:
        try:
            return diagnostic_snapshot(context, static_dir=static_dir, log_path=log_path)
        except Exception as exc:
            logger.log(
                "diagnostics_snapshot_failed",
                level="error",
                operation_id=dependencies.operation_id(request),
                workspace_id=context.workspace_id,
                error_code="diagnostics_snapshot_failed",
                fields={"message": str(exc)},
            )
            return JSONResponse(
                status_code=500,
                content=error_payload(
                    code="diagnostics_snapshot_failed",
                    message="诊断信息暂时无法生成",
                    operation_id=dependencies.operation_id(request),
                ),
            )

    @app.get("/api/diagnostics/preview")
    def diagnostics_preview(request: Request) -> JSONResponse:
        result = snapshot(request)
        if isinstance(result, JSONResponse):
            return result
        return JSONResponse(
            content={
                "ok": True,
                "files": [
                    {
                        "name": "diagnostics.json",
                        "description": "版本、架构、schema、状态摘要、脱敏错误、签名和同步计数",
                    }
                ],
                "snapshot": result,
            }
        )

    @app.get("/api/diagnostics/export")
    def diagnostics_export(request: Request) -> Response:
        result = snapshot(request)
        if isinstance(result, JSONResponse):
            return result
        return StreamingResponse(
            io.BytesIO(bundle_bytes(result)),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="summitworkbench-diagnostics.zip"',
                "Cache-Control": "no-store, max-age=0",
            },
        )


__all__ = ["register_diagnostics_routes"]
