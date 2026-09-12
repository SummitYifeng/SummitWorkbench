"""内置飞书默认凭据（分发包资源）与配置回退链测试。

覆盖 ``load_feishu_config`` 的三级优先级与 ``load_bundled_defaults`` 的边界：
显式 ``[feishu]`` 表 > 包内内置默认值 > 显式报错；显式表一旦存在就保持严格校验。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from summit_workbench.providers.feishu.bundled import (
    DEFAULT_REDIRECT_URI,
    bundled_defaults_file,
    load_bundled_defaults,
)
from summit_workbench.providers.feishu.config import DEFAULT_SCOPES, load_feishu_config
from summit_workbench.providers.feishu.errors import FeishuConfigError

BUNDLED_JSON = {
    "app_id": "cli_bundled",
    "app_secret": "bundled-secret",
    "redirect_uri": "http://localhost:8765/callback",
}


def _write_bundled(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = dict(BUNDLED_JSON)
    payload.update(overrides)
    path = tmp_path / "feishu-defaults.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _use_bundled(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(path))


# ---- load_bundled_defaults ----


def test_bundled_absent_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_bundled(monkeypatch, tmp_path / "absent.json")
    assert load_bundled_defaults() is None


def test_bundled_reads_all_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path))
    defaults = load_bundled_defaults()
    assert defaults is not None
    assert defaults.app_id == "cli_bundled"
    assert defaults.redirect_uri == DEFAULT_REDIRECT_URI
    assert defaults.app_secret is not None
    assert defaults.app_secret.get_secret_value() == "bundled-secret"


def test_bundled_redirect_uri_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path, redirect_uri=""))
    defaults = load_bundled_defaults()
    assert defaults is not None
    assert defaults.redirect_uri == DEFAULT_REDIRECT_URI


def test_bundled_without_app_id_is_treated_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path, app_id=""))
    assert load_bundled_defaults() is None


def test_bundled_without_secret_keeps_app_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path, app_secret=""))
    defaults = load_bundled_defaults()
    assert defaults is not None
    assert defaults.app_secret is None


def test_corrupt_bundled_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "feishu-defaults.json"
    path.write_text("{not json", encoding="utf-8")
    _use_bundled(monkeypatch, path)
    with pytest.raises(FeishuConfigError):
        load_bundled_defaults()


# ---- load_feishu_config 回退链 ----


def test_missing_config_uses_bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path))
    cfg = load_feishu_config(tmp_path / "nope.toml", workspace_id="ws-1")
    assert cfg.app_id == "cli_bundled"
    assert cfg.redirect_uri == DEFAULT_REDIRECT_URI
    assert cfg.scopes == DEFAULT_SCOPES
    assert cfg.workspace_id == "ws-1"


def test_config_without_feishu_section_uses_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path))
    config_file = tmp_path / "config.toml"
    config_file.write_text('timezone = "UTC"\n', encoding="utf-8")
    assert load_feishu_config(config_file).app_id == "cli_bundled"


def test_explicit_config_wins_over_bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_bundled(monkeypatch, _write_bundled(tmp_path))
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[feishu]\napp_id = "cli_explicit"\nredirect_uri = "http://localhost:9999/cb"\n',
        encoding="utf-8",
    )
    cfg = load_feishu_config(config_file)
    assert cfg.app_id == "cli_explicit"
    assert cfg.redirect_uri == "http://localhost:9999/cb"


def test_explicit_section_stays_strict_with_bundled_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式写了 [feishu] 却漏字段时必须报错，不能被内置默认值掩盖。"""
    _use_bundled(monkeypatch, _write_bundled(tmp_path))
    config_file = tmp_path / "config.toml"
    config_file.write_text('[feishu]\nredirect_uri = "http://localhost/cb"\n', encoding="utf-8")
    with pytest.raises(FeishuConfigError) as excinfo:
        load_feishu_config(config_file)
    assert "app_id" in str(excinfo.value)


def test_error_message_when_neither_config_nor_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_bundled(monkeypatch, tmp_path / "absent.json")
    with pytest.raises(FeishuConfigError) as excinfo:
        load_feishu_config(tmp_path / "nope.toml")
    assert "配置文件不存在" in str(excinfo.value)


# ---- 包内文件的查找路径（打包运行时契约）----
#
# 打包后 App 的布局是固定的，两条查找路径都必须有效；这里把它们锁成测试，
# 避免启动器改了环境变量或目录结构后「静默拿不到内置凭据」。


def _fake_bundle(tmp_path: Path) -> Path:
    """搭一个与真实 .app 同构的目录，返回 App 根。"""
    app = tmp_path / "SummitWorkbench.app"
    (app / "Contents" / "Resources" / "web" / "static").mkdir(parents=True)
    (app / "Contents" / "Resources" / "server").mkdir(parents=True)
    return app


def test_bundled_found_via_static_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动器通过 WB_STATIC_DIR 传资源位置时（真实 App 的路径）。"""
    app = _fake_bundle(tmp_path)
    expected = _write_bundled(app / "Contents" / "Resources")
    monkeypatch.delenv("WB_FEISHU_DEFAULTS", raising=False)
    monkeypatch.setenv("WB_STATIC_DIR", str(app / "Contents" / "Resources" / "web" / "static"))
    assert bundled_defaults_file() == expected


def test_bundled_found_next_to_server_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """没有 WB_STATIC_DIR 时，回退到 server 可执行文件的上一级（Resources）。"""
    app = _fake_bundle(tmp_path)
    expected = _write_bundled(app / "Contents" / "Resources")
    monkeypatch.delenv("WB_FEISHU_DEFAULTS", raising=False)
    monkeypatch.delenv("WB_STATIC_DIR", raising=False)
    monkeypatch.setattr(
        "sys.executable",
        str(app / "Contents" / "Resources" / "server" / "SummitWorkbenchServer"),
    )
    assert bundled_defaults_file() == expected


def test_explicit_override_wins_over_bundle_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _fake_bundle(tmp_path)
    _write_bundled(app / "Contents" / "Resources")
    elsewhere = _write_bundled(tmp_path / "elsewhere", app_id="cli_override")
    monkeypatch.setenv("WB_STATIC_DIR", str(app / "Contents" / "Resources" / "web" / "static"))
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", str(elsewhere))
    assert bundled_defaults_file() == elsewhere


def test_empty_override_disables_probing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """WB_FEISHU_DEFAULTS 设为空串＝显式关闭内置凭据（测试与开发用）。"""
    app = _fake_bundle(tmp_path)
    _write_bundled(app / "Contents" / "Resources")
    monkeypatch.setenv("WB_STATIC_DIR", str(app / "Contents" / "Resources" / "web" / "static"))
    monkeypatch.setenv("WB_FEISHU_DEFAULTS", "")
    assert bundled_defaults_file() is None
    assert load_bundled_defaults() is None
