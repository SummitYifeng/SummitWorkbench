"""飞书客户端池与写回器工厂（LEGACY-APP-SPLIT-PLAN Step 2 / B2 + B7）。

从 ``legacy_app.py`` 抽出的两簇：

- **B2 客户端池** ``_FeishuClientPool``：按身份（user / tenant）复用 ``FeishuClient``，
  由 App lifespan 统一释放。会话携带本工作区 lock root，飞书 refresh 与同 workspace
  的写者锁同一把 ``.wb.lock``，不默认落到 ``~/Documents/Work``。
- **B7 写回器工厂** ``_build_task_creator`` / ``_build_meeting_creator``：构造审批写回
  用的 ``TaskCreator`` / ``MeetingCreator``；同一次 apply 内身份只解析一次，会议缺省
  结束时间 = 开始 + 60 分钟。

**必须原样保留的测试契约**：``_get`` 里
``if "token_provider" in inspect.signature(FeishuClient).parameters:`` 这条测试兼容分支。
``tests/unit/test_webapi.py`` 用 2 参数 lambda 替换
``summit_workbench.providers.feishu.FeishuClient``，正是走它的 else 分支；客户端与配置
的导入仍留在函数体内（从 ``providers.feishu`` / ``workflows.settings_connections``
按名字取），因此 monkeypatch 目标不变。
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path

from summit_workbench.config.settings import default_config_file
from summit_workbench.webapp.context import WebContext
from summit_workbench.workflows.review_apply import TaskCreator


class _FeishuClientPool:
    """按身份复用飞书客户端，并由 App lifespan 统一释放。

    P0-06：会话携带本工作区 lock root，Feishu refresh 与同 workspace 写者锁同一把
    ``.wb.lock``，不再默认落到 ``~/Documents/Work``。
    """

    def __init__(
        self,
        lock_root: Path | None = None,
        *,
        config_file: Path | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self._clients: dict[str, object] = {}
        self._lock = threading.Lock()
        self._lock_root = lock_root
        self._config_file = config_file
        self._workspace_id = workspace_id

    def _get(self, identity: str) -> object:
        with self._lock:
            existing = self._clients.get(identity)
            if existing is not None:
                return existing
            from summit_workbench.providers.feishu import (
                FeishuClient,
                FeishuSession,
                load_feishu_config,
            )

            if self._workspace_id is not None:
                from summit_workbench.workflows.settings_connections import feishu_config

                cfg = feishu_config(
                    config_file=self._config_file or default_config_file(),
                    workspace_id=self._workspace_id,
                )
            elif self._config_file is None:
                cfg = load_feishu_config()
            else:
                cfg = load_feishu_config(self._config_file)
            session = FeishuSession(cfg, lock_root=self._lock_root)
            if identity == "user":
                token = session.access_token()
                if "token_provider" in inspect.signature(FeishuClient).parameters:
                    client = FeishuClient(
                        cfg,
                        token,
                        token_provider=session.access_token,
                        token_invalidator=session.invalidate_access_token,
                    )
                else:  # compatibility with injected legacy/test clients
                    client = FeishuClient(cfg, token)
            else:
                token = session.tenant_access_token()
                client = FeishuClient(cfg, token)
            self._clients[identity] = client
            return client

    def user_client(self) -> object:
        return self._get("user")

    def close(self) -> None:
        with self._lock:
            clients = tuple(self._clients.values())
            self._clients.clear()
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def invalidate(self, identity: str = "user") -> None:
        with self._lock:
            client = self._clients.pop(identity, None)
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def _build_task_creator(ctx: WebContext, clients: _FeishuClientPool) -> TaskCreator:
    from summit_workbench.providers.feishu import (
        create_task,
    )
    from summit_workbench.providers.feishu.meetings import verify_identity

    # 同一次 apply 内只解析一次身份；缺失时退化为不带 assignee（保持旧行为而不是失败）。
    resolved: dict[str, str | None] = {}

    def assignee_open_id() -> str | None:
        if "value" not in resolved:
            profile = verify_identity(clients.user_client())  # type: ignore[arg-type]
            resolved["value"] = str(profile.get("open_id") or "") or None
        return resolved["value"]

    def create(
        summary: str,
        due_date: str | None,
        candidate_id: str,
        *,
        operation_id: str | None = None,
        start_at: str | None = None,
    ) -> str:
        return create_task(
            clients.user_client(),  # type: ignore[arg-type]
            summary,
            due_date,
            candidate_id,
            timezone=ctx.timezone,
            start_date=start_at,
            operation_id=operation_id,
            assignee_open_id=assignee_open_id(),
        ).guid

    return create
