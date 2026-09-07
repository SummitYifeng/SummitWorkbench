"""Web 路由的显式依赖容器（P1-03）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI, Request

from summit_workbench.webapp.context import WebContext


@dataclass(frozen=True)
class RouteDependencies:
    """Router 可使用的应用边界依赖，不从 settings 或全局状态自行加载。"""

    app: FastAPI
    context: WebContext
    operation_id: Callable[[Request], str]


def get_app_context(request: Request) -> WebContext:
    """从 app.state 取得创建时注入的 AppContext。"""
    context = getattr(request.app.state, "app_context", None)
    if context is None:
        raise RuntimeError("AppContext 未注入")
    return cast(WebContext, context)


__all__ = ["RouteDependencies", "get_app_context"]
