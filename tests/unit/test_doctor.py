"""wb doctor 端到端预检（加固 #3）：默认离线、无副作用；未配置项为 WARN 不阻断。"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from summit_workbench.cli import doctor
from summit_workbench.cli.doctor import (
    CheckStatus,
    _credential_check,
    _feishu_online_check,
    run_checks,
)
from summit_workbench.cli.main import app
from summit_workbench.config.secrets import CredentialError, CredentialRef
from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError

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


# —— 失败分支 ——


def test_credential_check_fails_when_unresolvable(monkeypatch):
    """凭据解析失败 → FAIL，且不打印秘密值（只报能否解析）。"""

    def boom(_ref):
        raise CredentialError("item could not be found")

    monkeypatch.setattr(doctor, "resolve_credential", boom)
    check = _credential_check("测试凭据", CredentialRef(service="s", account="a"))
    assert check.status is CheckStatus.FAIL
    assert "无法解析" in check.detail


def test_feishu_online_check_reports_reauthorize(monkeypatch):
    """在线检查遇 token 失效 → FAIL 且提示 wb feishu login。"""

    class FakeSession:
        def __init__(self, _cfg):
            pass

        def access_token(self):
            raise FeishuAuthError("invalid_grant", needs_reauthorize=True)

    monkeypatch.setattr(doctor, "FeishuSession", FakeSession)
    cfg = FeishuConfig(app_id="x", redirect_uri="http://localhost/cb")
    check = _feishu_online_check(cfg)
    assert check.status is CheckStatus.FAIL
    assert "wb feishu login" in check.detail
