"""P1-05 本机日志、脱敏与诊断包契约测试。"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from summit_workbench.domain.workspace import WorkspaceManifest
from summit_workbench.observability.redaction import redact_fields, redact_text
from summit_workbench.observability.structured_logging import StructuredLogger
from summit_workbench.observability.support_bundle import bundle_bytes, diagnostic_snapshot
from summit_workbench.repositories.workspace_manifest import write_workspace_manifest
from summit_workbench.webapp.app_factory import AppContext, create_app

CANARY = "canary-secret-token-pat-api-key"
MEETING_BODY = "Confidential meeting body: discuss the unreleased plan."


def _context(tmp_path: Path) -> AppContext:
    vault = tmp_path / "vault"
    write_workspace_manifest(
        vault,
        WorkspaceManifest(
            workspace_id=str(uuid4()),
            display_name="Diagnostics test workspace",
            created_at=datetime(2026, 9, 6, tzinfo=UTC),
            min_reader_version="0.1.0",
            min_writer_version="0.1.0",
        ),
    )
    return AppContext(vault, tmp_path / "work", "UTC")


def test_redactor_removes_secret_body_auth_cookie_remote_url_and_home_path() -> None:
    raw = (
        f"{CANARY} {MEETING_BODY} Authorization: Bearer abc.def "
        "Cookie: session=secret-value "
        "https://alice:password@example.com/model "
        "/Users/alice/Library/Logs/summitworkbench-panel.log"
    )

    redacted = redact_text(raw)

    assert CANARY not in redacted
    assert MEETING_BODY not in redacted
    assert "abc.def" not in redacted
    assert "secret-value" not in redacted
    assert "alice:password@" not in redacted
    assert "/Users/alice" not in redacted
    assert "provider_token_invalid" in redact_text("provider_token_invalid")


def test_redactor_drops_sensitive_fields_and_nested_body() -> None:
    result = redact_fields(
        {
            "prompt": MEETING_BODY,
            "access_token": CANARY,
            "nested": {"body": MEETING_BODY},
            "count": 3,
            "state": "offline",
        }
    )

    assert result["prompt"] == "[redacted]"
    assert result["access_token"] == "[redacted]"
    assert result["nested"] == "[redacted]"
    assert result["count"] == 3
    assert result["state"] == "offline"
    assert MEETING_BODY not in json.dumps(result)
    assert CANARY not in json.dumps(result)


def test_structured_logger_has_required_fields_and_rotates_without_leaking(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "panel.log"
    logger = StructuredLogger(path, component="test", max_bytes=180)
    for index in range(8):
        logger.log(
            "provider_failed",
            level="error",
            operation_id="12345678-1234-4234-8234-123456789abc",
            workspace_id="87654321-1234-4234-8234-123456789abc",
            device_id="abcdefab-1234-4234-8234-123456789abc",
            error_code="authentication_required",
            fields={"message": f"{CANARY} {MEETING_BODY} {index}"},
        )

    recent = logger.recent()
    assert recent
    required = {
        "timestamp",
        "level",
        "component",
        "event",
        "operation_id",
        "workspace_id",
        "device_id",
        "error_code",
    }
    assert required <= recent[-1].keys()
    assert recent[-1]["operation_id"] == "12345678"
    assert CANARY not in path.read_text(encoding="utf-8")
    assert MEETING_BODY not in path.read_text(encoding="utf-8")
    assert path.with_name("panel.log.1").is_file()


def test_diagnostic_bundle_is_a_single_sanitized_file(tmp_path: Path) -> None:
    context = _context(tmp_path)
    log_path = tmp_path / "panel.log"
    StructuredLogger(log_path, component="server").log(
        "server_error",
        level="error",
        error_code="offline",
        fields={"message": f"{CANARY} {MEETING_BODY}"},
    )

    snapshot = diagnostic_snapshot(
        context, static_dir=tmp_path / "missing-static", log_path=log_path
    )
    payload = json.dumps(snapshot, ensure_ascii=False)
    assert snapshot["schema_version"] == 1
    assert snapshot["workspace"]["schema_state"] == "valid"  # type: ignore[index]
    assert snapshot["signature"] == {"mode": "internal-ad-hoc", "notarized": False}
    assert CANARY not in payload
    assert MEETING_BODY not in payload
    assert "config_keys" in snapshot

    with zipfile.ZipFile(BytesIO(bundle_bytes(snapshot))) as archive:
        assert archive.namelist() == ["diagnostics.json"]
        bundle_text = archive.read("diagnostics.json").decode("utf-8")
    assert CANARY not in bundle_text
    assert MEETING_BODY not in bundle_text


def test_diagnostics_routes_preview_and_export_without_real_home(
    tmp_path: Path, monkeypatch
) -> None:
    fake_home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(fake_home))
    app = create_app(_context(tmp_path), static_dir=tmp_path / "missing-static")
    client = TestClient(app)

    preview = client.get("/api/diagnostics/preview")
    assert preview.status_code == 200
    assert preview.json()["files"] == [
        {
            "name": "diagnostics.json",
            "description": "版本、架构、schema、状态摘要、脱敏错误、签名和同步计数",
        }
    ]

    exported = client.get("/api/diagnostics/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    assert "diagnostics.json" in zipfile.ZipFile(BytesIO(exported.content)).namelist()
    assert not fake_home.exists() or not list(fake_home.rglob("*"))
