"""P0-08 Web /api/onboarding/* 端点测试。

服务 + API（不做 UI）：status / preflight / create / upgrade / connect；
复用 P0-05 统一错误 envelope；空安装（无 profile、无 env）status = onboarding-required。
全程临时 HOME、临时模板目录，不触真实目录。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """应用固定在临时 ctx 上；HOME/WB_VAULT_TEMPLATES 全部隔离到 tmp。"""
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "inbox.template.md").write_text(
        "---\ndate: {{date}}\n---\n# 收件箱\n", encoding="utf-8"
    )
    monkeypatch.setenv("WB_VAULT_TEMPLATES", str(templates))
    app = create_app(
        WebContext(tmp_path / "vault", tmp_path, "UTC"),
        static_dir=tmp_path / "no-static",
    )
    return TestClient(app)


def _tmp_home(client: TestClient) -> Path:
    # fixture 中 HOME 指向 tmp_path/fake-home
    import os

    return Path(os.environ["HOME"])


def test_status_onboarding_required_when_empty(tmp_path, monkeypatch, client) -> None:
    resp = client.get("/api/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["state"] == "onboarding-required"
    # 空安装不创建任何目录
    home = _tmp_home(client)
    assert not (home / "Documents" / "Work").exists()
    assert not (home / "Library" / "Application Support" / "SummitWorkbench").exists()


def test_restricted_onboarding_accepts_dynamic_loopback_same_origin(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    app = create_app(
        None,
        static_dir=tmp_path / "no-static",
        bind_host="127.0.0.1",
        port=0,
        session_token="token",
    )
    client = TestClient(app, base_url="http://127.0.0.1:43123")
    response = client.put(
        "/api/onboarding/draft",
        json={"flow": "upgrade-existing", "step": "location", "provider_status": "skipped"},
        headers={
            "Origin": "http://127.0.0.1:43123",
            "X-WB-Session-Token": "token",
        },
    )
    assert response.status_code == 200, response.text


def test_preflight_and_create_via_api(tmp_path, monkeypatch, client) -> None:
    work = tmp_path / "api-work"
    payload = {"work_root": str(work), "display_name": "API Workspace"}
    resp = client.post("/api/onboarding/create", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    workspace_id = data["workspace_id"]
    assert (work / "inbox.md").is_file()
    # status 转 active
    status = client.get("/api/onboarding/status").json()
    assert status["workspace_id"] == workspace_id

    # 重复 create → 409 + 错误 envelope
    again = client.post("/api/onboarding/create", json=payload)
    assert again.status_code == 409
    body = again.json()
    assert body["ok"] is False
    assert body["code"] == "onboarding_rejected"
    assert body["operation_id"]
    assert "message" in body


def test_create_via_api_allows_cloud_path(tmp_path, monkeypatch, client) -> None:
    work = tmp_path / "OneDrive" / "Work"
    resp = client.post("/api/onboarding/create", json={"work_root": str(work)})
    assert resp.status_code == 200, resp.text
    assert (work / ".summit-workbench" / "manifest.json").is_file()


def test_legacy_upgrade_route_is_retired(tmp_path, monkeypatch, client) -> None:
    vault = tmp_path / "old-vault"
    vault.mkdir()
    (vault / "inbox.md").write_text("# inbox\n", encoding="utf-8")
    resp = client.post("/api/onboarding/upgrade", json={"vault_dir": str(vault)})
    assert resp.status_code == 404


def test_preflight_via_api_reports_blockers(tmp_path, monkeypatch, client) -> None:
    cloud = tmp_path / "Dropbox" / "Work"
    resp = client.post(
        "/api/onboarding/preflight",
        json={"flow": "create-new", "path": str(cloud)},
    )
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert report["cloud_storage"] is True
    assert report["ok"] is True
    assert report["rejections"] == []


def test_nonempty_unrecognized_folder_is_not_adopted(tmp_path, monkeypatch, client) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    resp = client.post("/api/onboarding/connect", json={"vault_dir": str(plain)})
    assert resp.status_code == 409
    assert "契约" in resp.json()["message"]


# ---- restricted app 的首启向导 ----


def _restricted_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """空安装（受限）app：与 wizard 测试同一入口。"""
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    return TestClient(create_app(None, static_dir=tmp_path / "no-static"))


def test_git_remote_onboarding_endpoints_are_retired(tmp_path, monkeypatch) -> None:
    client = _restricted_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/onboarding/remote/stage",
        json={
            "remote_url": "https://example.invalid/repo.git",
            "target_vault": str(tmp_path / "x"),
        },
    )
    assert response.status_code == 404


def test_wizard_api_client_surfaces_non_json_responses(tmp_path, monkeypatch) -> None:
    """向导的 `api()` 不能无条件 `response.json()`——非 JSON 响应要报 HTTP 状态与片段。"""
    page = _restricted_client(tmp_path, monkeypatch).get("/")
    assert "await response.text()" in page.text
    assert "JSON.parse(raw)" in page.text
    assert "（空响应）" in page.text
    assert "克隆" not in page.text
    assert "remote-pat" not in page.text
