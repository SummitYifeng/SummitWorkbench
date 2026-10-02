from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.webapp.app import WebContext, create_app


def _client(tmp_path: Path) -> TestClient:
    context = WebContext(
        vault_dir=tmp_path / "_vault",
        work_root=tmp_path,
        timezone="Asia/Shanghai",
    )
    return TestClient(create_app(context, static_dir=tmp_path / "no-static"))


def test_draft_api_saves_lists_reads_and_deletes_in_workspace(tmp_path: Path) -> None:
    client = _client(tmp_path)
    key = "journal-log:daily"
    saved = client.put(
        f"/api/drafts/{key}",
        json={"type": "journal-log", "id": "daily", "value": {"did": "继续推进"}},
    )
    assert saved.status_code == 200
    assert saved.json()["message"] == "草稿已保存在本机"
    assert client.get(f"/api/drafts/{key}").json()["draft"]["value"]["did"] == "继续推进"
    listed = client.get("/api/drafts").json()["drafts"]
    assert len(listed) == 1 and listed[0]["type"] == "journal-log"
    removed = client.delete(f"/api/drafts/{key}")
    assert removed.json()["deleted"] is True
    assert client.get(f"/api/drafts/{key}").json()["draft"] is None


def test_draft_api_rejects_secrets_uploads_and_mismatched_identity(tmp_path: Path) -> None:
    client = _client(tmp_path)
    secret = client.put(
        "/api/drafts/journal-thought:one",
        json={
            "type": "journal-thought",
            "id": "one",
            "value": {"problem": "x", "api_key": "never persist"},
        },
    )
    mismatch = client.put(
        "/api/drafts/journal-thought:one",
        json={"type": "journal-thought", "id": "two", "value": {"problem": "x"}},
    )

    assert secret.status_code == 422
    assert mismatch.status_code == 422


def test_draft_delete_of_missing_entry_is_idempotent(tmp_path: Path) -> None:
    response = _client(tmp_path).delete("/api/drafts/journal-log:missing")
    assert response.status_code == 200
    assert response.json()["deleted"] is False
