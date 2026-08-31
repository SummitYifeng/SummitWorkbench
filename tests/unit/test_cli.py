"""CLI 冒烟测试：version / diagnose / help 可运行，退出码正确。"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from summit_workbench import __version__
from summit_workbench.cli.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "diagnose" in result.stdout
    assert "version" in result.stdout


def test_meeting_group_registered() -> None:
    result = runner.invoke(app, ["meeting", "--help"])
    assert result.exit_code == 0
    assert "archive" in result.stdout
    assert "archive-local" in result.stdout
    assert "process" in result.stdout


def test_review_group_registered() -> None:
    result = runner.invoke(app, ["review", "--help"])
    assert result.exit_code == 0
    assert "refresh" in result.stdout
    assert "apply" in result.stdout


def test_status_registered_and_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "state_counts" in payload
    assert payload["pending_review"] == 0
    assert payload["budget"]["over_soft_limit"] is False


def test_ask_registered() -> None:
    result = runner.invoke(app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "--save" in result.stdout
    assert "--project" in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # no_args_is_help=True：无参数打印帮助并以 Click 约定退出码 2 结束。
    assert result.exit_code == 2
    assert "diagnose" in result.stdout


def test_diagnose_json_is_parseable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    result = runner.invoke(app, ["diagnose", "--json"])
    payload = json.loads(result.stdout)
    assert "python_ok" in payload
    assert "tools" in payload
    # 诊断输出绝不含秘密字段。
    assert "secret" not in result.stdout.lower()


def test_diagnose_exit_code_reflects_readiness(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    result = runner.invoke(app, ["diagnose"])
    # 就绪 → 0，缺失 → 1；本机通常就绪，这里只断言取值合法。
    assert result.exit_code in (0, 1)
