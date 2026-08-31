"""飞书配置加载与凭据引用测试。"""

from __future__ import annotations

import pytest

from summit_workbench.config.secrets import CredentialRef
from summit_workbench.providers.feishu.config import DEFAULT_SCOPES, load_feishu_config
from summit_workbench.providers.feishu.errors import FeishuConfigError


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def test_load_ok_with_defaults(tmp_path):
    cfg_file = tmp_path / "config.toml"
    _write(cfg_file, '[feishu]\napp_id = "cli_9"\nredirect_uri = "http://localhost/cb"\n')
    cfg = load_feishu_config(cfg_file)
    assert cfg.app_id == "cli_9"
    assert cfg.scopes == DEFAULT_SCOPES
    assert cfg.app_secret_ref == CredentialRef(
        service="summit-workbench-feishu-app-secret", account="cli_9"
    )
    assert cfg.refresh_token_ref.account == "cli_9"
    assert "offline_access" in cfg.scope_param


def test_missing_section_raises(tmp_path):
    cfg_file = tmp_path / "config.toml"
    _write(cfg_file, 'timezone = "UTC"\n')
    with pytest.raises(FeishuConfigError):
        load_feishu_config(cfg_file)


def test_missing_app_id_raises(tmp_path):
    cfg_file = tmp_path / "config.toml"
    _write(cfg_file, '[feishu]\nredirect_uri = "http://localhost/cb"\n')
    with pytest.raises(FeishuConfigError) as ei:
        load_feishu_config(cfg_file)
    assert "app_id" in str(ei.value)


def test_scopes_override(tmp_path):
    cfg_file = tmp_path / "config.toml"
    _write(
        cfg_file,
        '[feishu]\napp_id = "a"\nredirect_uri = "http://localhost/cb"\n'
        'scopes = ["task:task", "offline_access"]\n',
    )
    cfg = load_feishu_config(cfg_file)
    assert cfg.scopes == ("task:task", "offline_access")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FeishuConfigError):
        load_feishu_config(tmp_path / "nope.toml")
