"""work-sync 集成测试：真实 git、本地裸仓库做远端，无网络。

验证：up-to-date/pull/push/dirty/no-remote/diverged、幂等、非破坏性、逐仓库隔离。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from summit_workbench.workflows.sync import (
    SyncStatus,
    discover_repos,
    sync_repo,
    sync_work_root,
)


def _git(cwd: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return cp.stdout.strip()


def _init_clone(tmp: Path, name: str) -> tuple[Path, Path]:
    """建裸远端 + 有初始提交的工作克隆，返回 (remote, work)。"""
    remote = tmp / f"{name}.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    work = tmp / name
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    _git(work, "config", "user.email", "t@t.test")
    _git(work, "config", "user.name", "Tester")
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "-u", "origin", "HEAD")
    return remote, work


def _second_clone(tmp: Path, remote: Path, name: str) -> Path:
    work = tmp / name
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True)
    _git(work, "config", "user.email", "t2@t.test")
    _git(work, "config", "user.name", "Tester2")
    return work


def _commit(work: Path, filename: str, content: str) -> None:
    (work / filename).write_text(content, encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", f"add {filename}")


def test_up_to_date(tmp_path):
    _, work = _init_clone(tmp_path, "repo")
    result = sync_repo(work)
    assert result.status == SyncStatus.UP_TO_DATE


def test_push_when_ahead(tmp_path):
    remote, work = _init_clone(tmp_path, "repo")
    _commit(work, "a.txt", "x")
    result = sync_repo(work)
    assert result.status == SyncStatus.PUSHED
    # 远端确实收到了新提交（裸仓库 log 可见）
    assert "add a.txt" in _git(remote, "log", "--oneline")


def test_pull_when_behind(tmp_path):
    remote, work = _init_clone(tmp_path, "repo")
    other = _second_clone(tmp_path, remote, "repo-other")
    _commit(other, "b.txt", "y")
    _git(other, "push", "-q", "origin", "HEAD")
    # 现在 work 落后一个提交
    result = sync_repo(work)
    assert result.status == SyncStatus.PULLED
    assert (work / "b.txt").exists()


def test_dirty_does_not_touch_worktree(tmp_path):
    remote, work = _init_clone(tmp_path, "repo")
    other = _second_clone(tmp_path, remote, "repo-other")
    _commit(other, "b.txt", "y")
    _git(other, "push", "-q", "origin", "HEAD")
    # work 落后，且有未提交改动
    (work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    result = sync_repo(work)
    assert result.status == SyncStatus.DIRTY
    # 未提交文件仍在，且没有被合并进 b.txt（工作树未被动过）
    assert (work / "dirty.txt").exists()
    assert not (work / "b.txt").exists()


def test_no_remote(tmp_path):
    work = tmp_path / "solo"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    _git(work, "config", "user.email", "t@t.test")
    _git(work, "config", "user.name", "T")
    (work / "f.txt").write_text("x", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "c")
    result = sync_repo(work)
    assert result.status == SyncStatus.NO_REMOTE


def test_diverged_is_not_force_pushed(tmp_path):
    remote, work = _init_clone(tmp_path, "repo")
    other = _second_clone(tmp_path, remote, "repo-other")
    # 远端前进
    _commit(other, "remote.txt", "r")
    _git(other, "push", "-q", "origin", "HEAD")
    remote_head = _git(remote, "rev-parse", "HEAD")
    # 本地也基于旧点前进（造成分叉）
    _commit(work, "local.txt", "l")
    result = sync_repo(work)
    assert result.status == SyncStatus.DIVERGED
    # 关键：远端未被 force 覆盖，仍指向它自己的提交
    assert _git(remote, "rev-parse", "HEAD") == remote_head


def test_idempotent(tmp_path):
    remote, work = _init_clone(tmp_path, "repo")
    _commit(work, "a.txt", "x")
    first = sync_repo(work)
    assert first.status == SyncStatus.PUSHED
    second = sync_repo(work)
    assert second.status == SyncStatus.UP_TO_DATE


def test_discover_and_isolation(tmp_path):
    root = tmp_path / "Work"
    root.mkdir()
    _init_clone(root, "ok-repo")
    # 一个无远端仓库
    solo = root / "solo"
    solo.mkdir()
    subprocess.run(["git", "init", "-q", str(solo)], check=True)
    # 一个非 git 目录，应被跳过
    (root / "not-a-repo").mkdir()

    found = {p.name for p in discover_repos(root)}
    assert found == {"ok-repo", "solo"}

    results = {r.name: r.status for r in sync_work_root(root)}
    # 一个仓库有问题不影响另一个被处理
    assert results["ok-repo"] == SyncStatus.UP_TO_DATE
    assert results["solo"] == SyncStatus.NO_REMOTE


def test_discover_empty_when_root_missing(tmp_path):
    assert discover_repos(tmp_path / "nope") == []
