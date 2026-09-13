"""G1：主设备声明/接管与降级入口的后端行为（含 profile 角色同步）。

覆盖真机上的关键缺口：界面没有 automation-primary 的接管入口，且声明成功后本机
``device_role`` 不会跟着更新（D10 的"可改"能力）。这里逐条断言：

- 声明本机 ⇒ profile 角色变 automation-primary，响应带回角色；
- 声明别的设备 ⇒ 本机角色**不变**，且再次声明本机必须 primary_already_claimed；
- takeover 必须带当前 generation，generation 冲突报稳定码；
- 降级只改本机 profile，vault 内声明一个字节都不动。

变异验证（去掉修复必须让本用例失败）：
- 移除 claim 后的 ``_sync_local_role`` 调用 ⇒ 本机角色断言失败；
- 把 ``api_downgrade_primary`` 改成也重写 vault 声明 ⇒ 声明不变断言失败。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from summit_workbench.config.profiles import resolve_active_workspace
from summit_workbench.domain.workspace import DeviceRole, LocalProfile, WorkspaceManifest
from summit_workbench.repositories.automation_primary import load_automation_primary
from summit_workbench.repositories.profile_registry import (
    ensure_device_identity,
    load_profile,
    save_profile,
    set_active_profile,
)
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app import WebContext, create_app


def _workspace(tmp_path: Path, role: DeviceRole = DeviceRole.SECONDARY) -> LocalProfile:
    workspace_id = str(uuid4())
    vault = tmp_path / "work" / "_vault"
    vault.mkdir(parents=True, exist_ok=True)
    profile = LocalProfile(
        workspace_id=workspace_id,
        display_name="primary-ws",
        work_root=tmp_path / "work",
        vault_dir=vault,
        device_role=role,
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


def _claim(client: TestClient, **body: object):
    return client.post("/api/sync/primary/claim", json=body)


def test_claim_for_this_device_syncs_profile_role(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _workspace(tmp_path, DeviceRole.SECONDARY)
    device_id = ensure_device_identity(home=tmp_path).device_id
    client = _client(tmp_path, monkeypatch)

    response = _claim(client, device_id=device_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["claim"]["device_id"] == device_id
    assert payload["claim"]["generation"] == 1
    # 声明成功后本机角色必须同步（否则定时自动化在本机仍然被 gate 挡住）
    assert payload["device_role"] == DeviceRole.AUTOMATION_PRIMARY.value

    stored = load_profile(profile.workspace_id, home=tmp_path)
    assert stored is not None
    assert stored.device_role is DeviceRole.AUTOMATION_PRIMARY
    claim = load_automation_primary(profile.vault_dir)
    assert claim is not None and claim.device_id == device_id


def test_claim_for_other_device_keeps_local_role_and_blocks_silent_takeover(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _workspace(tmp_path, DeviceRole.SECONDARY)
    local_device = ensure_device_identity(home=tmp_path).device_id
    other_device = str(uuid4())
    client = _client(tmp_path, monkeypatch)

    first = _claim(client, device_id=other_device)
    assert first.status_code == 200, first.text
    # 别的设备成为主设备时，本机角色不得被顺手改成 primary
    assert first.json()["device_role"] == DeviceRole.SECONDARY.value
    still_secondary = load_profile(profile.workspace_id, home=tmp_path)
    assert still_secondary is not None
    assert still_secondary.device_role is DeviceRole.SECONDARY

    # 本机想成为主设备必须显式 takeover，且要基于当前 generation
    blocked = _claim(client, device_id=local_device)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "primary_already_claimed"

    wrong_generation = _claim(client, device_id=local_device, takeover=True, expected_generation=99)
    assert wrong_generation.status_code == 409
    assert wrong_generation.json()["code"] == "primary_generation_conflict"

    taken = _claim(client, device_id=local_device, takeover=True, expected_generation=1)
    assert taken.status_code == 200, taken.text
    assert taken.json()["claim"]["generation"] == 2
    assert taken.json()["device_role"] == DeviceRole.AUTOMATION_PRIMARY.value
    stored = load_profile(profile.workspace_id, home=tmp_path)
    assert stored is not None and stored.device_role is DeviceRole.AUTOMATION_PRIMARY


def test_downgrade_only_changes_local_profile_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = _workspace(tmp_path, DeviceRole.AUTOMATION_PRIMARY)
    device_id = ensure_device_identity(home=tmp_path).device_id
    client = _client(tmp_path, monkeypatch)
    claimed = _claim(client, device_id=device_id)
    assert claimed.status_code == 200, claimed.text
    before = load_automation_primary(profile.vault_dir)
    assert before is not None

    downgraded = client.post("/api/sync/primary/downgrade")
    assert downgraded.status_code == 200, downgraded.text
    assert downgraded.json()["device_role"] == DeviceRole.SECONDARY.value
    stored = load_profile(profile.workspace_id, home=tmp_path)
    assert stored is not None and stored.device_role is DeviceRole.SECONDARY

    # vault 内的声明保持原样：降级只是本机不再跑自动化，主设备归属没变
    after = load_automation_primary(profile.vault_dir)
    assert after is not None
    assert (after.device_id, after.generation) == (before.device_id, before.generation)

    # 幂等：已经是 secondary 再点一次也是 200
    again = client.post("/api/sync/primary/downgrade")
    assert again.status_code == 200
    assert again.json()["device_role"] == DeviceRole.SECONDARY.value


def test_downgrade_without_active_workspace_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    client = TestClient(
        create_app(
            WebContext(tmp_path / "vault", tmp_path / "vault", "UTC"),
            static_dir=tmp_path / "no-static",
        )
    )
    response = client.post("/api/sync/primary/downgrade")
    assert response.status_code == 409
    assert response.json()["code"] == "workspace_not_configured"
