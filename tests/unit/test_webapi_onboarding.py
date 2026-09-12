"""P0-08 Web /api/onboarding/* 端点测试。

服务 + API（不做 UI）：status / preflight / create / upgrade / connect；
复用 P0-05 统一错误 envelope；空安装（无 profile、无 env）status = onboarding-required。
全程临时 HOME、临时模板目录，不触真实目录。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

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
    assert (work / "_vault" / "inbox.md").is_file()
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


def test_create_via_api_rejects_cloud_path(tmp_path, monkeypatch, client) -> None:
    work = tmp_path / "OneDrive" / "Work"
    resp = client.post("/api/onboarding/create", json={"work_root": str(work)})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "onboarding_rejected"
    assert not work.exists()


def test_upgrade_via_api(tmp_path, monkeypatch, client) -> None:
    vault = tmp_path / "old-vault"
    vault.mkdir()
    (vault / "inbox.md").write_text("# inbox\n", encoding="utf-8")
    resp = client.post("/api/onboarding/upgrade", json={"vault_dir": str(vault)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["backup_dir"]
    assert (vault / ".summit-workbench" / "workspace.json").is_file()
    # 再次 upgrade → 409（已是工作区）
    again = client.post("/api/onboarding/upgrade", json={"vault_dir": str(vault)})
    assert again.status_code == 409


def test_preflight_via_api_reports_blockers(tmp_path, monkeypatch, client) -> None:
    cloud = tmp_path / "Dropbox" / "Work"
    resp = client.post(
        "/api/onboarding/preflight",
        json={"flow": "create-new", "path": str(cloud)},
    )
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert report["cloud_storage"] is True
    assert report["ok"] is False


def test_missing_marker_connect_via_api_hints_upgrade(tmp_path, monkeypatch, client) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    resp = client.post("/api/onboarding/connect", json={"vault_dir": str(plain)})
    assert resp.status_code == 409
    assert "marker" in resp.json()["message"].lower() or "升级" in resp.json()["message"]


# ---- P1-07D 第二台机器：空安装向导的私有 HTTPS 克隆旅程 ----
# 后端 remote clone（staging/confirm/cancel）此前只有 workflow 级测试，HTTP 层无覆盖；
# 这些用例把「向导暴露的入口」与「PAT 不落盘」一起锁住。


def _restricted_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """空安装（受限）app：与 wizard 测试同一入口，remote clone 路由只在这里注册。"""
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    return TestClient(create_app(None, static_dir=tmp_path / "no-static"))


def test_empty_install_wizard_offers_private_https_clone(tmp_path, monkeypatch) -> None:
    client = _restricted_client(tmp_path, monkeypatch)
    page = client.get("/")
    assert page.status_code == 200
    assert "从另一台 Mac 克隆" in page.text
    assert 'data-flow="connect-remote"' in page.text
    assert "/api/onboarding/remote/stage" in page.text
    assert "/api/onboarding/remote/confirm" in page.text
    # PAT 输入是遮挡字段，且不回声任何已有值。
    assert 'id="remote-pat" type="password" autocomplete="off"' in page.text
    assert not re.search(r'id="remote-pat"[^>]*value=', page.text)
    # 完整 app 里重开向导时不得出现这个入口（受限端点在那里也不存在）。
    assert "(fullApp ? '' : '<button class=\"choice '+(state.flow === 'connect-remote'" in page.text


def test_onboarding_draft_rejects_pat_and_keeps_non_secret_remote_facts(
    tmp_path, monkeypatch
) -> None:
    client = _restricted_client(tmp_path, monkeypatch)
    rejected = client.put(
        "/api/onboarding/draft",
        json={
            "flow": "connect-existing",
            "step": "welcome",
            "git_mode": "remote",
            "remote_url": "https://github.com/acme/private.git",
            "git_username": "alice",
            "pat": "canary-pat",
        },
    )
    assert rejected.status_code == 422
    assert "canary-pat" not in rejected.text
    accepted = client.put(
        "/api/onboarding/draft",
        json={
            "flow": "connect-existing",
            "step": "welcome",
            "git_mode": "remote",
            "remote_url": "https://github.com/acme/private.git",
            "git_username": "alice",
        },
    )
    assert accepted.status_code == 200
    draft = client.get("/api/onboarding/draft").json()["draft"]
    assert draft["git_mode"] == "remote"
    assert draft["remote_url"] == "https://github.com/acme/private.git"
    assert draft["git_username"] == "alice"
    assert draft["workspace_id"] is None


def test_remote_clone_stage_and_confirm_over_http(tmp_path, monkeypatch) -> None:
    """走空安装向导真正发出的那份 payload。

    这里**不 stub `stage_remote_clone`**：早期版本 stub 掉了它，于是"私有 clone 缺少
    expected_workspace_id"这条守卫永远走不到，真人一跑就炸（2026-09-13 实测）。
    现在只把网络 clone 换成假 backend，其余（守卫、marker 读取、兼容性、确认落盘）全是真的。
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from summit_workbench.config import secrets as secrets_mod
    from summit_workbench.domain.workspace import WorkspaceManifest
    from summit_workbench.repositories.profile_registry import load_profile
    from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
    from summit_workbench.workflows import remote_onboarding

    client = _restricted_client(tmp_path, monkeypatch)
    stored: dict[tuple[str, str], str] = {}

    def fake_resolve(ref: secrets_mod.CredentialRef):
        try:
            return SecretStr(stored[(ref.service, ref.account)])
        except KeyError as exc:  # pragma: no cover - 只在用例写坏时触发
            raise secrets_mod.CredentialError("missing") from exc

    monkeypatch.setattr(secrets_mod, "resolve_credential", fake_resolve)
    monkeypatch.setattr(
        secrets_mod,
        "store_credential",
        lambda ref, value: stored.__setitem__((ref.service, ref.account), value.get_secret_value()),
    )

    workspace_id = str(uuid4())
    manifest = WorkspaceManifest(
        schema_version=2,
        workspace_id=workspace_id,
        display_name="Remote workspace",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
        min_reader_version="0.1.0",
        min_writer_version="0.1.0",
    )

    class _FakeBackend:
        def __init__(self, path, **_kwargs) -> None:
            self.path = path

        def clone(self, url, destination) -> None:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "README.md").write_text("remote\n", encoding="utf-8")
            write_workspace_manifest(destination, manifest)

    monkeypatch.setattr(
        remote_onboarding,
        "_default_backend_factory",
        lambda path, **kwargs: _FakeBackend(path, **kwargs),
    )

    target = tmp_path / "work" / "_vault"
    target.parent.mkdir(parents=True, exist_ok=True)

    # 向导实际发出的字段：没有 expected_workspace_id（空安装根本不知道它）。
    response = client.post(
        "/api/onboarding/remote/stage",
        json={
            "remote_url": "https://github.com/acme/private.git",
            "target_vault": str(target),
            "git_username": "alice",
            "pat": "canary-pat",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["workspace_id"] == workspace_id, "workspace id 必须来自远端 marker"
    assert "canary-pat" not in response.text
    assert not target.exists(), "确认前不得落盘"

    confirmed = client.post(
        "/api/onboarding/remote/confirm",
        json={"stage_id": body["stage_id"], "pat": "canary-pat"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["workspace_id"] == workspace_id
    assert "canary-pat" not in confirmed.text
    assert target.is_dir(), "确认后 staging 被原子移动到目标"
    profile = load_profile(workspace_id, home=_tmp_home(client))
    assert profile is not None
    assert profile.device_role.value == "secondary"
    # PAT 只落到 workspace 作用域 Keychain 命名下。
    assert stored == {
        ("com.summitworkbench.credentials." + workspace_id, "git:github.com:alice"): "canary-pat",
    }


def test_remote_clone_failure_is_coded_and_never_leaks_pat(tmp_path, monkeypatch) -> None:
    from summit_workbench.workflows import remote_onboarding

    client = _restricted_client(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise remote_onboarding.RemoteCloneError(
            "remote_missing_marker", "远端没有 workspace marker"
        )

    monkeypatch.setattr(remote_onboarding, "stage_remote_clone", boom)
    response = client.post(
        "/api/onboarding/remote/stage",
        json={
            "remote_url": "https://github.com/acme/private.git",
            "target_vault": str(tmp_path / "work" / "_vault"),
            "git_username": "alice",
            "pat": "canary-pat",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "remote_missing_marker"
    assert "canary-pat" not in response.text
