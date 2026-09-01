"""wb doctor 端到端预检（加固 #3）：默认离线、无副作用；未配置项为 WARN 不阻断。"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from summit_workbench.cli.doctor import CheckStatus, run_checks
from summit_workbench.cli.main import app
from summit_workbench.config.settings import load_settings

runner = CliRunner()


def test_offline_doctor_no_fail_when_unconfigured(monkeypatch, tmp_path):
    """未配置飞书/模型时应为 WARN 而非 FAIL（离线不解析凭据、不联网）。"""
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    settings = load_settings()
    checks = run_checks(settings, config_file=tmp_path / "nonexistent.toml", online=False)

    by_name = {c.name: c for c in checks}
    assert by_name["飞书配置"].status is CheckStatus.WARN  # 未配置 → WARN
    assert by_name["模型配置"].status is CheckStatus.WARN
    # 未配置时不应尝试解析凭据（不出现 app_secret/api key 的 FAIL）。
    assert "飞书 app_secret" not in by_name
    # Python 达标即 OK；整体无 FAIL。
    assert by_name["Python"].status is CheckStatus.OK
    assert all(c.status is not CheckStatus.FAIL for c in checks)


def test_doctor_command_json_exit_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert any(c["name"] == "launchd 定时任务" for c in payload["checks"])


def test_doctor_command_human(monkeypatch, tmp_path):
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "预检通过" in result.stdout
