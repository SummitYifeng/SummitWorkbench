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
