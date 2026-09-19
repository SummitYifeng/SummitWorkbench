"""飞书 OAuth 状态、回调辅助和用户可见的授权失败文案。"""

from __future__ import annotations

import html
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from summit_workbench.config.app_support import PROFILE_FILE_MODE, app_support_dir
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.errors import error_payload

STATE_TTL = 600.0


@dataclass(frozen=True)
class PendingAuthorization:
    workspace_id: str
    created_at: float
    status: Literal["pending", "connected", "failed"] = "pending"
    #: 失败原因（面向用户的白话，已脱敏）——分发包内置凭据后同事本机无可改配置，
    #: 唯一能自救的方式就是界面把原因说清楚。
    reason: str | None = None


class AuthorizationStates:
    def __init__(self, state_file: Path | None = None) -> None:
        self._items: dict[str, PendingAuthorization] = {}
        self._state_file = state_file
        self._load()

    def issue(self, workspace_id: str) -> str:
        self._purge()
        state = secrets.token_urlsafe(32)
        self._items[state] = PendingAuthorization(workspace_id, time.time())
        self._persist()
        return state

    def consume(self, state: str, workspace_id: str | None = None) -> str | None:
        self._purge()
        item = self._items.pop(state, None)
        if item is None or (workspace_id is not None and item.workspace_id != workspace_id):
            return None
        self._persist()
        return item.workspace_id

    def lookup(self, state: str) -> PendingAuthorization | None:
        self._purge()
        return self._items.get(state)

    def finish(
        self,
        state: str,
        *,
        workspace_id: str,
        status: Literal["connected", "failed"],
        reason: str | None = None,
    ) -> bool:
        self._purge()
        item = self._items.get(state)
        if item is None or item.workspace_id != workspace_id or item.status != "pending":
            return False
        self._items[state] = PendingAuthorization(
            workspace_id=item.workspace_id,
            created_at=item.created_at,
            status=status,
            reason=reason if status == "failed" else None,
        )
        self._persist()
        return True

    def _purge(self) -> None:
        now = time.time()
        active = {
            key: value for key, value in self._items.items() if now - value.created_at < STATE_TTL
        }
        if active != self._items:
            self._items = active
            self._persist()

    def _load(self) -> None:
        if self._state_file is None or not self._state_file.is_file():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            items = raw.get("items", {}) if isinstance(raw, dict) else {}
            if not isinstance(items, dict):
                return
            for state, item in items.items():
                if not isinstance(state, str) or not isinstance(item, dict):
                    continue
                workspace_id = item.get("workspace_id")
                created_at = item.get("created_at")
                status = item.get("status", "pending")
                if (
                    isinstance(workspace_id, str)
                    and isinstance(created_at, (int, float))
                    and status in {"pending", "connected", "failed"}
                ):
                    reason = item.get("reason")
                    self._items[state] = PendingAuthorization(
                        workspace_id,
                        float(created_at),
                        status,
                        reason if isinstance(reason, str) and reason else None,
                    )
            self._purge()
        except (OSError, ValueError, TypeError):
            self._items.clear()

    def _persist(self) -> None:
        if self._state_file is None:
            return
        from summit_workbench.repositories._atomic import atomic_write_text

        payload = {
            "schema_version": 1,
            "items": {
                state: {
                    "workspace_id": item.workspace_id,
                    "created_at": item.created_at,
                    "status": item.status,
                    **({"reason": item.reason} if item.reason else {}),
                }
                for state, item in self._items.items()
            },
        }
        atomic_write_text(
            self._state_file,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            ensure_parents=True,
            new_mode=PROFILE_FILE_MODE,
        )


def authorization_state_file(home: Path | None) -> Path | None:
    return app_support_dir(home) / "feishu-auth-state.json" if home is not None else None


def denied_reason(error: str | None) -> str:
    """飞书侧直接拒绝、或回调没带授权码时的原因文案（面向用户，可执行）。"""
    if error == "access_denied":
        return "你取消了授权；需要时可以重新点一次「授权飞书」"
    if error:
        return f"飞书返回了授权错误（{error}）：请重新点一次「授权飞书」"
    return "没有收到授权码：请重新点一次「授权飞书」"


def failure(
    dependencies: RouteDependencies,
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            code=code,
            message=message,
            operation_id=dependencies.operation_id(request),
        ),
    )


def panel_redirect(
    request: Request, suffix: str, *, reason: str | None = None
) -> HTMLResponse | RedirectResponse:
    """回到随机主面板端口，而不是停留在固定 OAuth 回调端口。

    ``reason`` 只在「拿不到 wb_session cookie」这条分支用到：此时无法把用户带回面板
    （例如授权是在外部浏览器里完成的），返回的静态页必须自己说明失败原因，
    否则又是「只说失败」。文案做了 HTML 转义——它会拼进页面。
    """
    port = getattr(request.app.state, "bound_port", None)
    base = f"http://127.0.0.1:{port}" if isinstance(port, int) and port > 0 else ""
    if not request.cookies.get("wb_session"):
        status = "授权已完成" if "connected" in suffix else "授权未完成"
        detail = f"<p>{html.escape(reason)}</p>" if reason else ""
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>SummitWorkbench</title>"
            f"<main style='font:16px -apple-system,sans-serif;max-width:520px;margin:15vh auto'>"
            f"<h1>{status}</h1>{detail}<p>请返回 SummitWorkbench 窗口继续操作。</p></main>"
        )
    return RedirectResponse(url=f"{base}/?{suffix}", status_code=303)


def invalidate_feishu_client(app: FastAPI) -> None:
    clients = getattr(app.state, "feishu_clients", None)
    invalidate = getattr(clients, "invalidate", None)
    if callable(invalidate):
        invalidate("user")


__all__ = [
    "AuthorizationStates",
    "PendingAuthorization",
    "STATE_TTL",
    "authorization_state_file",
    "denied_reason",
    "failure",
    "invalidate_feishu_client",
    "panel_redirect",
]
