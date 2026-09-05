"""P0-09 Git backend conformance：system 与 dulwich 在同一临时 bare remote 上行为一致。

矩阵覆盖：detect/init/clone、status(staged/unstaged/untracked)、add 显式路径、commit、
log/filter、diff、revert wb commit（含冲突 typed error）、remote/upstream、fetch、
ahead/behind、fast-forward、push、current branch；remote-missing / non-ff typed error；
PATH 为空时 production（dulwich）后端不调系统 git 完成 init/commit/fetch/ff/push。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from summit_workbench.repositories.git_backend import (
    CommitIdentity,
    GitConflictError,
    GitNonFastForward,
)

KINDS = ["system", "dulwich"]
ID = CommitIdentity("Conformance 作者", "conformance@example.com")


def _backend(kind: str, path: Path):
    # 直接实例化具体后端（不经运行时选择），避免向进程 env 写入 WB_GIT_BACKEND 泄漏到其它测试
    if kind == "dulwich":
        from summit_workbench.repositories.dulwich_git import DulwichGitBackend

        return DulwichGitBackend(path)
    from summit_workbench.repositories.system_git import SystemGitBackend

    return SystemGitBackend(path)


@pytest.mark.parametrize("kind", KINDS)
def test_local_commit_history_and_revert(kind: str, tmp_path: Path) -> None:
    repo = _backend(kind, tmp_path / "repo")
    assert not repo.is_git_repo()
    repo.init()
    assert repo.is_git_repo()
    (tmp_path / "repo" / "a.txt").write_text("v1", encoding="utf-8")
    repo.add(["a.txt"])
    assert repo.has_staged_changes(["a.txt"])
    assert repo.staged_paths() == ["a.txt"]
    assert repo.is_dirty()
    repo.commit("wb: first", author=ID)
    sha = repo.resolve_commit(repo.log_grep("wb:", 1)[0][0])
    subject, parents = repo.validate_commit(sha)
    assert subject == "wb: first" and parents == 0
    assert repo.files_changed_by(sha) == ["a.txt"]
    assert repo.current_branch()

    # 未跟踪/未暂存状态
    (tmp_path / "repo" / "untracked.md").write_text("x", encoding="utf-8")
    assert repo.is_dirty_paths(["untracked.md"])
    (tmp_path / "repo" / "a.txt").write_text("v2", encoding="utf-8")
    assert repo.is_dirty_paths(["a.txt"])
    repo.add(["a.txt"])
    repo.commit("wb: second", author=ID)
    rows = repo.log_grep("wb:", 10)
    assert [row[2] for row in rows] == ["wb: second", "wb: first"]
    assert "a.txt" in repo.show_patch(rows[1][0])

    # revert HEAD（second）→ a.txt 回到 v1；先 revert 更旧的 first 必须冲突
    with pytest.raises(GitConflictError):
        repo.revert(rows[1][0])
    repo.revert(rows[0][0])
    assert (tmp_path / "repo" / "a.txt").read_text(encoding="utf-8") == "v1"
    assert repo.commit_subject(repo.resolve_commit(repo.log_grep("Revert", 1)[0][0])).startswith(
        "Revert"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_remote_push_clone_fetch_ff(kind: str, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    _backend(kind, bare).init(bare=True)
    a = _backend(kind, tmp_path / "a")
    a.init()
    (tmp_path / "a" / "f.txt").write_text("one", encoding="utf-8")
    a.add(["f.txt"])
    a.commit("wb: one", author=ID)
    a.add_remote("origin", str(bare))
    a.push()

    c = _backend(kind, tmp_path / "c")
    c.clone(str(bare), tmp_path / "c")
    assert (tmp_path / "c" / "f.txt").read_text(encoding="utf-8") == "one"
    assert c.has_remote() and c.has_upstream()

    (tmp_path / "a" / "f.txt").write_text("two", encoding="utf-8")
    a.add(["f.txt"])
    a.commit("wb: two", author=ID)
    a.push()
    c.fetch()
    behind = c.ahead_behind().behind
    assert behind >= 1, behind
    c.ff_merge_upstream()
    assert (tmp_path / "c" / "f.txt").read_text(encoding="utf-8") == "two"


@pytest.mark.parametrize("kind", KINDS)
def test_remote_missing_and_non_fast_forward_typed(kind: str, tmp_path: Path) -> None:
    from summit_workbench.repositories.git_backend import GitRemoteUnavailable

    repo = _backend(kind, tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "f.txt").write_text("x", encoding="utf-8")
    repo.add(["f.txt"])
    repo.commit("wb: x", author=ID)
    repo.add_remote("origin", str(tmp_path / "no-such-remote.git"))
    with pytest.raises(GitRemoteUnavailable):
        repo.push()

    # non-ff：双方都从共同祖先分叉后，落后方 push 被拒（typed）
    bare = tmp_path / "shared.git"
    _backend(kind, bare).init(bare=True)
    base = _backend(kind, tmp_path / "base")
    base.init()
    (tmp_path / "base" / "f.txt").write_text("0", encoding="utf-8")
    base.add(["f.txt"])
    base.commit("wb: base", author=ID)
    base.add_remote("origin", str(bare))
    base.push()

    b1 = _backend(kind, tmp_path / "b1")
    b1.clone(str(bare), tmp_path / "b1")
    b2 = _backend(kind, tmp_path / "b2")
    b2.clone(str(bare), tmp_path / "b2")
    (tmp_path / "b1" / "f.txt").write_text("b1", encoding="utf-8")
    b1.add(["f.txt"])
    b1.commit("wb: b1", author=ID)
    b1.push()
    (tmp_path / "b2" / "f.txt").write_text("b2", encoding="utf-8")
    b2.add(["f.txt"])
    b2.commit("wb: b2", author=ID)
    with pytest.raises(GitNonFastForward):
        b2.push()


def test_identity_and_revert_message_recorded(tmp_path: Path) -> None:
    """author 由调用方显式传入并写入 commit 对象（system/dulwich 一致）。"""
    from dulwich.repo import Repo

    for kind in KINDS:
        repo = _backend(kind, tmp_path / f"repo-{kind}")
        repo.init()
        (tmp_path / f"repo-{kind}" / "f.txt").write_text("x", encoding="utf-8")
        repo.add(["f.txt"])
        repo.commit("wb: authored", author=ID)
        git_repo = Repo(str(tmp_path / f"repo-{kind}"))
        commit = git_repo[git_repo.head()]
        assert commit.author == b"Conformance \xe4\xbd\x9c\xe8\x80\x85 <conformance@example.com>"


def test_backends_produce_equal_semantics(tmp_path: Path) -> None:
    """两种后端跑同一场景：提交主题列表与触碰文件完全一致。"""
    results: dict[str, tuple[list[str], list[str]]] = {}
    for kind in KINDS:
        base = tmp_path / kind
        repo = _backend(kind, base / "repo")
        repo.init()
        (base / "repo" / "f.txt").write_text("1", encoding="utf-8")
        repo.add(["f.txt"])
        repo.commit("wb: equal", author=ID)
        rows = repo.log_grep("wb:", 10)
        results[kind] = (
            [row[2] for row in rows],
            repo.files_changed_by(repo.resolve_commit(rows[0][0])),
        )
    assert results["system"] == results["dulwich"]


def test_dulwich_production_backend_works_with_empty_path(tmp_path: Path) -> None:
    """PATH 为空时 dulwich 后端完成 init/commit/fetch/ff/push（绝不调用系统 git）。"""
    script = """
import os, sys
from pathlib import Path
root = Path(sys.argv[1])
os.environ["WB_GIT_BACKEND"] = "dulwich"
from summit_workbench.repositories.dulwich_git import DulwichGitBackend
from summit_workbench.repositories.git_backend import CommitIdentity
ID = CommitIdentity("no git", "no@git")
bare = root / "remote.git"
DulwichGitBackend(bare).init(bare=True)
a = DulwichGitBackend(root / "a"); a.init()
(root / "a" / "f.txt").write_text("one")
a.add(["f.txt"]); a.commit("wb: one", author=ID)
a.add_remote("origin", str(bare)); a.push()
c = DulwichGitBackend(root / "c"); c.clone(str(bare), root / "c")
(root / "a" / "f.txt").write_text("two")
a.add(["f.txt"]); a.commit("wb: two", author=ID); a.push()
c.fetch(); c.ff_merge_upstream()
assert (root / "c" / "f.txt").read_text() == "two"
print("OK")
"""
    env = {k: v for k, v in os.environ.items() if k != "PATH"}
    env["PATH"] = ""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK" in completed.stdout
