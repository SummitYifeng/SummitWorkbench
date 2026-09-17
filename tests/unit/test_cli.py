"""CLI 冒烟测试：version / diagnose / help 可运行，退出码正确。"""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from summit_workbench import __version__
from summit_workbench.cli.main import app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _help_text(*args: str) -> str:
    """渲染子命令 --help 并返回去除 ANSI 的纯文本。

    固定宽终端渲染：Typer/Rich 的选项面板在窄终端（如 CI runner）会把选项名截断成
    ``--dry-…``，导致按选项名做子串断言不稳定。强制 COLUMNS 宽 + 去 ANSI 让断言稳定。
    """
    result = runner.invoke(app, [*args, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    return _ANSI.sub("", result.stdout)


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
    text = _help_text("brief")
    assert "--dry-run" in text
    assert "--date" in text
    assert "--commit" in text


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


def test_help_omits_retired_local_search_commands() -> None:
    text = _help_text()
    assert re.search(r"(?m)^│\s+ask\s", text) is None
    assert re.search(r"(?m)^│\s+kb\s", text) is None


@pytest.mark.parametrize("command", ["ask", "kb"])
def test_retired_local_search_commands_are_unknown(command: str) -> None:
    result = runner.invoke(app, [command])
    assert result.exit_code == 2
    assert f"No such command '{command}'" in result.output


def test_model_smoke_help_omits_retired_qa_capability() -> None:
    assert "qa" not in _help_text("model", "smoke")


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


def test_web_help_shows_open_flag() -> None:
    result = _help_text("web")
    assert "--open" in result
    assert "后台拉起" in result


def test_status_notify_delivers_macos_notification(monkeypatch, tmp_path) -> None:
    """wb status --notify 把评估出的新通知发到 macOS 通知中心（osascript 替身）。"""
    from summit_workbench.observability.alerts import Notification

    sent: list[tuple[str, str, str | None]] = []

    def fake_send(title: str, message: str, *, subtitle: str | None = None) -> bool:
        sent.append((title, message, subtitle))
        return True

    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setattr("summit_workbench.observability.notifier.send_notification", fake_send)
    monkeypatch.setattr(
        "summit_workbench.cli.status.check_and_update",
        lambda _vault, _report: [Notification("backlog", "待确认积压需要处理：测试积压。")],
    )
    result = runner.invoke(app, ["status", "--notify"])
    assert result.exit_code == 0
    assert len(sent) == 1
    title, message, subtitle = sent[0]
    assert title == "SummitWorkbench"
    assert "测试积压" in message
    assert subtitle == "待确认积压"
