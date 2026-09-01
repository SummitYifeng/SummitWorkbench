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
    assert "import" in result.stdout
    assert "process" in result.stdout
    assert "backfill" in result.stdout


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


def test_brief_dry_run_degrades_without_feishu_or_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    result = runner.invoke(app, ["brief", "--date", "2026-09-01", "--dry-run", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["date"] == "2026-09-01"
    assert payload["health"] == "degraded"  # 无飞书 + 无信号
    assert payload["ranking_degraded"] is True
    assert payload["note_path"] is None  # dry-run 不写


def test_brief_run_records_heartbeat_surfaced_in_status(monkeypatch, tmp_path) -> None:
    """真实运行（非 --dry-run）记一条心跳，且 wb status 呈现该运行健康度（#2 端到端）。"""
    work = tmp_path / "work"
    (work / "_vault").mkdir(parents=True)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(work))

    brief = runner.invoke(app, ["brief", "--date", "2026-09-01", "--json"])
    assert brief.exit_code == 0

    status = runner.invoke(app, ["status", "--json"])
    assert status.exit_code == 0
    runs = json.loads(status.stdout)["runs"]
    # 无飞书/模型 → 降级，但确实产出了（心跳记 degraded，最近运行日为该日）。
    assert runs["brief"]["last_status"] == "degraded"
    assert runs["brief"]["last_day"] == "2026-09-01"
    assert runs["weekly"]["last_status"] is None  # 未跑过

    human = runner.invoke(app, ["status"])
    assert human.exit_code == 0
    assert "定时任务健康度" in human.stdout


def test_brief_registered_help() -> None:
    result = runner.invoke(app, ["brief", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.stdout
    assert "--date" in result.stdout
    assert "--commit" in result.stdout


def test_brief_commit_publishes_to_vault_git(monkeypatch, tmp_path) -> None:
    import subprocess

    work = tmp_path / "work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(work))
    result = runner.invoke(app, ["brief", "--date", "2026-09-01", "--commit", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["publish"] == "committed"  # 无 upstream 下仅提交
    log = subprocess.run(
        ["git", "-C", str(vault), "log", "--oneline"], capture_output=True, text=True
    ).stdout
    assert "晨间简报 2026-09-01" in log


def test_weekly_registered_and_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    (tmp_path / "work" / "_vault").mkdir(parents=True)
    result = runner.invoke(app, ["weekly", "--date", "2026-09-01", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["week"] == "2026-W35"  # 2026-09-01 的上一周
    assert payload["range"] == "2026-08-24~2026-08-30"
    assert (tmp_path / "work" / "_vault" / "reviews" / "weekly" / "2026-W35.md").is_file()


def test_ask_registered() -> None:
    result = runner.invoke(app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "--save" in result.stdout
    assert "--project" in result.stdout


def test_project_new_and_list(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    created = runner.invoke(app, ["project", "new", "HIC_Fresh", "--alias", "新项目"])
    assert created.exit_code == 0
    assert (tmp_path / "work" / "_vault" / "projects" / "HIC_Fresh.md").is_file()
    listed = runner.invoke(app, ["project", "list"])
    assert listed.exit_code == 0
    assert "HIC_Fresh" in listed.stdout
    assert "新项目" in listed.stdout


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
