"""request boundary 的中间件顺序守卫（LEGACY-APP-SPLIT-PLAN Step 4 前置）。

**顺序就是行为**：`@app.middleware("http")` 在 Starlette 里走
``user_middleware.insert(0, ...)`，而 build 时 ``reversed(middleware)`` ⇒
**后注册者在最外层**。当前 ``legacy_app`` 先注册安全边界（内层）、后注册缓存策略
（外层），因此被安全边界拒绝的响应（例如 Host 不在白名单）**仍会带上
``Cache-Control``**；``_unexpected_error`` 由 ``ServerErrorMiddleware`` 承载，在最外层。

Step 4 把这两个中间件搬进 ``webapp/request_boundary.py`` 时，若调换
``install_security_boundary`` / ``install_cache_policy`` 的调用顺序，HTTP 行为会变，
而多数单测只断言状态码、未必发现。因此在搬移**之前**先把顺序冻结成断言：
搬移后这条测试必须仍然通过，否则就是行为变化，应当回滚该步。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from summit_workbench.webapp.app import WebContext, create_app


def _describe(app: FastAPI) -> list[str]:
    """把中间件栈描述成「类名:dispatch 函数名」。

    两个 `@app.middleware("http")` 生成的类名都是 ``BaseHTTPMiddleware``，只有 dispatch
    函数名能区分它们。
    """
    described: list[str] = []
    for middleware in app.user_middleware:
        # Starlette 把这两者都标成 _MiddlewareFactory，静态上没有 __name__；用 Any 收敛，
        # 这里只做测试期描述，不参与产品类型契约。
        cls: Any = middleware.cls
        kwargs: Any = middleware.kwargs
        dispatch = kwargs.get("dispatch") if isinstance(kwargs, dict) else None
        cls_name = str(getattr(cls, "__name__", "?"))
        if dispatch is None:
            described.append(cls_name)
            continue
        described.append(f"{cls_name}:{getattr(dispatch, '__name__', '?')}")
    return described


def test_full_app_middleware_order_is_frozen(tmp_path: Path) -> None:
    vault = tmp_path / "_vault"
    vault.mkdir()
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    assert _describe(create_app(ctx, static_dir=tmp_path / "no-static")) == [
        "BaseHTTPMiddleware:_cache_policy",
        "BaseHTTPMiddleware:_security_boundary",
    ]


def test_restricted_app_middleware_order_is_frozen(tmp_path: Path) -> None:
    assert _describe(create_app(None, static_dir=tmp_path / "no-static")) == [
        "BaseHTTPMiddleware:_restricted_boundary",
    ]
