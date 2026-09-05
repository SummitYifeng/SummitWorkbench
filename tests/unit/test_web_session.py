"""P0-12 生产面板会话隔离与动态实例握手。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app

_STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "summit_workbench" / "webapp" / "static"


def _client(tmp_path: Path, token: str, workspace: str, instance: str) -> TestClient:
    ctx = WebContext(
        vault_dir=tmp_path / f"{workspace}-vault",
        work_root=tmp_path,
        timezone="Asia/Shanghai",
    )
    return TestClient(
        create_app(
            ctx,
            static_dir=_STATIC_DIR,
            bind_host="127.0.0.1",
            session_token=token,
            workspace_id=workspace,
            server_instance=instance,
        ),
        base_url="http://127.0.0.1:8787",
    )


def test_production_sensitive_read_and_write_require_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    client = _client(tmp_path, "token-a", "workspace-a", "instance-a")

    assert client.get("/api/version").status_code == 401
    assert client.get("/api/state").status_code == 401
    assert (
        client.post(
            "/api/review/decide",
            json={"candidate_id": "missing", "decision": "approved"},
        ).status_code
        == 401
    )

    response = client.get("/api/version", cookies={"wb_session": "token-a"})
    assert response.status_code == 200
    assert response.json()["server_instance"] == "instance-a"

    response = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={"X-WB-Session-Token": "token-a"},
    )
    assert response.status_code != 401


def test_wrong_or_cross_workspace_session_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    first = _client(tmp_path, "token-a", "workspace-a", "instance-a")
    second = _client(tmp_path, "token-b", "workspace-b", "instance-b")

    assert first.get("/api/version", cookies={"wb_session": "token-b"}).status_code == 401
    assert second.get("/api/version", cookies={"wb_session": "token-a"}).status_code == 401


def test_development_bootstrap_exchanges_one_time_token_for_cookie(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "development-managed")
    client = _client(tmp_path, "dev-token", "workspace-a", "instance-a")

    response = client.get("/api/session/bootstrap?token=dev-token", follow_redirects=False)
    assert response.status_code == 303
    assert "wb_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "token=" not in response.headers["location"]
