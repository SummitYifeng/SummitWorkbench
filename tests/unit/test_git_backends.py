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
import time
from pathlib import Path

import pytest
from dulwich.graph import can_fast_forward
from dulwich.objects import Commit, ObjectID
from dulwich.refs import Ref
from dulwich.repo import Repo

from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    GitConflictError,
    GitCredentialsUnavailable,
    GitNonFastForward,
    GitRemoteSchemeUnsupported,
    is_missing_local_remote,
    require_https_remote,
)

KINDS = ["system", "dulwich"]
ID = CommitIdentity("Conformance 作者", "conformance@example.com")


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:yifeng93/WorkKnowledge.git",
        "ssh://git@github.com/yifeng93/WorkKnowledge.git",
        "https://github.com/yifeng93/WorkKnowledge.git",
    ],
)
def test_production_remote_contract_accepts_https_and_ssh(url: str) -> None:
    require_https_remote(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/yifeng93/WorkKnowledge.git",
        "file:///tmp/work-knowledge",
        "ssh://git@/yifeng93/WorkKnowledge.git",
        "https://alice:" + "secret" + "@example.com/repo.git",
        "not a url",
    ],
)
def test_production_remote_contract_rejects_unsupported_or_invalid_urls(url: str) -> None:
    with pytest.raises(GitRemoteSchemeUnsupported) as exc_info:
        require_https_remote(url)
    assert url not in str(exc_info.value)


def test_production_remote_contract_does_not_echo_url_credentials() -> None:
    with pytest.raises(GitRemoteSchemeUnsupported) as exc_info:
        require_https_remote("http://alice:" + "secret" + "@example.com/repo.git")
    assert "secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # SCP-like SSH 不含 "://"，但它是远端而不是本地路径（2026-09-18 真机回归：
        # 旧判据把它当不存在的本地目录，SSH remote 的 push 在联网前就报 remote-unavailable）。
        ("git@github.com:yifeng93/WorkKnowledge.git", False),
        ("ssh://git@github.com/yifeng93/WorkKnowledge.git", False),
        ("https://github.com/yifeng93/WorkKnowledge.git", False),
        ("/tmp/summit-workbench-does-not-exist-9f3a", True),
        ("../relative-remote-does-not-exist-9f3a", True),
        (None, False),
        ("", False),
    ],
)
def test_missing_local_remote_only_matches_bare_nonexistent_paths(
    url: str | None, expected: bool
) -> None:
    assert is_missing_local_remote(url) is expected


def test_missing_local_remote_accepts_existing_directory(tmp_path) -> None:
    assert is_missing_local_remote(str(tmp_path)) is False


@pytest.mark.parametrize("kind", KINDS)
def test_https_remote_without_username_is_a_credentials_error(kind: str, tmp_path: Path) -> None:
    repo = _backend(kind, tmp_path / "repo")
    repo.init()
    repo.add_remote("origin", "https://github.com/example/private.git")
    with pytest.raises(GitCredentialsUnavailable):
        repo.fetch()


def test_dulwich_fetch_preserves_sanitized_transport_diagnostic(
    tmp_path: Path, monkeypatch
) -> None:
    """fetch 必须把（脱敏后的）传输层诊断附进 typed error。

    2026-09-19 改接缝：dulwich 1.2 的 ``porcelain.fetch`` 不再接受传输参数，fetch 改为自己
    经 ``get_transport_and_path`` 建 client（见 ``tests/contract/test_dulwich_api_contract.py``）。
    因此这里 monkeypatch 的对象从 ``porcelain.fetch`` 换成「传输入口 + client」，
    **断言的性质不变**：诊断文本保留、凭据字符串脱敏。
    """
    from summit_workbench.repositories import dulwich_git
    from summit_workbench.repositories.git_backend import GitAuthError

    repo = _backend("dulwich", tmp_path / "repo")
    repo.init()
    repo.add_remote("origin", "https://github.com/example/private.git")
    backend = dulwich_git.DulwichGitBackend(tmp_path / "repo", username="alice")
    monkeypatch.setattr(backend, "transport_kwargs", lambda *_args, **_kwargs: {})

    class _FailingClient:
        def fetch(self, _path, _target, progress=None):
            assert progress is not None, "transport 诊断必须接到 sink 上"
            progress(
                b"fatal: Authentication failed for https://alice:"
                + b"secret-token"
                + b"@example.git\n"
            )
            raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(
        dulwich_git,
        "get_transport_and_path",
        lambda *_args, **_kwargs: (_FailingClient(), "/example/private.git"),
    )
    with pytest.raises(GitAuthError) as caught:
        backend.fetch()
    assert "Authentication failed" in caught.value.stderr
    assert "secret-token" not in caught.value.stderr


def test_dulwich_clone_preserves_sanitized_transport_diagnostic(
    tmp_path: Path, monkeypatch
) -> None:
    """clone 与 fetch/push 一样，必须把（脱敏后的）传输层诊断附进 typed error。

    2026-09-19 补：此前只有 fetch/push 传了 ``stderr=``，clone 漏了 —— 于是 onboarding
    连接私有远端失败时又退回笼统文案，使用者无法区分凭据 / TLS / 代理 / 网络。
    """
    from dulwich import porcelain

    from summit_workbench.repositories import dulwich_git
    from summit_workbench.repositories.git_backend import GitAuthError

    backend = dulwich_git.DulwichGitBackend(tmp_path / "repo", username="alice")
    monkeypatch.setattr(backend, "transport_kwargs", lambda *_args, **_kwargs: {})

    def fake_clone(*_args, errstream, **_kwargs):
        errstream.write(
            b"fatal: Authentication failed for https://alice:" + b"secret-token" + b"@example.git\n"
        )
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(porcelain, "clone", fake_clone)
    with pytest.raises(GitAuthError) as caught:
        backend.clone("https://github.com/example/private.git", tmp_path / "cloned")
    assert "Authentication failed" in caught.value.stderr
    assert "secret-token" not in caught.value.stderr


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


def test_dulwich_scp_remote_push_roundtrip_reaches_transport(tmp_path: Path, monkeypatch) -> None:
    """SCP 形状 SSH 地址必须能走到 push 传输层（2026-09-18 真机回归的机器守卫）。

    旧守卫把 ``git@host:path`` 当成不存在的本地目录，push 在联网之前就抛
    ``remote-unavailable``；本次只把「URL → 传输」的解析换成落地到本地 bare remote，
    其余（守卫、refspec 选择、远端 ref 更新）都走真实实现。真实 SSH 回环需要本机
    sshd 的公钥登录，环境相关性太强，故不放进单测。
    """
    from dulwich import porcelain
    from dulwich.client import LocalGitClient
    from dulwich.repo import Repo

    bare = tmp_path / "remote.git"
    _backend("dulwich", bare).init(bare=True)
    repo = _backend("dulwich", tmp_path / "a")
    repo.init()
    (tmp_path / "a" / "f.txt").write_text("one", encoding="utf-8")
    repo.add(["f.txt"])
    repo.commit("wb: one", author=ID)
    repo.add_remote("origin", "git@localhost:remote.git")

    calls: list[str] = []

    def route_to_local_bare(location, config=None, operation=None, **kwargs):
        calls.append(location)
        return LocalGitClient(), str(bare)

    monkeypatch.setattr(porcelain, "get_transport_and_path", route_to_local_bare)

    repo.push()  # 旧代码在这里抛 GitRemoteUnavailable

    assert calls == ["git@localhost:remote.git"]
    # 真推到了：bare remote 的 HEAD 分支已与本地 HEAD 一致（旧代码根本到不了这里）
    assert Repo(str(bare)).refs[Ref(b"refs/heads/main")] == ObjectID(
        repo.head_revision().encode("ascii")
    )


def test_dulwich_merge_base_reads_diverged_refs(tmp_path: Path) -> None:
    """Production conflict details can resolve a common ancestor with Dulwich."""
    from dulwich.repo import Repo

    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    repo = DulwichGitBackend(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "base.txt").write_text("base", encoding="utf-8")
    repo.add(["base.txt"])
    repo.commit("wb: base", author=ID)
    base = repo.head_revision()

    (tmp_path / "repo" / "local.txt").write_text("local", encoding="utf-8")
    repo.add(["local.txt"])
    repo.commit("wb: local", author=ID)
    local = repo.head_revision()

    raw_repo = Repo(str(tmp_path / "repo"))
    raw_repo.refs[Ref(b"refs/heads/other")] = ObjectID(base.encode("ascii"))
    raw_repo.refs.set_symbolic_ref(Ref(b"HEAD"), Ref(b"refs/heads/other"))
    (tmp_path / "repo" / "remote.txt").write_text("remote", encoding="utf-8")
    repo.add(["remote.txt"])
    repo.commit("wb: remote", author=ID)
    remote = repo.head_revision()

    assert repo.merge_base(local, remote) == base


@pytest.mark.parametrize("kind", KINDS)
def test_normal_merge_commit_preserves_both_parents_and_pushes_fast_forward(
    kind: str, tmp_path: Path
) -> None:
    bare = tmp_path / "remote.git"
    _backend(kind, bare).init(bare=True)
    seed = _backend(kind, tmp_path / "seed")
    seed.init()
    (tmp_path / "seed" / "base.txt").write_text("base", encoding="utf-8")
    seed.add(["base.txt"])
    seed.commit("wb: base", author=ID)
    seed.add_remote("origin", str(bare))
    seed.push()

    local = _backend(kind, tmp_path / "local")
    local.clone(str(bare), tmp_path / "local")
    remote_writer = _backend(kind, tmp_path / "remote-writer")
    remote_writer.clone(str(bare), tmp_path / "remote-writer")
    (tmp_path / "remote-writer" / "remote.txt").write_text("remote", encoding="utf-8")
    remote_writer.add(["remote.txt"])
    remote_writer.commit("wb: remote", author=ID)
    remote_writer.push()

    (tmp_path / "local" / "local.txt").write_text("local", encoding="utf-8")
    local.add(["local.txt"])
    local.commit("wb: local", author=ID)
    local.fetch()
    remote_revision = local.upstream_revision()
    local.commit_merge("wb: recovery merge", remote_revision, author=ID)

    merge_revision = local.head_revision()
    assert local.commit_parent_count(merge_revision) == 2
    local.push()
    assert local.ahead_behind().ahead == 0
    assert local.ahead_behind().behind == 0


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


def _skewed_commit(path: Path, message: str, *, when: int) -> str:
    """造一个 committer/author 时间显式给定的提交（模拟两台机器的时钟偏差）。

    ``backend.commit`` 用当前时间；D9 的坏区只有在**远端父提交比本地提交新**时出现，
    所以这里绕过后端直接写 commit 对象（仍走 ``ref=b"HEAD"``，语义与正常提交一致）。
    """
    sha = (
        Repo(str(path))
        .get_worktree()
        .commit(
            message=message.encode("utf-8"),
            author=b"Skew Author <skew@example.com>",
            committer=b"Skew Author <skew@example.com>",
            commit_timestamp=when,
        )
    )
    return sha.decode("ascii")


def test_push_succeeds_when_remote_parent_committer_time_is_newer(tmp_path: Path) -> None:
    """D9：远端父提交的 committer time 比本地提交新（跨机时钟偏差）时仍须推送成功。

    dulwich 的 ``can_fast_forward`` 用时间戳剪枝，两跳（恢复提交 + 审计提交）会落在
    坏区：图上是真快进，它却报分叉。修复后用图可达性复核 + 单 refspec 显式强推。
    变异验证：去掉 ``_push_confirmed_fast_forward``（或让 ``_is_ancestor`` 恒为 False）
    本用例在 ``local.push()`` 处抛 ``GitNonFastForward``。
    """
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    bare = tmp_path / "remote.git"
    DulwichGitBackend(bare).init(bare=True)
    seed = DulwichGitBackend(tmp_path / "seed")
    seed.init()
    (tmp_path / "seed" / "base.txt").write_text("base", encoding="utf-8")
    seed.add(["base.txt"])
    seed.commit("wb: base", author=ID)
    seed.add_remote("origin", str(bare))
    seed.push()
    base = seed.head_revision()

    local = DulwichGitBackend(tmp_path / "local")
    local.clone(str(bare), tmp_path / "local")
    assert local.has_upstream() and local.upstream_revision() == base

    now = int(time.time())
    for name, delta in (("recovery", 7200), ("audit", 3600)):
        (tmp_path / "local" / f"{name}.txt").write_text(name, encoding="utf-8")
        local.add([f"{name}.txt"])
        _skewed_commit(tmp_path / "local", f"wb: {name}", when=now - delta)
    head = local.head_revision()

    # 前置断言：确认确实落在 D9 的坏区（dulwich 认为不可快进，而图上是真快进）。
    # 保留这条是为了防止哪天 dulwich 修好了、本用例悄悄失去覆盖；届时请连同图复核一起复核。
    assert (
        can_fast_forward(
            Repo(str(tmp_path / "local")),
            ObjectID(base.encode("ascii")),
            ObjectID(head.encode("ascii")),
        )
        is False
    )

    local.push()

    assert DulwichGitBackend(bare).head_revision() == head
    assert local.ahead_behind() == AheadBehind(ahead=0, behind=0)


def test_push_rejects_true_divergence_even_when_graph_check_runs(tmp_path: Path) -> None:
    """D9 的另一半：真分叉必须仍然是 typed ``GitNonFastForward``，远端一个字节都不动。

    变异验证：把 ``_is_ancestor`` 改成恒 True（即"无条件 force"），远端 ref 会被本地
    head 覆盖，下面的 ``head_revision() == remote_head`` 断言立刻失败。
    """
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    bare = tmp_path / "remote.git"
    DulwichGitBackend(bare).init(bare=True)
    seed = DulwichGitBackend(tmp_path / "seed")
    seed.init()
    (tmp_path / "seed" / "f.txt").write_text("0", encoding="utf-8")
    seed.add(["f.txt"])
    seed.commit("wb: base", author=ID)
    seed.add_remote("origin", str(bare))
    seed.push()

    local = DulwichGitBackend(tmp_path / "local")
    local.clone(str(bare), tmp_path / "local")
    writer = DulwichGitBackend(tmp_path / "writer")
    writer.clone(str(bare), tmp_path / "writer")
    (tmp_path / "writer" / "f.txt").write_text("writer", encoding="utf-8")
    writer.add(["f.txt"])
    writer.commit("wb: writer", author=ID)
    writer.push()
    remote_head = writer.head_revision()

    (tmp_path / "local" / "f.txt").write_text("local", encoding="utf-8")
    local.add(["f.txt"])
    local.commit("wb: local", author=ID)

    with pytest.raises(GitNonFastForward):
        local.push()

    assert DulwichGitBackend(bare).head_revision() == remote_head


@pytest.mark.parametrize("kind", KINDS)
def test_backend_remote_bind_and_unbind_roundtrip(kind: str, tmp_path: Path) -> None:
    """G2 依赖的 remote 原语在两个后端上语义一致：add_remote / set_upstream / remove_remote。

    ``set_upstream`` 等价 ``git push -u``：写 branch.<name>.remote/merge，使 @{u} 与
    ahead/behind 可用；``remove_remote`` 幂等（本来没有就是 no-op）。
    """
    bare = tmp_path / "remote.git"
    _backend(kind, bare).init(bare=True)
    repo = _backend(kind, tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "f.txt").write_text("x", encoding="utf-8")
    repo.add(["f.txt"])
    repo.commit("wb: x", author=ID)
    head = repo.head_revision()

    repo.add_remote("origin", str(bare))
    assert repo.has_remote("origin")
    assert repo.remote_url("origin") == str(bare)
    assert not repo.has_upstream()

    repo.push()
    repo.fetch()
    repo.set_upstream("origin")
    assert repo.has_upstream()
    assert repo.upstream_revision() == head

    repo.remove_remote("origin")
    assert not repo.has_remote("origin")
    assert repo.remote_url("origin") is None
    repo.remove_remote("origin")  # 幂等
    assert not repo.has_remote("origin")


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
        assert isinstance(commit, Commit)
        assert commit.author == b"Conformance \xe4\xbd\x9c\xe8\x80\x85 <conformance@example.com>"


def test_dulwich_clean_status_honors_blob_ids_and_ignored_files(tmp_path: Path) -> None:
    """A clean production worktree must ignore valid files such as Finder metadata."""
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    repo = DulwichGitBackend(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    (tmp_path / "repo" / "tracked.md").write_text("stable\n", encoding="utf-8")
    repo.add([".gitignore", "tracked.md"])
    repo.commit("wb: clean baseline", author=ID)

    assert not repo.is_dirty()
    (tmp_path / "repo" / ".DS_Store").write_text("finder\n", encoding="utf-8")
    (tmp_path / "repo" / "nested").mkdir()
    (tmp_path / "repo" / "nested" / ".DS_Store").write_text("finder\n", encoding="utf-8")
    assert not repo.is_dirty()

    (tmp_path / "repo" / "ignored-directory").mkdir()
    (tmp_path / "repo" / "ignored-directory" / "cache.bin").write_bytes(b"cache")
    (tmp_path / "repo" / ".gitignore").write_text(
        ".DS_Store\nignored-directory/\n", encoding="utf-8"
    )
    repo.add([".gitignore"])
    repo.commit("wb: ignore generated directory", author=ID)
    assert not repo.is_dirty()

    (tmp_path / "repo" / "real-untracked.txt").write_text("must be reported\n", encoding="utf-8")
    assert repo.is_dirty()
    (tmp_path / "repo" / "real-untracked.txt").unlink()

    (tmp_path / "repo" / "tracked.md").write_text("changed\n", encoding="utf-8")
    assert repo.is_dirty()
    repo.add(["tracked.md"])
    repo.commit("wb: restore tracked file", author=ID)
    (tmp_path / "repo" / "tracked.md").unlink()
    assert repo.is_dirty()


@pytest.mark.parametrize("kind", KINDS)
def test_add_skips_ignored_paths_for_both_backends(kind: str, tmp_path: Path) -> None:
    """显式 add 也必须遵守 vault 的 ignore 规则，不能把机器状态重新入库。"""
    from dulwich.repo import Repo

    repo = _backend(kind, tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / ".gitignore").write_text("_signals/\n", encoding="utf-8")
    repo.add([".gitignore"])
    repo.commit("wb: ignore signals", author=ID)

    signal = tmp_path / "repo" / "_signals" / "meeting-state" / "log.jsonl"
    signal.parent.mkdir(parents=True)
    signal.write_text("machine state\n", encoding="utf-8")

    repo.add(["_signals/meeting-state/log.jsonl"])

    assert not repo.has_staged_changes()
    assert "_signals/meeting-state/log.jsonl" not in repo.staged_paths()
    assert b"_signals/meeting-state/log.jsonl" not in Repo(str(tmp_path / "repo")).open_index()


@pytest.mark.parametrize("kind", KINDS)
def test_add_honors_deep_gitignore_negation(kind: str, tmp_path: Path) -> None:
    """A deeper negation rule must re-include only its matching path."""
    repo = _backend(kind, tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / ".gitignore").write_text("*.cache\n!nested/keep.cache\n", encoding="utf-8")
    nested = tmp_path / "repo" / "nested"
    nested.mkdir()
    (nested / "keep.cache").write_text("keep\n", encoding="utf-8")
    (nested / "drop.cache").write_text("drop\n", encoding="utf-8")

    repo.add([".gitignore", "nested/keep.cache", "nested/drop.cache"])

    assert repo.staged_paths() == [".gitignore", "nested/keep.cache"]


def test_dulwich_clean_status_ignores_workspace_lock_file(tmp_path: Path) -> None:
    """工作台内部锁不是用户改动，不应把共享 vault 误判为 dirty-protected。"""
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    repo = DulwichGitBackend(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "tracked.md").write_text("stable\n", encoding="utf-8")
    repo.add(["tracked.md"])
    repo.commit("wb: clean baseline", author=ID)

    (tmp_path / "repo" / ".wb.lock").touch()

    assert not repo.is_dirty()


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


_LOGGREP_MESSAGES = (
    "chore: seed",
    "wb: journal/log [op-1]",
    "chore: outer subject\n\nwb: inner body line",
    "subject line one\nsubject line two\n\nbody para",
    "first\n  indented second\n\nbody",
    "wb: journal/log [op-2]",
)

# 生产常量 `autocommit._WB_PREFIX_GREP` 就是 `^wb:`（`^` 必须按行锚定，否则打包 App 的空面板）。
_LOGGREP_PATTERNS = ("^wb:", "wb:", "^chore", "^subject line", "Revert", "body line", "^first")


def test_log_grep_semantics_agree_across_backends(tmp_path: Path, monkeypatch) -> None:
    """两个后端的 `log_grep` 必须**同语义**：整条消息、正则、`^`/`$` 按行锚定、返回 `%s` 主题。

    2026-09-19 真实缺陷（用户可见）：dulwich 原来是「**字面子串** + 只匹配**主题**」，于是生产
    常量 ``autocommit._WB_PREFIX_GREP = "^wb:"`` 在 dulwich（**打包 App 固定的后端**）上恒不
    命中 ⇒ ``list_wb_commits()`` 恒返回 ``[]`` ⇒「撤销历史」面板空白。

    写库用 system 后端（提交消息经 git 清理，两个后端读到的是同一份消息 ⇒ 差异只可能来自
    **读取**语义）；读库两个后端各来一遍，逐模式比对。每个提交给不同的 author/committer 时间，
    避免同一秒内的提交让遍历顺序出现并列歧义。

    变异验证：把 ``dulwich_git.log_grep`` 改回 ``needle in subject`` ⇒ 本用例立刻红
    （`^wb:` 与 `body line` 在两个后端上结果不同）。
    """
    repo_dir = tmp_path / "repo"
    writer = _backend("system", repo_dir)
    writer.init()
    for index, message in enumerate(_LOGGREP_MESSAGES):
        stamp = f"2026-09-19T10:{index:02d}:00+08:00"
        monkeypatch.setenv("GIT_AUTHOR_DATE", stamp)
        monkeypatch.setenv("GIT_COMMITTER_DATE", stamp)
        (repo_dir / f"f{index}.txt").write_text(str(index), encoding="utf-8")
        writer.add([f"f{index}.txt"])
        writer.commit(message, author=ID)

    by_kind = {
        kind: {
            pattern: [row[2] for row in _backend(kind, repo_dir).log_grep(pattern, 50)]
            for pattern in _LOGGREP_PATTERNS
        }
        for kind in KINDS
    }

    assert by_kind["dulwich"] == by_kind["system"]
    # 非空护栏：两个后端"一致地坏掉"（例如都返回空）不算通过。
    assert by_kind["system"]["^wb:"] == [
        "wb: journal/log [op-2]",
        "chore: outer subject",  # 正文里以 `wb:` 开头的那一行：`^` 按行锚定才命中
        "wb: journal/log [op-1]",
    ]
    # `%s` 折叠规则：多行首段折成一个空格；续行缩进保留。
    assert by_kind["system"]["^subject line"] == ["subject line one subject line two"]
    assert by_kind["system"]["^first"] == ["first   indented second"]
    assert by_kind["system"]["Revert"] == []


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


def test_dulwich_https_transport_uses_ca_bundle(monkeypatch, tmp_path) -> None:
    """P1-07D：HTTPS transport 显式使用可信 CA bundle，修复 frozen OpenSSL 默认 CA 失效。"""
    from types import SimpleNamespace

    from pydantic import SecretStr

    from summit_workbench.config.tls_trust import ca_bundle_path
    from summit_workbench.repositories import dulwich_git

    bundle = ca_bundle_path()
    assert bundle is not None and bundle.is_file()
    backend = dulwich_git.DulwichGitBackend(
        tmp_path / "repo",
        workspace_id="ws",
        username="alice",
        credential_resolver=lambda ws, host, user: SimpleNamespace(password=SecretStr("s")),
    )
    kwargs = backend.transport_kwargs("https://github.com/acme/private.git", operation="fetch")
    pool_manager = kwargs["pool_manager"]
    assert pool_manager.connection_pool_kw["cert_reqs"] == "CERT_REQUIRED"
    assert os.fsdecode(pool_manager.connection_pool_kw["ca_certs"]) == str(bundle)


def test_dulwich_https_transport_never_disables_tls(monkeypatch, tmp_path) -> None:
    """P1-07D：即便 CA bundle 定位失败，HTTPS transport 也绝不关闭 TLS 校验。"""
    from types import SimpleNamespace

    from pydantic import SecretStr

    from summit_workbench.repositories import dulwich_git

    monkeypatch.setattr(dulwich_git, "ca_bundle_path", lambda: None)
    backend = dulwich_git.DulwichGitBackend(
        tmp_path / "repo",
        workspace_id="ws",
        username="alice",
        credential_resolver=lambda ws, host, user: SimpleNamespace(password=SecretStr("s")),
    )
    kwargs = backend.transport_kwargs("https://github.com/acme/private.git", operation="clone")
    pool_manager = kwargs["pool_manager"]
    assert pool_manager.connection_pool_kw["cert_reqs"] == "CERT_REQUIRED"
    assert pool_manager.connection_pool_kw.get("ca_certs") is None


def test_ca_bundle_path_frozen_fallback(monkeypatch, tmp_path) -> None:
    """P1-07D：frozen 数据目录 <bundle>/certifi/cacert.pem 是可靠的 CA 回退。"""
    import ssl
    import sys
    import types

    from summit_workbench.config import tls_trust

    fake = tmp_path / "certifi" / "cacert.pem"
    fake.parent.mkdir(parents=True)
    fake.write_text("fake-bundle", encoding="utf-8")
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(
        ssl,
        "get_default_verify_paths",
        lambda: types.SimpleNamespace(cafile=None, openssl_cafile=None),
    )
    assert tls_trust.ca_bundle_path() == fake


def test_classify_remote_boundary_tls_auth_unavailable() -> None:
    """证书/TLS 握手/认证/网络各自归类到 typed error。"""
    from summit_workbench.repositories import dulwich_git
    from summit_workbench.repositories.git_backend import (
        GitAuthError,
        GitCertificateError,
        GitRemoteUnavailable,
        GitTlsError,
    )

    cert = RuntimeError("certificate verify failed: unable to get local issuer certificate")
    tls_handshake = RuntimeError("[SSL: TLSV1_ALERT_PROTOCOL_VERSION] tlsv1 alert protocol version")
    auth = RuntimeError("No valid credentials provided (401)")
    network = OSError("Connection refused")

    assert isinstance(dulwich_git._classify_remote(cert, "m"), GitCertificateError)
    assert isinstance(dulwich_git._classify_remote(tls_handshake, "m"), GitTlsError)
    assert isinstance(dulwich_git._classify_remote(auth, "m"), GitAuthError)
    assert isinstance(dulwich_git._classify_remote(network, "m"), GitRemoteUnavailable)


def test_classify_remote_proxy_credentials_runtime() -> None:
    """P1-07D：代理→GitProxyError，凭据缺失→GitCredentialsUnavailable，未知异常→GitBackendRuntimeError。"""
    from summit_workbench.repositories import dulwich_git
    from summit_workbench.repositories.git_backend import (
        GitBackendRuntimeError,
        GitProxyError,
    )

    proxy = RuntimeError("Cannot connect to proxy. Tunnel connection failed: 407")
    unknown = RuntimeError("something totally unexpected happened")
    assert isinstance(dulwich_git._classify_remote(proxy, "m"), GitProxyError)
    assert isinstance(dulwich_git._classify_remote(unknown, "m"), GitBackendRuntimeError)


def test_classify_remote_preserves_already_typed_errors() -> None:
    """已分类的错误不得被文本兜底重包（否则缺凭据会显示 unclassified）。

    2026-09-13 真机复现：恢复机器后、HTTPS 转换之前，`transport_kwargs()` 抛
    `GitCredentialsUnavailable`，被 `_classify_remote` 的兜底重新包成
    `GitBackendRuntimeError` ⇒ 原因码 `unclassified`、界面只说「未分类的同步失败」。
    """
    from summit_workbench.domain.sync import SyncState, classify_repo_error, repo_error_reason
    from summit_workbench.repositories import dulwich_git
    from summit_workbench.repositories.git_backend import (
        GitCredentialsUnavailable,
        GitProxyError,
        GitTlsError,
    )

    for typed in (
        GitCredentialsUnavailable("缺少凭据"),
        GitTlsError("tls"),
        GitProxyError("proxy"),
    ):
        assert dulwich_git._classify_remote(typed, "m") is typed

    missing = dulwich_git._classify_remote(GitCredentialsUnavailable("缺少凭据"), "m")
    assert repo_error_reason(missing) == "credentials-missing"
    assert classify_repo_error(missing) is SyncState.AUTH_REQUIRED


def test_fetch_keeps_typed_credential_error(tmp_path: Path) -> None:
    """fetch 里缺凭据必须落成 credentials-missing，而不是被包装成 unclassified。"""
    from dulwich.repo import Repo

    from summit_workbench.domain.sync import repo_error_reason
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend
    from summit_workbench.repositories.git_backend import GitCredentialsUnavailable

    path = tmp_path / "vault"
    path.mkdir(parents=True, exist_ok=True)
    Repo.init(str(path))
    repo = Repo(str(path))
    config = repo.get_config()
    config.set((b"remote", b"origin"), b"url", b"https://github.com/example/private.git")
    config.write_to_path()

    def resolver(*_args: object) -> None:
        raise GitCredentialsUnavailable("缺少 workspace-scoped Git 凭据配置")

    backend = DulwichGitBackend(
        path, workspace_id="ws", username="Yifeng93", credential_resolver=resolver
    )
    with pytest.raises(GitCredentialsUnavailable) as caught:
        backend.fetch()
    assert repo_error_reason(caught.value) == "credentials-missing"


def test_classify_git_error_stable_codes() -> None:
    """classify_git_error 返回稳定脱敏码（auth/tls/cert/proxy/credential/network/runtime）。"""
    from summit_workbench.repositories.git_backend import (
        GitAuthError,
        GitCertificateError,
        GitCredentialsUnavailable,
        GitProxyError,
        GitRemoteUnavailable,
        GitTlsError,
        classify_git_error,
    )

    assert classify_git_error(GitAuthError("x")) == "git_auth_failed"
    assert classify_git_error(GitTlsError("x")) == "git_tls_failed"
    assert classify_git_error(GitCertificateError("x")) == "git_certificate_failed"
    assert classify_git_error(GitProxyError("x")) == "git_proxy_failed"
    assert classify_git_error(GitCredentialsUnavailable("x")) == "git_credentials_unavailable"
    assert classify_git_error(GitRemoteUnavailable("x")) == "git_remote_unavailable"
    assert classify_git_error(RuntimeError("x")) == "git_backend_runtime_error"


def test_push_updates_remote_tracking_ref_and_clears_ahead_behind(tmp_path: Path) -> None:
    """P1-07D：push 成功后 refs/remotes/origin/<branch> 必须同步到本地 head，
    否则 ahead/behind 与 pending_wb_commits 永不归零（local-ahead 假象）。"""
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend
    from summit_workbench.repositories.git_backend import AheadBehind

    bare = tmp_path / "remote.git"
    DulwichGitBackend(bare).init(bare=True)
    seed = DulwichGitBackend(tmp_path / "seed")
    seed.init()
    (tmp_path / "seed" / "f.txt").write_text("zero", encoding="utf-8")
    seed.add(["f.txt"])
    seed.commit("wb: zero", author=ID)
    seed.add_remote("origin", str(bare))
    seed.push()

    # clone 会配置 branch.<name>.remote/merge 并建立 refs/remotes/origin/*（真实 vault 亦然）
    repo = DulwichGitBackend(tmp_path / "repo")
    repo.clone(str(bare), tmp_path / "repo")
    assert repo.has_upstream()
    assert repo.ahead_behind() == AheadBehind(ahead=0, behind=0)

    (tmp_path / "repo" / "f.txt").write_text("one", encoding="utf-8")
    repo.add(["f.txt"])
    repo.commit("wb: one", author=ID)
    assert repo.ahead_behind() == AheadBehind(ahead=1, behind=0)
    assert repo.pending_wb_commits() == 1

    repo.push()
    assert repo.ahead_behind() == AheadBehind(ahead=0, behind=0)
    assert repo.pending_wb_commits() == 0


def test_fetch_updates_remote_tracking_ref_for_named_remote(tmp_path: Path) -> None:
    """P1-07D：fetch 传 remote 名称后必须更新 refs/remotes/origin/*（HTTPS 路径同此语义）。"""
    from summit_workbench.repositories.dulwich_git import DulwichGitBackend

    bare = tmp_path / "remote.git"
    DulwichGitBackend(bare).init(bare=True)
    writer = DulwichGitBackend(tmp_path / "writer")
    writer.init()
    (tmp_path / "writer" / "f.txt").write_text("one", encoding="utf-8")
    writer.add(["f.txt"])
    writer.commit("wb: one", author=ID)
    writer.add_remote("origin", str(bare))
    writer.push()

    reader = DulwichGitBackend(tmp_path / "reader")
    reader.clone(str(bare), tmp_path / "reader")
    (tmp_path / "writer" / "f.txt").write_text("two", encoding="utf-8")
    writer.add(["f.txt"])
    writer.commit("wb: two", author=ID)
    writer.push()

    reader.fetch()
    counts = reader.ahead_behind()
    assert counts.behind == 1 and counts.ahead == 0
    reader.ff_merge_upstream()
    assert (tmp_path / "reader" / "f.txt").read_text(encoding="utf-8") == "two"


def test_system_http_proxy_parses_macos_output(monkeypatch) -> None:
    """P1-07D：macOS 系统代理经 scutil --proxy 解析（HTTPS 优先），不含凭据。"""
    from summit_workbench.config import network_proxy

    class _Completed:
        returncode = 0
        stdout = (
            "HTTPEnable : 1\nHTTPPort : 7890\nHTTPProxy : 127.0.0.1\n"
            "HTTPSEnable : 1\nHTTPSPort : 7890\nHTTPSProxy : 127.0.0.1\n"
            "SOCKSEnable : 1\nSOCKSPort : 7890\nSOCKSProxy : 127.0.0.1\n"
        )

    class _Subprocess:
        @staticmethod
        def run(*_: object, **__: object) -> _Completed:
            return _Completed()

    monkeypatch.setattr(network_proxy, "subprocess", _Subprocess())
    assert network_proxy.system_http_proxy() == "http://127.0.0.1:7890"
    assert network_proxy.proxy_detected() is True


def test_system_http_proxy_env_takes_precedence(monkeypatch) -> None:
    """env 代理优先于系统代理；命中 env 时绝不调用 scutil。"""
    from summit_workbench.config import network_proxy

    monkeypatch.setenv("https_proxy", "http://env-proxy:9999")

    class _Subprocess:
        @staticmethod
        def run(*_: object, **__: object) -> None:
            raise AssertionError("should not call scutil")

    monkeypatch.setattr(network_proxy, "subprocess", _Subprocess())
    assert network_proxy.system_http_proxy() == "http://env-proxy:9999"


def test_https_pool_manager_honors_system_proxy_when_no_env(monkeypatch) -> None:
    """P1-07D：无 env 代理时，HTTPS pool 显式回退 macOS 系统代理（不关 TLS 校验）。"""
    from summit_workbench.config import network_proxy
    from summit_workbench.repositories import dulwich_git

    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    monkeypatch.setattr(dulwich_git, "ca_bundle_path", lambda: None)
    monkeypatch.setattr(network_proxy, "system_http_proxy", lambda: "http://127.0.0.1:7890")

    manager = dulwich_git._https_pool_manager("https://github.com/acme/private.git")
    assert type(manager).__name__ == "ProxyManager"
    assert manager.connection_pool_kw["cert_reqs"] == "CERT_REQUIRED"
