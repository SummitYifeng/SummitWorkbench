"""飞书授权健康度：token 失效可见性（加固 #4）。"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from summit_workbench.cli.main import app
from summit_workbench.repositories._schema import FEISHU_AUTH_STATE_VERSION
from summit_workbench.repositories.feishu_auth_state import (
    _state_path,
    read_auth_state,
    write_auth_state,
)
from summit_workbench.webapp.routers.settings import _AuthorizationStates

runner = CliRunner()


def test_missing_state_is_healthy(tmp_path):
    assert read_auth_state(tmp_path / "_vault").needs_reauthorize is False


def test_write_read_roundtrip_with_version(tmp_path):
    vault = tmp_path / "_vault"
    write_auth_state(vault, needs_reauthorize=True, day="2026-09-02", detail="token 过期")
    row = json.loads(_state_path(vault).read_text(encoding="utf-8"))
    assert row["schema_version"] == FEISHU_AUTH_STATE_VERSION
    state = read_auth_state(vault)
    assert state.needs_reauthorize is True
    assert state.detail == "token 过期"
    assert state.since_day == "2026-09-02"


def test_since_day_holds_earliest_until_recovery(tmp_path):
    vault = tmp_path / "_vault"
    write_auth_state(vault, needs_reauthorize=True, day="2026-09-02", detail="x")
    write_auth_state(vault, needs_reauthorize=True, day="2026-09-03", detail="x")
    assert read_auth_state(vault).since_day == "2026-09-02"  # 连续需授权不刷新起点
    # 恢复正常：清空 detail/since_day。
    write_auth_state(vault, needs_reauthorize=False, day="2026-09-04")
    recovered = read_auth_state(vault)
    assert recovered.needs_reauthorize is False
    assert recovered.detail is None
    assert recovered.since_day is None


def test_status_surfaces_reauthorize(monkeypatch, tmp_path):
    """写入需重新授权后，wb status 醒目提示并在 JSON 暴露（可见性端到端）。"""
    work = tmp_path / "work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    write_auth_state(vault, needs_reauthorize=True, day="2026-09-02", detail="invalid_grant")
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(work))

    js = runner.invoke(app, ["status", "--json"])
    assert js.exit_code == 0
    assert json.loads(js.stdout)["feishu_auth"]["needs_reauthorize"] is True

    human = runner.invoke(app, ["status"])
    assert "飞书授权已失效" in human.stdout
    assert "wb feishu login" in human.stdout


def test_web_authorization_state_survives_server_restart(tmp_path):
    state_file = tmp_path / "feishu-auth-state.json"
    first = _AuthorizationStates(state_file)
    state = first.issue("workspace-a")
    assert first.finish(state, workspace_id="workspace-a", status="connected") is True

    second = _AuthorizationStates(state_file)
    item = second.lookup(state)
    assert item is not None
    assert item.workspace_id == "workspace-a"
    assert item.status == "connected"
    assert second.finish(state, workspace_id="workspace-a", status="failed") is False
