"""G2：首次发布端点的稳定错误面（工作流本身在 test_remote_publish.py 里单测）。

这里只钉住 API 契约：缺 active workspace ⇒ workspace_not_configured；工作流抛
稳定码 ⇒ 原样 409 返回；成功 ⇒ 带回 remote_url/branch/head。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.profile_registry import save_profile, set_active_profile
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.workflows import remote_publish as workflow

PAYLOAD = {
    "candidate_url": "https://github.com/owner/repo.git",
    "git_username": "alice",
    "pat": "pat-never-on-disk-1234",
}


def _workspace(tmp_path: Path) -> LocalProfile:
    workspace_id = str(uuid4())
    vault = tmp_path / "work" / "_vault"
    vault.mkdir(parents=True, exist_ok=True)
    profile = LocalProfile(
        workspace_id=workspace_id,
        display_name="publish-api",
        work_root=tmp_path / "work",
        vault_dir=vault,
        device_role=DeviceRole.SECONDARY,
        created_at=datetime.now(UTC),
    )
    save_profile(profile, home=tmp_path)
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            workspace_id=workspace_id,
            display_name=profile.display_name,
            created_at=datetime.now(UTC),
            min_reader_version="0.1.0",
            min_writer_version="0.1.0",
        ),
    )
    set_active_profile(workspace_id, home=tmp_path)
    return profile


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    context = resolve_active_workspace(home=tmp_path, allow_env_fallback=False)
    return TestClient(create_app(WebContext.from_active_workspace(context)))


def test_publish_endpoint_requires_active_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client = TestClient(
        create_app(
            WebContext(tmp_path / "vault", tmp_path / "vault", "UTC"),
            static_dir=tmp_path / "no-static",
        )
    )
    response = client.post("/api/settings/git/remote/publish", json=PAYLOAD)
    assert response.status_code == 409
    assert response.json()["code"] == "workspace_not_configured"


def test_publish_endpoint_returns_binding_and_surfaces_stable_codes(
    tmp_path: Path, monkeypatch
) -> None:
    _workspace(tmp_path)
    client = _client(tmp_path, monkeypatch)

    def fake_publish(*args: object, **kwargs: object) -> workflow.RemotePublishResult:
        return workflow.RemotePublishResult(
            remote_url=PAYLOAD["candidate_url"], workspace_id="ws", branch="main", head="a" * 40
        )

    monkeypatch.setattr(workflow, "publish_workspace_to_remote", fake_publish)
    ok = client.post("/api/settings/git/remote/publish", json=PAYLOAD)
    assert ok.status_code == 200, ok.text
    assert ok.json() == {
        "ok": True,
        "remote_url": PAYLOAD["candidate_url"],
        "branch": "main",
        "head": "a" * 40,
        "note": "origin 与 upstream 已绑定并完成首次推送；未修改 vault 内容",
    }

    def refuse(*args: object, **kwargs: object) -> workflow.RemotePublishResult:
        raise workflow.RemotePublishError("remote_not_empty", "目标远端已有提交")

    monkeypatch.setattr(workflow, "publish_workspace_to_remote", refuse)
    rejected = client.post("/api/settings/git/remote/publish", json=PAYLOAD)
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "remote_not_empty"
    assert "pat-never-on-disk-1234" not in rejected.text
