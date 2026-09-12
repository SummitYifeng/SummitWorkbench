"""会议逐字稿导入路由（LEGACY-APP-SPLIT-PLAN Step 14 / R11）。

承载原 ``legacy_app`` 的 ``POST /api/meetings/import``：上传逐字稿（≤ 10 MiB），落地
临时文件后交给 ``webapp.meeting_import._run_web_import`` 全自动处理。

``inspect.signature(_run_web_import)`` 的兼容分支**原样保留**——蓝图明确不批准把它改成
依赖注入探测。``runtime`` 由 ``create_app`` 注入，作为集中式写入门。
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.meeting_import import _run_web_import as _run_web_import
from summit_workbench.webapp.mutation_runtime import MutationRuntime


def register_meetings_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册会议逐字稿导入路由（原 ``legacy_app`` 440–479）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/api/meetings/import")
    def api_meetings_import(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        """拖拽上传逐字稿 → 全自动归档 + 结构化 + 生成审批候选。"""
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
        tmp_dir = Path(tempfile.mkdtemp(prefix="wb-web-import-"))
        try:
            target = tmp_dir / Path(name).name
            target.write_text(text, encoding="utf-8")
            if "local_mutation" in inspect.signature(_run_web_import).parameters:
                return _run_web_import(ctx, target, local_mutation=runtime.run)
            # 保持旧版/测试注入器的二参数兼容性；正式实现始终走集中式写入门。
            return _run_web_import(ctx, target)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


__all__ = ["register_meetings_routes"]
