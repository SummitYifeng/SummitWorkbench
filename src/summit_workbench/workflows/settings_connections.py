"""Shared connection operations for the Web settings and onboarding flows.

The UI routes only adapt HTTP requests.  Credential scope, model verification and
Feishu token persistence live here so restricted onboarding and the full workspace
app cannot drift into separate provider/Keychain implementations.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import SecretStr

from summit_workbench.config.secrets import resolve_credential
from summit_workbench.config.settings import default_config_file
from summit_workbench.providers.feishu.config import FeishuConfig, load_feishu_config
from summit_workbench.providers.feishu.errors import FeishuConfigError
from summit_workbench.providers.feishu.session import FeishuSession
from summit_workbench.providers.llm import load_model_config
from summit_workbench.providers.llm.client import ModelClient
from summit_workbench.providers.llm.config import ModelConfig
from summit_workbench.providers.llm.errors import LLMConfigError


def verify_model(
    *,
    config_file: Path,
    workspace_id: str,
    secret: str | None = None,
) -> dict[str, object]:
    """Send one minimal non-mutating chat request using a workspace-scoped key."""
    config = model_config(capability="ranking", config_file=config_file, workspace_id=workspace_id)
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
    except FeishuConfigError:
        if config_file.is_file():
            try:
                data = tomllib.loads(config_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                raise
            if isinstance(data.get("feishu"), dict):
                raise
        # Initial onboarding may not have copied non-secret app settings into the
        # profile yet.  The application config remains the only fallback source;
        # tokens are still always written to the workspace-scoped Keychain.
        return load_feishu_config(default_config_file(), workspace_id=workspace_id)


def ensure_feishu_credentials(*, config: FeishuConfig, lock_root: Path | None = None) -> None:
    """授权跳转前验证 app_secret；不返回或记录秘密。"""
    FeishuSession(config, lock_root=lock_root)._app_secret()


def model_config(*, capability: str, config_file: Path, workspace_id: str) -> ModelConfig:
    """Resolve one model config using the profile first and app config as fallback."""
    try:
        return load_model_config(capability, config_file, workspace_id=workspace_id)
    except LLMConfigError:
        return load_model_config(capability, default_config_file(), workspace_id=workspace_id)


def complete_feishu_authorization(
    *,
    config_file: Path,
    workspace_id: str,
    lock_root: Path | None,
    code: str,
    home: Path | None = None,
) -> None:
    cfg = feishu_config(config_file=config_file, workspace_id=workspace_id)
    FeishuSession(cfg, lock_root=lock_root).complete_authorization(code)
    if home is not None:
        # Persist only the non-secret provider settings after token exchange succeeds.
        # The shared profile workflow owns the transaction and workspace Keychain
        # boundary; this keeps the settings card in sync with the authorization result.
        from summit_workbench.workflows.profile_settings import update_provider_settings

        update_provider_settings(
            home=home,
            workspace_id=workspace_id,
            provider="feishu",
            settings={
                "app_id": cfg.app_id,
                "redirect_uri": cfg.redirect_uri,
                "scopes": list(cfg.scopes),
            },
            secret=None,
        )


__all__ = [
    "complete_feishu_authorization",
    "ensure_feishu_credentials",
    "feishu_config",
    "model_config",
    "verify_model",
]
