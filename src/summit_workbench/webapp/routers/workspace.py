"""Workspace 路由：协议适配 + workspace migration service 调用。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Body, Request
from fastapi.responses import JSONResponse

from summit_workbench.webapp.api import WorkspaceMigrationPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload
from summit_workbench.webapp.services import workspace
from summit_workbench.workflows import workspace_migration


def register_workspace_routes(dependencies: RouteDependencies) -> None:
    """注册 workspace 领域路由。"""
    app = dependencies.app
    context = dependencies.context

    @app.post("/api/workspace/migration", response_model=None)
    def api_workspace_migration(
        request: Request, payload: Annotated[WorkspaceMigrationPayload, Body()]
    ) -> dict[str, object] | JSONResponse:
        try:
            result = workspace.migrate_workspace(context, payload.confirmed_device_id)
        except ValueError as exc:
            if str(exc) != "workspace_not_configured":
                raise
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    code="workspace_not_configured",
                    message="只有 active profile 可以执行 workspace 迁移",
                    operation_id=dependencies.operation_id(request),
                ),
            )
        except workspace_migration.WorkspaceMigrationError as exc:
            status_code = {
                "migration_busy": 423,
                "migration_remote_unreachable": 503,
                "migration_failed": 500,
            }.get(exc.code, 409)
            return JSONResponse(
                status_code=status_code,
                content=error_payload(
                    code=exc.code,
                    message=str(exc),
                    operation_id=dependencies.operation_id(request),
                    details=(
                        {"failure_report": str(exc.failure_report)}
                        if exc.failure_report is not None
                        else None
                    ),
                ),
            )
        return workspace.migration_result_payload(result)


__all__ = ["register_workspace_routes"]
