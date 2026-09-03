"""P0' Web 撤销三端点冒烟（U4）：history / diff / revert，含错误分支与「飞书侧不可撤销」文案。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from summit_workbench.repositories.autocommit import commit_paths
from summit_workbench.webapp.app import WebContext, create_app


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)


def _git_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q")
    _git(vault, "config", "user.email", "t@t.test")
    _git(vault, "config", "user.name", "Tester")
    (vault / "seed.txt").write_text("seed", encoding="utf-8")
    _git(vault, "add", "seed.txt")
    _git(vault, "commit", "-q", "-m", "chore: seed")
    return vault


def _client(vault: Path) -> TestClient:
    ctx = WebContext(vault_dir=vault, work_root=vault.parent, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx, static_dir=vault.parent / "no-static"))


def test_u4_history_not_git_graceful(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    r = _client(vault).get("/api/undo/history")
    body = r.json()
    assert body["ok"] is True
    assert body["commits"] == []
    assert "不是 git 仓库" in body["note"]


def test_u4_history_lists_wb_commits(tmp_path: Path) -> None:
    vault = _git_vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("# inbox\n- [ ] 一条", encoding="utf-8")
    commit_paths(vault, [target], "wb: capture")
    r = _client(vault).get("/api/undo/history")
    body = r.json()
    assert body["ok"] is True
    assert len(body["commits"]) == 1
    assert body["commits"][0]["message"] == "wb: capture"
    assert "inbox.md" in body["commits"][0]["files"]


def test_u4_diff_ok_and_error(tmp_path: Path) -> None:
    vault = _git_vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("# inbox\n- [ ] 一条", encoding="utf-8")
    commit_paths(vault, [target], "wb: capture")
    client = _client(vault)
    sha = client.get("/api/undo/history").json()["commits"][0]["sha"]
    ok = client.get("/api/undo/diff", params={"sha": sha})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert "- [ ] 一条" in ok.json()["diff"]
    bad = client.get("/api/undo/diff", params={"sha": "deadbeef" * 5})
    assert bad.json()["ok"] is False


def test_u4_revert_restores_file_with_flynote(tmp_path: Path) -> None:
    vault = _git_vault(tmp_path)
    target = vault / "projects" / "P1.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text("v1", encoding="utf-8")
    _git(vault, "add", "projects/P1.md")
    _git(vault, "commit", "-q", "-m", "chore: v1")
    target.write_text("v2", encoding="utf-8")
    commit_paths(vault, [target], "wb: threads/state")
    client = _client(vault)
    sha = client.get("/api/undo/history").json()["commits"][0]["sha"]
    r = client.post("/api/undo/revert", json={"sha": sha})
    body = r.json()
    assert body["ok"] is True
    assert "飞书侧" in body["message"]  # UI 文案明示外部副作用不可撤销
    assert target.read_text(encoding="utf-8") == "v1"


def test_u4_revert_refused_when_dirty(tmp_path: Path) -> None:
    vault = _git_vault(tmp_path)
    target = vault / "inbox.md"
    target.write_text("wb 写入", encoding="utf-8")
    commit_paths(vault, [target], "wb: capture")
    client = _client(vault)
    sha = client.get("/api/undo/history").json()["commits"][0]["sha"]
    target.write_text("wb 写入 + 手改", encoding="utf-8")
    r = client.post("/api/undo/revert", json={"sha": sha})
    assert r.json()["ok"] is False
    assert "未提交改动" in r.json()["message"]


def test_u4_revert_not_git_graceful(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    r = _client(vault).post("/api/undo/revert", json={"sha": "a" * 40})
    body = r.json()
    assert body["ok"] is False
    assert "不是 git 仓库" in body["message"]
