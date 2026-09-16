"""会议逐字稿导入路由（LEGACY-APP-SPLIT-PLAN Step 14 / R11）。

承载原 ``legacy_app`` 的 ``POST /api/meetings/import``：上传逐字稿（≤ 10 MiB），落地
临时文件后交给 ``webapp.meeting_import._run_web_import`` 全自动处理。

``inspect.signature(_run_web_import)`` 的兼容分支**原样保留**——蓝图明确不批准把它改成
依赖注入探测。``runtime`` 由 ``create_app`` 注入，作为集中式写入门。
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.meeting_import import (
    MeetingImportManager,
    _job_payload,
    _run_web_import,
)
from summit_workbench.webapp.mutation_runtime import MutationRuntime


def register_meetings_routes(
    dependencies: RouteDependencies, *, runtime: MutationRuntime, importer: MeetingImportManager
) -> None:
    """注册会议逐字稿导入路由（原 ``legacy_app`` 440–479）。"""
    app: FastAPI = dependencies.app

    @app.post("/api/meetings/import", response_model=None, status_code=202)
    def api_meetings_import(
        file: Annotated[UploadFile, File()],
    ) -> JSONResponse | dict[str, object]:
        """拖拽上传逐字稿 → 归档后立即返回任务，模型阶段由单 worker 继续。"""
        from summit_workbench.workflows.meetings.backfill import MAX_TRANSCRIPT_BYTES

        max_upload_bytes = MAX_TRANSCRIPT_BYTES
        chunk_size = 64 * 1024
        name = (file.filename or "transcript.txt")[:200]
        if not name.lower().endswith((".md", ".txt")):
            return {"ok": False, "message": "仅支持 .md / .txt 逐字稿文件"}
        buffer = BytesIO()
        total = 0
        while True:
            chunk = file.file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "upload_too_large",
                        "message": "逐字稿文件不能超过 10 MiB",
                    },
                )
            buffer.write(chunk)
        data = buffer.getvalue()
        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            return {"ok": False, "message": "文件内容为空"}
        try:
            job = importer.submit(name, text)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        return JSONResponse(
            status_code=202,
            content={"ok": True, "message": "已归档，后台继续处理", **_job_payload(job)},
        )

    @app.get("/api/meetings/imports")
    def api_meeting_imports() -> dict[str, object]:
        return {"ok": True, "jobs": [_job_payload(job) for job in importer.store.list_recent()]}

    @app.get("/api/meetings/imports/{job_id}", response_model=None)
    def api_meeting_import(job_id: str) -> JSONResponse | dict[str, object]:
        job = importer.store.get(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"ok": False, "message": "任务不存在"})
        return {"ok": True, **_job_payload(job)}

    @app.post("/api/meetings/imports/{job_id}/retry", response_model=None)
    def api_meeting_import_retry(job_id: str) -> JSONResponse | dict[str, object]:
        job = importer.retry(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"ok": False, "message": "任务不存在"})
        if job.status not in {"queued", "running"}:
            return {"ok": False, "message": "任务当前不可重试", **_job_payload(job)}
        return JSONResponse(status_code=202, content={"ok": True, **_job_payload(job)})


__all__ = ["_run_web_import", "register_meetings_routes"]
