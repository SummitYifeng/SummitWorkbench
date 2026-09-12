"""工作区模型配置加载入口（LEGACY-APP-SPLIT-PLAN Step 11 / B1）。

从 ``legacy_app`` 抽出 ``_load_model_config_for_context``：按工作区 profile 解析模型
配置，``workspace_id is None`` 时回退到既有的 ``load_model_config``。

函数体**逐字保留**——两个依赖都在函数内局部 import，以维持既有 monkeypatch 契约
（测试 patch 的是 ``summit_workbench.providers.llm.load_model_config`` 与
``summit_workbench.workflows.settings_connections.model_config`` 这两个源模块）。

``routers/threads.py``（Step 11）、``routers/capture.py``（Step 12）以及后续的
``webapp/meeting_import.py``（S5）共用本模块。
"""

from __future__ import annotations

from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.webapp.context import WebContext


def _load_model_config_for_context(ctx: WebContext, capability: str) -> ModelConfig:
    """Load legacy test/development config without changing its monkeypatch contract."""
    from summit_workbench.workflows.settings_connections import model_config

    if ctx.workspace_id is None:
        from summit_workbench.providers.llm import load_model_config

        return load_model_config(capability)
    return model_config(
        capability=capability,
        config_file=ctx.provider_config_file(),
        workspace_id=ctx.workspace_id,
    )


__all__ = ["_load_model_config_for_context"]
