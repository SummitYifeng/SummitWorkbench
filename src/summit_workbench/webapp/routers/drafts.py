"""本机表单草稿 API。"""

from __future__ import annotations

import hashlib

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from summit_workbench.repositories.local_drafts import DraftValidationError, LocalDraftStore
from summit_workbench.webapp.context import WebContext


class DraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    value: dict[str, object]


def _store(context: WebContext) -> LocalDraftStore:
    workspace_id = context.workspace_id
    if not workspace_id:
        workspace_id = (
            "local-"
            + hashlib.sha256(str(context.vault_dir.expanduser().resolve()).encode()).hexdigest()[
                :24
            ]
        )
    home = context.active_workspace.home if context.active_workspace else context.work_root
    return LocalDraftStore(workspace_id, home=home)


def _split_key(key: str) -> tuple[str, str]:
    draft_type, separator, draft_id = key.partition(":")
    if not separator:
        raise DraftValidationError("草稿标识格式无效")
    return draft_type, draft_id


def register_draft_routes(app: FastAPI, context: WebContext) -> None:
    @app.get("/api/drafts", response_model=None)
    def api_drafts() -> dict[str, object]:
        return {"ok": True, "drafts": _store(context).list()}

    @app.get("/api/drafts/{key}", response_model=None)
    def api_get_draft(key: str) -> dict[str, object] | JSONResponse:
        try:
            draft_type, draft_id = _split_key(key)
            draft = _store(context).get(draft_type, draft_id)
        except DraftValidationError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "message": str(exc)})
        return {"ok": True, "draft": draft}

    @app.put("/api/drafts/{key}", response_model=None)
    def api_save_draft(key: str, payload: DraftPayload) -> dict[str, object] | JSONResponse:
        try:
            draft_type, draft_id = _split_key(key)
            if (draft_type, draft_id) != (payload.type, payload.id):
                raise DraftValidationError("草稿地址与内容标识不一致")
            draft = _store(context).save(draft_type, draft_id, payload.value)
        except DraftValidationError as exc:
            return JSONResponse(status_code=422, content={"ok": False, "message": str(exc)})
        return {"ok": True, "draft": draft, "message": "草稿已保存在本机"}

    @app.delete("/api/drafts/{key}", response_model=None)
    def api_delete_draft(key: str) -> dict[str, object] | JSONResponse:
        try:
            draft_type, draft_id = _split_key(key)
            deleted = _store(context).delete(draft_type, draft_id)
        except DraftValidationError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "message": str(exc)})
        return {"ok": True, "deleted": deleted}


__all__ = ["register_draft_routes"]
