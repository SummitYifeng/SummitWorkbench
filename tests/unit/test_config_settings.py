"""配置分层测试：默认值 < 配置文件 < 环境变量 < 显式覆盖。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.settings import load_settings


def test_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    settings = load_settings()
    assert settings.timezone == "Asia/Shanghai"
    assert settings.log_level == "INFO"
    assert settings.work_root is None


def test_toml_file_overrides_default(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "UTC"\nlog_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.setenv("WB_CONFIG_FILE", str(cfg))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    settings = load_settings()
    assert settings.timezone == "UTC"
    assert settings.log_level == "DEBUG"


def test_env_overrides_toml(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "UTC"\n', encoding="utf-8")
    monkeypatch.setenv("WB_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("WB_TIMEZONE", "America/New_York")
    settings = load_settings()
    assert settings.timezone == "America/New_York"


def test_explicit_override_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WB_TIMEZONE", "America/New_York")
    settings = load_settings(timezone="Europe/London")
    assert settings.timezone == "Europe/London"


def test_work_paths_derived_from_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", "/tmp/derived-work")
    paths = load_settings().work_paths()
    assert paths.work_root == Path("/tmp/derived-work")
    assert paths.vault_dir == Path("/tmp/derived-work/_vault")
