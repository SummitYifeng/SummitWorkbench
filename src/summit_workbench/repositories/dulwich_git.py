"""dulwich 生产 git 后端（P0-09）：纯 Python 实现，**绝不调用系统 git**。

覆盖契约：detect/init/clone、status 与 staged/unstaged/untracked、add 显式路径、
commit、log/filter、show diff、revert wb commit、remote/upstream、fetch、
ahead/behind、fast-forward、push、current branch、commit identity、typed errors。

与 :mod:`.system_git` 同跑 conformance suite（对同一临时 bare remote 结果一致）。
HTTPS 远端的凭据接线经 ``WB_GIT_BACKEND=dulwich`` 显式选择后由调用方传入
credentials；真实私有 HTTPS 远端、打包与证书矩阵属真机门（P0-13 前未验证）。
"""

from __future__ import annotations

import datetime
import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dulwich import porcelain
from dulwich.diff_tree import tree_changes
from dulwich.errors import NotGitRepository
from dulwich.ignore import IgnoreFilterManager
from dulwich.index import IndexEntry
from dulwich.objects import Blob, Tree
from dulwich.repo import Repo

from summit_workbench.config.tls_trust import ca_bundle_path as ca_bundle_path
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    GitAuthError,
    GitBackendRuntimeError,
    GitCertificateError,
    GitConflictError,
    GitCredentialsUnavailable,
    GitError,
    GitInvalidRevision,
    GitNonFastForward,
    GitProxyError,
    GitRemoteUnavailable,
    GitTlsError,
    default_identity,
)

Entry = tuple[str, bytes]  # (octal mode, blob sha)


def _identity_bytes(identity: CommitIdentity | None) -> bytes:
    chosen = identity if identity is not None else default_identity()
    return f"{chosen.name} <{chosen.email}>".encode()


def _silenced() -> Any:
    # porcelain 的进度/错误输出可能写 bytes → 用二进制 sink
    return open(os.devnull, "wb")


def _classify_remote(exc: BaseException, message: str) -> GitError:
    """把 dulwich/网络异常映射成 typed error（文本不含 URL 或凭据）。

    顺序重要：证书 → TLS 握手 → 认证 → 代理 → 网络，避免宽泛标记互相吞并。
    未命中任何已知标记的异常归为 :class:`GitBackendRuntimeError`，绝不伪装成
    远端不可达（便于 acceptance preflight 区分「后端 bug」与「网络/凭据/TLS」）。
    """
    text = f"{type(exc).__name__}: {exc}".casefold()
    if any(
        marker in text
        for marker in (
            "proxy",
            "proxyerror",
            "407",
            "tunnel connection failed",
            "cannot connect to proxy",
        )
    ):
        return GitProxyError(message)
    if any(
        marker in text
        for marker in (
            "certificate",
            "sslcert",
            "self-signed",
            "unable to get local issuer",
            "unknown ca",
            "certificate_verify",
        )
    ):
        return GitCertificateError(message)
    if any(marker in text for marker in ("ssl", "tls", "handshake")):
        return GitTlsError(message)
    if any(
        marker in text
        for marker in ("auth", "401", "403", "permission", "unauthorized", "forbidden")
    ):
        return GitAuthError(message)
    if any(
        marker in text
        for marker in (
            "timeout",
            "timed out",
            "connection refused",
            "getaddrinfo",
            "network is unreachable",
            "name or service not known",
            "no route to host",
            "connection reset",
            "broken pipe",
            "unreachable",
            "not found",
            "could not read",
        )
    ):
        return GitRemoteUnavailable(message)
    return GitBackendRuntimeError(message)


def _https_pool_manager(url: str) -> Any:
    """为 HTTPS 远端构造带 CA bundle 的 urllib3 连接池（保留 dulwich 代理支持）。

    frozen 环境下 OpenSSL 默认 CA 路径不可用（P1-07D：``git_tls_failed``），因此
    显式把发现的 CA bundle 通过 ``http.sslCAInfo`` 传入 dulwich 的
    ``default_urllib3_manager``；``sslVerify=true`` 保持 TLS 校验开启。

    另外：打包 App 经 Finder/LaunchServices 启动时没有代理环境变量，而部分网络下
    直接连接 github.com 会被阻断（``git_remote_unavailable``）。这里在无 env 代理时
    显式回退到 macOS 系统代理（``http.proxy``），绝不关闭 TLS 校验。
    """
    from dulwich.client import default_urllib3_manager
    from dulwich.config import ConfigDict

    from summit_workbench.config.network_proxy import system_http_proxy

    config = ConfigDict()
    config.set(b"http", b"sslVerify", b"true")
    bundle = ca_bundle_path()
    if bundle is not None:
        config.set(b"http", b"sslCAInfo", str(bundle).encode("utf-8"))
    if not any(os.environ.get(key) for key in ("https_proxy", "http_proxy", "all_proxy")):
        proxy = system_http_proxy()
        if proxy:
            config.set(b"http", b"proxy", proxy.encode("utf-8"))
    return default_urllib3_manager(config, base_url=url)


class _DirNode:
    """重建树时的目录节点：children 按文件名排序。"""

    def __init__(self) -> None:
        self.files: list[tuple[bytes, str, bytes]] = []  # (name, mode, sha)
        self.dirs: dict[bytes, _DirNode] = {}


class DulwichGitBackend:
    """把 :class:`~summit_workbench.repositories.git_backend.GitBackend` 契约映射到 dulwich。"""

    def __init__(
        self,
        path: Path,
        *,
        workspace_id: str | None = None,
        username: str | None = None,
        credential_resolver: Callable[[str, str, str], Any] | None = None,
    ) -> None:
        self._path = path
        self._workspace_id = workspace_id
        self._username = username
        self._credential_resolver = credential_resolver

    @property
    def path(self) -> Path:
        return self._path

    # ---- 打开仓库 / refs ----

    def _open(self) -> Repo:
        try:
            return Repo(str(self._path))
        except NotGitRepository as exc:
            raise GitError(f"不是 git 仓库：{self._path}") from exc

    @staticmethod
    def _ref(repo: Repo, name: bytes) -> bytes | None:
        try:
            return repo.refs[name]
        except KeyError:
            return None

    def _head_sha(self, repo: Repo) -> bytes | None:
        return self._ref(repo, b"HEAD")

    def _branch_ref(self, repo: Repo) -> bytes:
        ref_name = self._head_ref_name(repo)
        if ref_name is None:
            raise GitError("HEAD 不指向任何分支")
        return ref_name

    def _write_commit(
        self,
        repo: Repo,
        message: str,
        *,
        author: CommitIdentity | None,
        tree: bytes | None = None,
        parent: bytes | None = None,
    ) -> bytes:
        identity = _identity_bytes(author)
        new_sha = repo.do_commit(
            message=message.encode("utf-8"),
            author=identity,
            committer=identity,
            tree=tree,
            ref=b"HEAD",
            merge_heads=[parent] if parent else None,
        )
        return new_sha

    # ---- detect / init / clone ----

    def is_git_repo(self) -> bool:
        return (self._path / ".git").exists()

    def init(self, *, bare: bool = False) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        if bare:
            Repo.init_bare(str(self._path))
        else:
            Repo.init(str(self._path))

    def clone(self, url: str, destination: Path) -> None:
        with _silenced() as sink:
            try:
                clone: Any = porcelain.clone
                clone(
                    url,
                    str(destination),
                    errstream=sink,
                    **dict(self.transport_kwargs(url, operation="clone")),
                )
            except Exception as exc:  # noqa: BLE001 - 需要跨库分类
                raise _classify_remote(exc, "clone 失败") from exc
        # 补齐 branch.<name>.remote/merge（git clone 语义；dulwich porcelain 可能不写）
        repo = self._open()
        ref_name = self._head_ref_name(repo)
        if ref_name is not None and ref_name.startswith(b"refs/heads/"):
            branch = ref_name[len(b"refs/heads/") :]
            config = repo.get_config()
            section = (b"branch", branch)
            config.set(section, b"remote", b"origin")
            config.set(section, b"merge", ref_name)
            config.write_to_path()

    # ---- remote / branch ----

    def _config_get(self, repo: Repo, section: tuple[bytes, bytes], name: bytes) -> bytes | None:
        try:
            return repo.get_config_stack().get(section, name)
        except KeyError:
            return None

    def has_remote(self, name: str = "origin") -> bool:
        repo = self._open()
        return self._config_get(repo, (b"remote", name.encode("utf-8")), b"url") is not None

    def remote_url(self, name: str = "origin") -> str | None:
        repo = self._open()
        url = self._config_get(repo, (b"remote", name.encode("utf-8")), b"url")
        return url.decode("utf-8") if url is not None else None

    def set_remote_url(self, url: str, name: str = "origin") -> None:
        repo = self._open()
        config = repo.get_config()
        section = (b"remote", name.encode("utf-8"))
        if self._config_get(repo, section, b"url") is None:
            raise GitError(f"没有配置 remote {name}")
        config.set(section, b"url", url.encode("utf-8"))
        config.write_to_path()

    def add_remote(self, name: str, url: str) -> None:
        repo = self._open()
        config = repo.get_config()
        section = (b"remote", name.encode("utf-8"))
        config.set(section, b"url", url.encode("utf-8"))
        config.set(
            section,
            b"fetch",
            b"+refs/heads/*:refs/remotes/%s/*" % name.encode("utf-8"),
        )
        config.write_to_path()

    def _head_ref_name(self, repo: Repo) -> bytes | None:
        """HEAD 符号引用最终指向的分支 ref（detached HEAD → None）。"""
        raw = repo.refs.read_ref(b"HEAD")
        if not raw or not raw.startswith(b"ref: "):
            return None  # detached HEAD（raw 为 sha）或未初始化
        return raw[len(b"ref: ") :]

    def current_branch(self) -> str:
        repo = self._open()
        ref_name = self._head_ref_name(repo)
        if ref_name is None:
            raise GitError("HEAD 不指向任何分支")
        return ref_name[len(b"refs/heads/") :].decode("utf-8")

    def head_revision(self) -> str:
        head = self._head_sha(self._open())
        if head is None:
            raise GitError("HEAD 没有指向任何提交")
        return head.decode("ascii")

    def has_upstream(self) -> bool:
        repo = self._open()
        ref_name = self._head_ref_name(repo)
        if ref_name is None or not ref_name.startswith(b"refs/heads/"):
            return False
        branch = ref_name[len(b"refs/heads/") :]
        return (
            self._config_get(repo, (b"branch", branch), b"remote") is not None
            and self._config_get(repo, (b"branch", branch), b"merge") is not None
        )

    def _upstream_sha(self, repo: Repo) -> bytes:
        """@ {u} 语义：branch.<name>.remote + merge 对应的远端追踪 ref。"""
        ref_name = self._head_ref_name(repo)
        if ref_name is None or not ref_name.startswith(b"refs/heads/"):
            raise GitError("当前分支没有 upstream")
        branch = ref_name[len(b"refs/heads/") :]
        remote = self._config_get(repo, (b"branch", branch), b"remote")
        if remote is None:
            raise GitError("当前分支没有 upstream")
        tracking = b"refs/remotes/" + remote + b"/" + branch
        sha = self._ref(repo, tracking)
        if sha is None:
            raise GitError("当前分支没有 upstream（远端追踪 ref 缺失，请先 fetch）")
        return sha

    # ---- 工作树/暂存区 ----

    def _head_tree_id(self, repo: Repo) -> bytes | None:
        head = self._head_sha(repo)
        if head is None:
            return None
        try:
            return repo[head].tree  # type: ignore[attr-defined]
        except (KeyError, TypeError, AttributeError):
            return None

    @staticmethod
    def _flatten(repo: Repo, tree_id: bytes | None) -> dict[str, Entry]:
        if tree_id is None:
            return {}
        flat: dict[str, Entry] = {}

        def walk(prefix: str, tree: Tree) -> None:
            for name, mode, sha in tree.iteritems():
                rel = f"{prefix}{name.decode('utf-8')}"
                if mode & 0o40000:
                    walk(f"{rel}/", repo[sha])  # type: ignore[arg-type]
                else:
                    flat[rel] = (f"{mode:o}", sha)

        walk("", repo[tree_id])  # type: ignore[arg-type]
        return flat

    def _index_entries(self, repo: Repo) -> dict[str, bytes]:
        index = repo.open_index()
        entries: dict[str, bytes] = {}
        for path, entry in index.iteritems():
            sha = getattr(entry, "sha", None)
            if sha is not None:
                entries[path.decode("utf-8")] = sha
        return entries

    def _staged_paths(self, repo: Repo) -> list[str]:
        head = self._flatten(repo, self._head_tree_id(repo))
        index = self._index_entries(repo)
        staged: set[str] = set()
        for path, sha in index.items():
            if head.get(path, ("", b""))[1] != sha:
                staged.add(path)
        staged.update(path for path in head if path not in index)
        return sorted(staged)

    @staticmethod
    def _blob_id(data: bytes) -> str:
        """Return the hexadecimal Git blob id used by the index comparison."""
        return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()  # noqa: S324

    def _worktree_delta(self, repo: Repo) -> tuple[set[str], set[str]]:
        """返回 (已跟踪但有改动, 未跟踪)，路径相对仓库根（posix）。"""
        index = self._index_entries(repo)
        ignore_manager = IgnoreFilterManager.from_repo(repo)
        changed: set[str] = set()
        untracked: set[str] = set()
        for root, dirs, files in os.walk(self._path):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), self._path).replace(os.sep, "/")
                if rel in index:
                    if self._blob_id(Path(root, name).read_bytes()).encode("ascii") != index[rel]:
                        changed.add(rel)
                else:
                    if ignore_manager.is_ignored(rel):
                        continue
                    untracked.add(rel)
        changed.update(tracked for tracked in index if not (self._path / tracked).is_file())
        return changed, untracked

    def is_dirty(self) -> bool:
        repo = self._open()
        changed, untracked = self._worktree_delta(repo)
        return bool(self._staged_paths(repo) or changed or untracked)

    def is_dirty_paths(self, rel_paths: list[str]) -> bool:
        if not rel_paths:
            return False
        repo = self._open()
        wanted = set(rel_paths)
        changed, untracked = self._worktree_delta(repo)
        return bool((set(self._staged_paths(repo)) | changed | untracked) & wanted)

    def staged_paths(self) -> list[str]:
        return self._staged_paths(self._open())

    def has_staged_changes(self, paths: list[str] | None = None) -> bool:
        staged = set(self._staged_paths(self._open()))
        if paths is not None:
            return bool(staged & set(paths))
        return bool(staged)

    def add(self, paths: list[str]) -> None:
        if not paths:
            return
        repo = self._open()
        index = repo.open_index()
        for rel in paths:
            target = self._path / rel
            if not target.is_file():
                raise GitError(f"git add 失败：路径不存在 {rel}")
            data = target.read_bytes()
            blob = Blob.from_string(data)
            repo.object_store.add_object(blob)
            stat = target.stat()
            index[rel.encode("utf-8")] = IndexEntry(
                ctime=(int(stat.st_ctime), stat.st_ctime_ns % 1_000_000_000),
                mtime=(int(stat.st_mtime), stat.st_mtime_ns % 1_000_000_000),
                dev=stat.st_dev,
                ino=stat.st_ino,
                mode=0o100644,
                uid=stat.st_uid,
                gid=stat.st_gid,
                size=stat.st_size,
                sha=blob.id,
            )
        index.write()

    def commit(self, message: str, *, author: CommitIdentity | None = None) -> None:
        repo = self._open()
        try:
            self._write_commit(repo, message, author=author)
        except KeyError as exc:
            raise GitError("git commit 失败：HEAD 无法解析") from exc

    # ---- fetch / ahead-behind / ff / push ----

    def _remote_url(self, repo: Repo, remote: str) -> str:
        url = repo.get_config_stack().get((b"remote", remote.encode("utf-8")), b"url")
        if url is None:
            raise GitError(f"没有配置 remote {remote}")
        return url.decode("utf-8")

    def transport_kwargs(self, url: str, *, operation: str) -> dict[str, Any]:
        """为 Dulwich HTTP transport 解析凭据与带 CA bundle 的连接池。

        该方法只返回给当前请求的短生命周期参数；调用方不得把返回值写入配置、
        remote URL 或日志。测试可注入 resolver，production 默认使用 P0-07 的
        workspace Keychain resolver。HTTPS 额外携带一个 TLS 校验开启、且指向
        可信 CA bundle 的 ``pool_manager``（P1-07D：frozen OpenSSL 默认 CA 失效）。
        """
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            return {}
        if parsed.username is not None or parsed.password is not None:
            raise GitAuthError("HTTPS remote 不允许把凭据写入 URL")
        if not self._workspace_id or not self._username:
            raise GitCredentialsUnavailable("HTTPS remote 缺少 workspace-scoped Git 凭据配置")
        resolver = self._credential_resolver
        if resolver is None:
            from summit_workbench.config.git_credentials import resolve_git_credentials

            resolver = resolve_git_credentials
        try:
            credentials = resolver(self._workspace_id, parsed.hostname or "", self._username)
        except GitError:
            raise
        except Exception as exc:  # noqa: BLE001 - Keychain errors must be sanitized
            raise GitCredentialsUnavailable("Git workspace 凭据读取失败") from exc
        password = credentials.password.get_secret_value()
        kwargs: dict[str, Any] = {"username": self._username, "password": password}
        manager = _https_pool_manager(url)
        if manager is not None:
            kwargs["pool_manager"] = manager
        return kwargs

    def fetch(self, remote: str = "origin") -> None:
        repo = self._open()
        url = self._remote_url(repo, remote)
        with _silenced() as sink:
            try:
                # 传 remote *名称* 而非 URL：porcelain.fetch 仅在 remote_name 非空时
                # 调用 _import_remote_refs，把远端 refs/heads/* 落到 refs/remotes/<remote>/*。
                # 传 URL 会得到 remote_name=None，导致 HTTPS 下 ahead/behind 永不更新。
                porcelain.fetch(
                    repo,
                    remote_location=remote,
                    errstream=sink,
                    **self.transport_kwargs(url, operation="fetch"),
                )
            except Exception as exc:  # noqa: BLE001 - 跨库分类
                raise _classify_remote(exc, f"fetch {remote} 失败") from exc
        self._copy_local_remote_refs(repo, remote, url)

    def _copy_local_remote_refs(self, repo: Repo, remote: str, url: str) -> None:
        """本地路径远端：把远端 refs/heads/* 复制成 refs/remotes/<remote>/*（git fetch 语义）。"""
        if url.startswith(("http://", "https://")):
            return
        try:
            remote_repo = Repo(url)
        except Exception:  # noqa: BLE001 - 远端缺失时 _peek 已返回 None
            return
        prefix = b"refs/heads/"
        tracking_base = b"refs/remotes/" + remote.encode("utf-8") + b"/"
        for ref in list(remote_repo.refs.keys()):
            if ref.startswith(prefix):
                branch = ref[len(prefix) :]
                sha = self._ref(remote_repo, ref)
                if sha is not None:
                    repo.refs[tracking_base + branch] = sha

    def _ancestor_count(self, repo: Repo, include: bytes, exclude: bytes | None) -> int:
        walker = repo.get_walker(include=[include], exclude=[exclude] if exclude else None)
        return sum(1 for _ in walker)

    def ahead_behind(self) -> AheadBehind:
        repo = self._open()
        upstream = self._upstream_sha(repo)
        head = self._head_sha(repo)
        if head is None:
            return AheadBehind(ahead=0, behind=self._ancestor_count(repo, upstream, None))
        return AheadBehind(
            ahead=self._ancestor_count(repo, head, upstream),
            behind=self._ancestor_count(repo, upstream, head),
        )

    def pending_wb_commits(self) -> int:
        repo = self._open()
        head = self._head_sha(repo)
        if head is None:
            return 0
        exclude: list[bytes] = []
        if self.has_upstream():
            exclude.append(self._upstream_sha(repo))
        return sum(
            1
            for entry in repo.get_walker(include=[head], exclude=exclude)
            if entry.commit.message.decode("utf-8", "replace").lstrip().startswith("wb:")
        )

    def ff_merge_upstream(self) -> None:
        repo = self._open()
        upstream = self._upstream_sha(repo)
        head = self._head_sha(repo)
        if head is None:
            raise GitNonFastForward("无法快进合并（存在分叉，需人工处理）")
        if head == upstream:
            return
        # The two ancestor counts are the authoritative relation.  In
        # particular, a diverged pair has both counts > 0; checking only the
        # upstream walker can incorrectly treat that pair as fast-forwardable.
        counts = self.ahead_behind()
        if counts.ahead != 0 or counts.behind == 0:
            raise GitNonFastForward("无法快进合并（存在分叉，需人工处理）")
        self._move_to(repo, upstream)

    def _move_to(self, repo: Repo, target: bytes) -> None:
        """快进当前分支到 target：更新 ref 并把工作树/index 同步到新树。"""
        branch_ref = self._branch_ref(repo)
        old_tree = self._head_tree_id(repo)
        repo.refs[branch_ref] = target
        new_tree = repo[target].tree  # type: ignore[attr-defined]
        self._sync_worktree(repo, old_tree, new_tree)

    def _sync_worktree(self, repo: Repo, old_tree: bytes | None, new_tree: bytes) -> None:
        """把工作树与 index 从旧树同步到新树（写/删文件 + reset index）。"""
        old_flat = self._flatten(repo, old_tree)
        new_flat = self._flatten(repo, new_tree)
        for path, (mode, sha) in new_flat.items():
            if old_flat.get(path, ("", b""))[1] != sha:
                blob = repo[sha]
                destination = self._path / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob.data)  # type: ignore[attr-defined]
                try:
                    destination.chmod(int(mode, 8) & 0o777)
                except OSError:
                    pass
        for path in old_flat:
            if path not in new_flat:
                try:
                    (self._path / path).unlink()
                except FileNotFoundError:
                    pass
        repo.reset_index(new_tree)

    def push(self, remote: str = "origin") -> None:
        repo = self._open()
        url = self._remote_url(repo, remote)
        if url and "://" not in url and not Path(url).is_dir():
            raise GitRemoteUnavailable(f"push {remote} 失败")
        head = self._head_sha(repo)
        if head is None:
            raise GitError("没有可推送的提交")
        with _silenced() as sink:
            try:
                # 传 remote *名称* 而非 URL：porcelain.push 仅在 remote_name 非空时把
                # 推送后的 refs 经 _import_remote_refs 落到 refs/remotes/<remote>/*。
                # 否则 push 成功后 refs/remotes/origin/<branch> 仍停留在旧值，导致
                # ahead/behind 与 pending_wb_commits 永远不归零（P1-07D local-ahead 假象）。
                porcelain.push(
                    repo,
                    remote_location=remote,
                    errstream=sink,
                    **self.transport_kwargs(url, operation="push"),
                )
            except porcelain.DivergedBranches as exc:
                raise GitNonFastForward(f"push {remote} 失败（非快进被拒）") from exc
            except Exception as exc:  # noqa: BLE001
                raise _classify_remote(exc, f"push {remote} 失败") from exc
        remote_head = self._peek_remote_head(url)
        if remote_head is not None and remote_head != head:
            raise GitNonFastForward(f"push {remote} 失败（远端拒绝非快进）")

    def _peek_remote_head(self, url: str) -> bytes | None:
        if url.startswith(("http://", "https://")):
            return None  # HTTP(S) 远端 refs 由真实 HTTPS 门（P0-10/P0-13）验证
        try:
            return self._ref(Repo(url), b"HEAD")
        except Exception:  # noqa: BLE001 - 远端可能不存在
            return None

    def revert(self, sha: str) -> None:
        """撤销 wb 提交：生成反向提交（类似 ``git revert --no-edit``）。

        只支持「该提交之后没有其他提交再改同一批路径」的干净撤销；否则抛
        :class:`GitConflictError` 且不改动仓库（绝不 force）。
        """
        repo = self._open()
        head = self._head_sha(repo)
        target = self._resolve_sha(repo, sha)
        if head is None:
            raise GitError("没有可撤销的提交")
        commit = repo[target]
        parent_tree: bytes | None = (
            repo[commit.parents[0]].tree  # type: ignore[attr-defined]
            if commit.parents
            else None
        )
        target_tree = commit.tree  # type: ignore[attr-defined]
        base_flat = self._flatten(repo, parent_tree)
        target_flat = self._flatten(repo, target_tree)
        head_flat = self._flatten(repo, self._head_tree_id(repo))
        changed = set(base_flat) | set(target_flat)
        overrides: dict[str, Entry | None] = {}
        for path in changed:
            base_entry = base_flat.get(path)
            target_entry = target_flat.get(path)
            if base_entry == target_entry:
                continue  # 该提交未改动此路径
            if head_flat.get(path) != target_entry:
                raise GitConflictError(
                    f"git revert {sha} 失败：{path} 在后续提交中被修改（需人工处理）"
                )
            overrides[path] = base_entry
        old_tree = self._head_tree_id(repo)
        new_tree = _rebuild_tree(repo, old_tree, overrides)
        subject = commit.message.decode("utf-8", "replace").strip().splitlines()[0]
        self._write_commit(repo, f'Revert "{subject}"', author=None, tree=new_tree)
        self._sync_worktree(repo, old_tree, new_tree)

    # ---- 读提交/历史 ----

    def _resolve_sha(self, repo: Repo, sha: str) -> bytes:
        try:
            obj = repo.object_store[sha.encode("ascii")]
        except (KeyError, ValueError) as exc:
            raise GitInvalidRevision(f"无法解析提交：{sha}") from exc
        if getattr(obj, "type_name", b"") != b"commit":
            raise GitInvalidRevision(f"{sha} 不是 commit 对象")
        return obj.id

    def resolve_commit(self, sha: str) -> str:
        return self._resolve_sha(self._open(), sha).decode("ascii")

    def _commit(self, repo: Repo, sha: str):
        return repo[self._resolve_sha(repo, sha)]

    def commit_subject(self, sha: str) -> str:
        repo = self._open()
        return self._commit(repo, sha).message.decode("utf-8", "replace").strip().splitlines()[0]

    def commit_parent_count(self, sha: str) -> int:
        return len(self._commit(self._open(), sha).parents)

    def validate_commit(self, sha: str) -> tuple[str, int]:
        resolved = self.resolve_commit(sha)
        return self.commit_subject(resolved), self.commit_parent_count(resolved)

    def files_changed_by(self, sha: str) -> list[str]:
        repo = self._open()
        commit = self._commit(repo, sha)
        parent_id = commit.parents[0] if commit.parents else None
        parent_tree = repo[parent_id].tree if parent_id else None  # type: ignore[attr-defined]
        names: set[str] = set()
        for change in tree_changes(repo.object_store, parent_tree, commit.tree):
            path = change.new.path if change.new is not None else change.old.path
            names.add(path.decode("utf-8"))
        return sorted(names)

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        repo = self._open()
        head = self._head_sha(repo)
        rows: list[tuple[str, str, str]] = []
        if head is None:
            return rows
        needle = pattern.encode("utf-8")
        for entry in repo.get_walker(include=[head]):
            commit = entry.commit
            subject = commit.message.decode("utf-8", "replace").strip().splitlines()[0]
            if needle in subject.encode("utf-8"):
                when = datetime.datetime.fromtimestamp(commit.commit_time, datetime.UTC).isoformat()
                rows.append((commit.id.decode("ascii"), when, subject))
                if len(rows) >= limit:
                    break
        return rows

    def show_patch(self, sha: str) -> str:
        """某提交的差异文本（unified diff，路径/内容可检索；与 git 文本不完全逐字一致）。"""
        import difflib

        repo = self._open()
        commit = self._commit(repo, sha)
        parent_id = commit.parents[0] if commit.parents else None
        parent_tree = repo[parent_id].tree if parent_id else None  # type: ignore[attr-defined]
        parent_flat = self._flatten(repo, parent_tree)
        blocks: list[str] = []
        for change in tree_changes(repo.object_store, parent_tree, commit.tree):
            if change.new is not None:
                path = change.new.path.decode("utf-8")
                new_data = repo[change.new.sha].data  # type: ignore[attr-defined]
                old_data = (
                    repo[parent_flat[path][1]].data  # type: ignore[attr-defined]
                    if path in parent_flat
                    else b""
                )
            else:
                path = change.old.path.decode("utf-8")
                new_data = b""
                old_data = repo[change.old.sha].data  # type: ignore[attr-defined]
            diff = "".join(
                difflib.unified_diff(
                    old_data.decode("utf-8", "replace").splitlines(keepends=True),
                    new_data.decode("utf-8", "replace").splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
            blocks.append(diff)
        return "\n".join(blocks)

    def commits_between(self, since_iso: str, until_iso: str) -> list[tuple[str, str]]:
        repo = self._open()
        head = self._head_sha(repo)
        rows: list[tuple[str, str]] = []
        if head is None:
            return rows
        since_ts = int(
            datetime.datetime.fromisoformat(since_iso).replace(tzinfo=datetime.UTC).timestamp()
        )
        until_ts = int(
            datetime.datetime.fromisoformat(until_iso).replace(tzinfo=datetime.UTC).timestamp()
        )
        for entry in repo.get_walker(include=[head]):
            commit = entry.commit
            if since_ts <= commit.commit_time <= until_ts + 86_400:
                subject = commit.message.decode("utf-8", "replace").strip().splitlines()[0]
                rows.append((commit.id.decode("ascii")[:7], subject))
        return rows


def _rebuild_tree(
    repo: Repo,
    base_tree_id: bytes | None,
    overrides: dict[str, Entry | None],
) -> bytes:
    """基于 base 树重建一棵树：把 overrides（路径→entry 或 None=删除）落进去。

    从底向上构建目录节点后一次性写入 object store，保证子树 id 正确。
    """
    root = _DirNode()

    def node_for(dir_path: str) -> _DirNode:
        current = root
        if dir_path:
            for part in dir_path.split("/"):
                key = part.encode("utf-8")
                current = current.dirs.setdefault(key, _DirNode())
        return current

    def set_file(rel: str, mode: str, sha: bytes) -> None:
        dir_path, _, name = rel.rpartition("/")
        node_for(dir_path).files.append((name.encode("utf-8"), mode, sha))

    merged = DulwichGitBackend._flatten(repo, base_tree_id)
    for path, value in overrides.items():
        if value is None:
            merged.pop(path, None)
        else:
            merged[path] = value
    for rel, (mode, sha) in merged.items():
        set_file(rel, mode, sha)

    def build(node: _DirNode) -> bytes:
        tree = Tree()
        for name, child in sorted(node.dirs.items()):
            tree.add(name, 0o40000, build(child))
        for name, mode, sha in node.files:
            tree.add(name, int(mode, 8), sha)
        repo.object_store.add_object(tree)
        return tree.id

    return build(root)
