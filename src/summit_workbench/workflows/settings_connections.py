"""Shared connection operations for the Web settings and onboarding flows.

The UI routes only adapt HTTP requests.  Credential scope, model verification and
Feishu token persistence live here so restricted onboarding and the full workspace
app cannot drift into separate provider/Keychain implementations.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from summit_workbench.config.secrets import resolve_credential
from summit_workbench.config.settings import default_config_file
from summit_workbench.providers.feishu.config import FeishuConfig, load_feishu_config
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import load_model_config
from summit_workbench.providers.llm.client import ModelClient


def verify_model(
    *,
    config_file: Path,
    workspace_id: str,
    secret: str | None = None,
) -> dict[str, object]:
    """Send one minimal non-mutating chat request using a workspace-scoped key."""
    config = load_model_config("ranking", config_file, workspace_id=workspace_id)
    api_key = SecretStr(secret) if secret else resolve_credential(config.api_key_ref)
    result = ModelClient(config, api_key).complete(
        "You are a connection check. Return only the word OK.",
        "Reply with OK.",
        json_mode=False,
        max_retries=0,
    )
    return {
        "model": config.model_id,
        "message": "现场验证成功（模型已返回）",
        "attempts": result.attempts,
    }


def feishu_config(*, config_file: Path, workspace_id: str) -> FeishuConfig:
    try:
        return load_feishu_config(config_file, workspace_id=workspace_id)
    except Exception:
        # Initial onboarding may not have copied non-secret app settings into the
        # profile yet.  The application config remains the only fallback source;
        # tokens are still always written to the workspace-scoped Keychain.
        return load_feishu_config(default_config_file(), workspace_id=workspace_id)


def complete_feishu_authorization(
    *,
    config_file: Path,
    workspace_id: str,
    lock_root: Path | None,
    code: str,
) -> None:
    cfg = feishu_config(config_file=config_file, workspace_id=workspace_id)
    FeishuSession(cfg, lock_root=lock_root).complete_authorization(code)


__all__ = ["complete_feishu_authorization", "feishu_config", "verify_model"]
