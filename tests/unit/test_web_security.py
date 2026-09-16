"""P0-05：本地 Web 绑定、请求边界、上传上限与错误 envelope。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app
from summit_workbench.webapp.security import validate_bind_host


def _client(
    tmp_path: Path,
    *,
    host: str = "127.0.0.1",
    mode: str | None = None,
    token: str | None = None,
) -> TestClient:
    if mode is not None:
        import os

        os.environ["WB_PANEL_MODE"] = mode
    if token is not None:
        import os

        os.environ["WB_SESSION_TOKEN"] = token
    ctx = WebContext(vault_dir=tmp_path / "_vault", work_root=tmp_path, timezone="Asia/Shanghai")
    base_host = "127.0.0.1" if mode == "production" else host
    return TestClient(
        create_app(ctx, static_dir=tmp_path / "no-static", bind_host=host),
        base_url=f"http://{base_host}:8787",
    )


def test_production_rejects_non_loopback_bind(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    with pytest.raises(ValueError, match="loopback"):
        _client(tmp_path, host="0.0.0.0")


def test_explicit_open_bind_warns(monkeypatch) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "development-external")
    with pytest.warns(UserWarning, match="认证"):
        validate_bind_host("192.0.2.10", "development-external")


def test_production_does_not_accept_testclient_host(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    client = _client(tmp_path, mode="production")
    response = client.get("/api/state", headers={"Host": "testserver:8787"})
    assert response.status_code == 403
    assert response.json()["code"] == "host_not_allowed"


def test_spoofed_host_is_rejected(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/state", headers={"Host": "evil.example"})
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "host_not_allowed"
    assert body["operation_id"]


def test_cross_origin_write_is_rejected_and_same_origin_is_allowed(tmp_path: Path) -> None:
    client = _client(tmp_path)
    cross = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={"Origin": "http://evil.example"},
    )
    assert cross.status_code == 403
    assert cross.json()["code"] == "origin_not_allowed"

    same = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={"Origin": "http://testserver"},
    )
    assert same.status_code != 403


def test_dynamic_loopback_same_origin_write_is_allowed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    ctx = WebContext(vault_dir=tmp_path / "_vault", work_root=tmp_path, timezone="UTC")
    client = TestClient(
        create_app(
            ctx,
            static_dir=tmp_path / "no-static",
            bind_host="127.0.0.1",
            port=0,
            session_token="token",
        ),
        base_url="http://127.0.0.1:43123",
    )
    response = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={
            "Origin": "http://127.0.0.1:43123",
            "X-WB-Session-Token": "token",
        },
    )
    assert response.status_code != 403


def test_production_originless_write_requires_session_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "production")
    client = _client(tmp_path, mode="production")
    response = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_external_bind_same_origin_write_requires_session_token(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("WB_PANEL_MODE", "development-external")
    client = _client(tmp_path, host="192.0.2.10", mode="development-external", token="secret")
    response = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={"Origin": "http://192.0.2.10:8787"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"

    accepted = client.post(
        "/api/review/decide",
        json={"candidate_id": "missing", "decision": "approved"},
        headers={
            "Origin": "http://192.0.2.10:8787",
            "X-WB-Session-Token": "secret",
        },
    )
    assert accepted.status_code != 401


def test_oversized_fields_and_batches_use_422_envelope(tmp_path: Path) -> None:
    client = _client(tmp_path)
    capture = client.post("/api/capture", json={"text": "x" * 100_001})
    assert capture.status_code == 422
    assert capture.json()["code"] == "validation_error"
    assert capture.json()["operation_id"]

    batch = client.post(
        "/api/review/batch",
        json={"candidate_ids": [f"c-{i}" for i in range(101)], "decision": "approved"},
    )
    assert batch.status_code == 422
    assert batch.json()["code"] == "validation_error"


def test_upload_reads_in_chunks_and_rejects_after_10_mib(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def fake_import(_ctx: object, path: Path) -> dict[str, object]:
        seen["path"] = path.name
        return {"ok": True, "path": path.name}

    monkeypatch.setattr("summit_workbench.webapp.app._run_web_import", fake_import)
    client = _client(tmp_path)
    exact = client.post(
        "/api/meetings/import",
        files={"file": ("../meeting.md", io.BytesIO(b"x" * (10 * 1024 * 1024)), "text/markdown")},
    )
    assert exact.status_code == 200
    assert seen["path"] == "meeting.md"

    oversized = client.post(
        "/api/meetings/import",
        files={"file": ("meeting.md", io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "text/markdown")},
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "upload_too_large"
