"""简报提交/推送工作流单测：只暂存指定文件、幂等、落后不推（真实临时 git）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from summit_workbench.workflows.brief.publish import PublishStatus, publish_brief


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout


def _init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@e.com")
    _git(path, "config", "user.name", "t")


def _bare_remote_clone(tmp_path: Path) -> tuple[Path, Path]:
    """建裸远端 + 克隆出带 upstream 的工作仓库。"""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-q")
    work = tmp_path / "vault"
    _git(tmp_path, "clone", "-q", str(bare), "vault")
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "t")
    (work / "seed.txt").write_text("seed", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "branch", "--set-upstream-to=origin/main")
    return work, bare


def test_not_git_returns_visible_status(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "daily").mkdir()
    note = vault / "daily" / "d.md"
    note.write_text("x", encoding="utf-8")
    result = publish_brief(vault, [note], message="m", push=False)
    assert result.status is PublishStatus.NOT_GIT


def test_commit_only_stages_listed_files(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    _init(vault)
    (vault / "daily").mkdir()
    note = vault / "daily" / "d.md"
    note.write_text("brief", encoding="utf-8")
    # 用户另有未提交改动，不应被提交
    user_file = vault / "user-notes.md"
    user_file.write_text("私人", encoding="utf-8")

    result = publish_brief(vault, [note], message="chore(brief): d", push=False)
    assert result.status is PublishStatus.COMMITTED
    # user-notes.md 仍是未跟踪状态
    status = _git(vault, "status", "--porcelain")
    assert "user-notes.md" in status
    assert "daily/d.md" not in status  # 已提交


def test_idempotent_nothing_to_commit(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    _init(vault)
    note = vault / "d.md"
    note.write_text("brief", encoding="utf-8")
    first = publish_brief(vault, [note], message="m", push=False)
    assert first.status is PublishStatus.COMMITTED
    second = publish_brief(vault, [note], message="m", push=False)  # 内容未变
    assert second.status is PublishStatus.NOTHING_TO_COMMIT


def test_push_when_upstream(tmp_path: Path) -> None:
    work, bare = _bare_remote_clone(tmp_path)
    note = work / "d.md"
    note.write_text("brief", encoding="utf-8")
    result = publish_brief(work, [note], message="chore(brief): d", push=True)
    assert result.status is PublishStatus.COMMITTED_AND_PUSHED


def test_commit_without_push_flag(tmp_path: Path) -> None:
    work, _ = _bare_remote_clone(tmp_path)
    note = work / "d.md"
    note.write_text("brief", encoding="utf-8")
    result = publish_brief(work, [note], message="m", push=False)
    assert result.status is PublishStatus.COMMITTED
