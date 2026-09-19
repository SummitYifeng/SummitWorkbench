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
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from dulwich import porcelain
from dulwich.diff_tree import tree_changes
from dulwich.errors import NotGitRepository
from dulwich.ignore import IgnoreFilterManager
from dulwich.index import IndexEntry
from dulwich.objects import Blob, Commit, ObjectID, Tree
from dulwich.refs import Ref
from dulwich.repo import Repo

from summit_workbench.config.tls_trust import ca_bundle_path as ca_bundle_path
from summit_workbench.repositories.git_backend import (
    AheadBehind,
    CommitIdentity,
    CommitMetadata,
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
    is_missing_local_remote,
)

Entry = tuple[str, ObjectID]  # (octal mode, blob sha)


def _object_id(value: bytes) -> ObjectID:
    """Narrow Dulwich's runtime-compatible bytes values to its typed object id."""
    return cast(ObjectID, value)


def _commit_object(repo: Repo, sha: ObjectID) -> Commit:
    obj = repo[sha]
    if not isinstance(obj, Commit):
        raise GitError("对象不是 commit")
    return obj


def _tree_object(repo: Repo, sha: ObjectID) -> Tree:
    obj = repo[sha]
    if not isinstance(obj, Tree):
        raise GitError("对象不是 tree")
    return obj


def _blob_object(repo: Repo, sha: ObjectID) -> Blob:
    obj = repo[sha]
    if not isinstance(obj, Blob):
        raise GitError("对象不是 blob")
    return obj


def _commit_message(commit: Commit) -> bytes:
    return cast(bytes, commit.message)


def _git_subject(message: str) -> str:
    """按 ``git log --pretty=%s`` 的规则取提交主题（**不调用系统 git**）。

    规则（2026-09-19 用真实 git 实测确认）：

    - 取**首个空行之前**的整段；段内换行折成**一个空格**（``first\\nsecond`` → ``first second``）；
    - 续行的**缩进保留**（``first\\n  second`` → ``first   second``：折行那一个空格 + 原缩进两个）；
    - 开头的空行跳过；两端去空白。

    为什么不用 ``splitlines()[0]``：那只取第一行，多行首段会被截断，于是同一个库在两个后端上
    会返回**不同的主题**（system 用 ``%s``，dulwich 用第一行）。
    """
    paragraph: list[str] = []
    for line in message.splitlines():
        if not line.strip():
            if paragraph:
                break
            continue
        paragraph.append(line)
    return " ".join(paragraph).strip()


def _identity_bytes(identity: CommitIdentity | None) -> bytes:
    chosen = identity if identity is not None else default_identity()
    return f"{chosen.name} <{chosen.email}>".encode()


def _silenced() -> Any:
    # porcelain 的进度/错误输出可能写 bytes；留在内存里以便失败时附进 typed error。
    return tempfile.SpooledTemporaryFile(max_size=64 * 1024, mode="w+b")


def _sanitize_diagnostic(text: str) -> str:
    text = re.sub(r"(https?://)[^/\s:@]+:[^@\s]+@", r"\1<redacted>@", text)
    text = re.sub(
        r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"(?i)((?:token|password|secret)\s*[=:]\s*)[^\s]+", r"\1<redacted>", text)
    return text.replace("\x00", " ").strip()[:2000]


def _sink_text(sink: Any) -> str:
    sink.seek(0)
    raw = sink.read(8 * 1024)
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    return _sanitize_diagnostic(text)


def _diagnostic_text(value: Any) -> str:
    if not value:
        return ""
    return _sanitize_diagnostic(value) if isinstance(value, str) else _sink_text(value)


def _classify_remote(exc: BaseException, message: str, *, stderr: Any = "") -> GitError:
    """把 dulwich/网络异常映射成 typed error（文本不含 URL 或凭据）。

    顺序重要：证书 → TLS 握手 → 认证 → 代理 → 网络，避免宽泛标记互相吞并。
    未命中任何已知标记的异常归为 :class:`GitBackendRuntimeError`，绝不伪装成
    远端不可达（便于 acceptance preflight 区分「后端 bug」与「网络/凭据/TLS」）。

    **已经是我们自己的 typed error 时原样抛出**：否则它的类型会被下面的文本匹配抹掉。
    2026-09-13 真机复现——恢复机器后还没做 HTTPS 转换时，``transport_kwargs()`` 抛
    :class:`GitCredentialsUnavailable`（"缺少 workspace-scoped Git 凭据配置"），却被这段
    兜底重新包成 ``GitBackendRuntimeError`` ⇒ 原因码落成 ``unclassified``，界面只说
    「未分类的同步失败」，正好把 D3 想要的"缺凭据"说没了。
    """
    if isinstance(exc, GitError):
        error = exc
        error.stderr = _diagnostic_text(stderr)
        return error
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
        error = GitProxyError(message)
        error.stderr = _diagnostic_text(stderr)
        return error
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
        error = GitCertificateError(message)
        error.stderr = _diagnostic_text(stderr)
        return error
    if any(marker in text for marker in ("ssl", "tls", "handshake")):
        error = GitTlsError(message)
        error.stderr = _diagnostic_text(stderr)
        return error
    if any(
        marker in text
        for marker in ("auth", "401", "403", "permission", "unauthorized", "forbidden")
    ):
        error = GitAuthError(message)
        error.stderr = _diagnostic_text(stderr)
        return error
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
        error = GitRemoteUnavailable(message)
        error.stderr = _diagnostic_text(stderr)
        return error
    error = GitBackendRuntimeError(message)
    error.stderr = _diagnostic_text(stderr)
    return error


def _https_pool_manager(url: str) -> Any:
    """为 HTTPS 远端构造带 CA bundle 的 urllib3 连接池（保留 dulwich 代理支持）。

    frozen 环境下 OpenSSL 默认 CA 路径不可用（P1-07D：``git_tls_failed``），因此
    显式把发现的 CA bundle 通过 ``http.sslCAInfo`` 传入 dulwich 的
    ``default_urllib3_manager``；``sslVerify=true`` 保持 TLS 校验开启。

    另外：直连优先；仅在没有 env 代理且直连路径需要回退时，显式使用 macOS 系统代理
    （``http.proxy``），绝不关闭 TLS 校验。
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
        self.files: list[tuple[bytes, str, ObjectID]] = []  # (name, mode, sha)
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
    def _ref(repo: Repo, name: bytes) -> ObjectID | None:
        try:
            return repo.refs[Ref(name)]
        except KeyError:
            return None

    def _head_sha(self, repo: Repo) -> ObjectID | None:
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
        tree: ObjectID | None = None,
        parent: ObjectID | None = None,
    ) -> ObjectID:
        identity = _identity_bytes(author)
        new_sha = repo.get_worktree().commit(
            message=message.encode("utf-8"),
            author=identity,
            committer=identity,
            tree=tree,
            ref=Ref(b"HEAD"),
            merge_heads=[parent] if parent else None,
        )
        return new_sha

    # ---- detect / init / clone ----

    def is_git_repo(self) -> bool:
        return (self._path / ".git").exists()

    def init(self, *, bare: bool = False, default_branch: str = "main") -> None:
        # dulwich 默认把 HEAD 指向 refs/heads/master；产品约定是 main（同步横幅、克隆对端、
        # 验收记录都按 main 写），所以显式指定，避免新工作台一诞生就叫 master。
        self._path.mkdir(parents=True, exist_ok=True)
        branch = default_branch.encode("utf-8")
        if bare:
            Repo.init_bare(str(self._path), default_branch=branch)
        else:
            Repo.init(str(self._path), default_branch=branch)

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
                raise _classify_remote(exc, "clone 失败", stderr=_sink_text(sink)) from exc
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

    def remove_remote(self, name: str = "origin") -> None:
        """删除 remote 配置段（幂等：本来就没有时为 no-op）。

        G2 的"首次发布"在失败回滚时用它把刚加的 origin 抹掉；绝不动 refs 与工作树。
        """
        repo = self._open()
        section = (b"remote", name.encode("utf-8"))
        if self._config_get(repo, section, b"url") is None:
            return
        config = repo.get_config()
        config._values.pop(section, None)
        config.write_to_path()

    def set_upstream(self, remote: str = "origin", branch: str | None = None) -> None:
        """写 ``branch.<name>.remote/merge``（等价 ``git push -u``）。

        只写配置：@ {u}、ahead/behind 与"有 upstream"判定都依赖它；不碰 refs 或工作树。
        """
        repo = self._open()
        if branch is None:
            ref_name = self._branch_ref(repo)
            name = ref_name[len(b"refs/heads/") :]
        else:
            name = branch.encode("utf-8")
            ref_name = b"refs/heads/" + name
        config = repo.get_config()
        section = (b"branch", name)
        config.set(section, b"remote", remote.encode("utf-8"))
        config.set(section, b"merge", ref_name)
        config.write_to_path()

    def _head_ref_name(self, repo: Repo) -> bytes | None:
        """HEAD 符号引用最终指向的分支 ref（detached HEAD → None）。"""
        raw = repo.refs.read_ref(Ref(b"HEAD"))
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

    def upstream_revision(self) -> str:
        return self._upstream_sha(self._open()).decode("ascii")

    def _upstream_sha(self, repo: Repo) -> ObjectID:
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

    def _head_tree_id(self, repo: Repo) -> ObjectID | None:
        head = self._head_sha(repo)
        if head is None:
            return None
        try:
            return _object_id(_commit_object(repo, head).tree)
        except (KeyError, TypeError, AttributeError):
            return None

    @staticmethod
    def _flatten(repo: Repo, tree_id: ObjectID | None) -> dict[str, Entry]:
        if tree_id is None:
            return {}
        flat: dict[str, Entry] = {}

        def walk(prefix: str, tree: Tree) -> None:
            for name, mode, sha in tree.iteritems():
                rel = f"{prefix}{name.decode('utf-8')}"
                if mode & 0o40000:
                    walk(f"{rel}/", _tree_object(repo, sha))
                else:
                    flat[rel] = (f"{mode:o}", sha)

        walk("", _tree_object(repo, tree_id))
        return flat

    def _index_entries(self, repo: Repo) -> dict[str, ObjectID]:
        index = repo.open_index()
        entries: dict[str, ObjectID] = {}
        for path, entry in index.iteritems():
            sha = getattr(entry, "sha", None)
            if sha is not None:
                entries[path.decode("utf-8")] = _object_id(sha)
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
                # .wb.lock 是工作台跨进程锁。它可能位于历史版本使用的 vault 根，
                # 但始终是机器内部状态，不是用户内容，不应触发 dirty-protected。
                if rel == ".wb.lock":
                    continue
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

    def dirty_paths(self) -> list[str]:
        """返回未被 ignore 的工作树/暂存区脏路径（相对仓库根）。"""
        repo = self._open()
        changed, untracked = self._worktree_delta(repo)
        return sorted(set(self._staged_paths(repo)) | changed | untracked)

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
        ignore_manager = IgnoreFilterManager.from_repo(repo)
        for rel in paths:
            # 被 ignore 的路径永不入 index；已跟踪且同时被 ignore 的文件也不会被这个 add 暂存。
            # 这是 Git 语义，vault 侧已保证 _signals/ 不再被跟踪。
            if ignore_manager.is_ignored(rel):
                continue
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

    def commit_merge(
        self,
        message: str,
        merge_parent: str,
        *,
        author: CommitIdentity | None = None,
    ) -> None:
        """Create a normal two-parent commit from the prepared index tree."""
        repo = self._open()
        head = self._head_sha(repo)
        if head is None:
            raise GitError("git merge commit 失败：HEAD 无法解析")
        parent = self._resolve_sha(repo, merge_parent)
        if head == parent:
            raise GitError("merge parent 不能与当前 HEAD 相同")
        tree = repo.open_index().commit(repo.object_store)
        try:
            self._write_commit(repo, message, author=author, tree=tree, parent=parent)
        except KeyError as exc:
            raise GitError("git merge commit 失败：HEAD 无法解析") from exc

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
        # workspace_id 只在**需要从 Keychain 按作用域查找**时才必需。空安装向导克隆
        # 私有远端时手里没有这个 id（它由远端 marker 决定），于是显式注入本次要用的
        # resolver；此时 workspace_id 为空是正常的（2026-09-13 实测：此前的强制检查
        # 让向导的 clone 抛 GitCredentialsUnavailable，又被上层兜底成"请检查凭据、
        # 网络或 TLS"，真因完全不可见）。
        resolver = self._credential_resolver
        if not self._username or (resolver is None and not self._workspace_id):
            raise GitCredentialsUnavailable("HTTPS remote 缺少 workspace-scoped Git 凭据配置")
        if resolver is None:
            from summit_workbench.config.git_credentials import resolve_git_credentials

            resolver = resolve_git_credentials
        try:
            credentials = resolver(self._workspace_id or "", parsed.hostname or "", self._username)
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
                raise _classify_remote(
                    exc, f"fetch {remote} 失败", stderr=_sink_text(sink)
                ) from exc
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
                    repo.refs[Ref(tracking_base + branch)] = sha

    def _ancestor_count(self, repo: Repo, include: ObjectID, exclude: ObjectID | None) -> int:
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
        exclude: list[ObjectID] = []
        if self.has_upstream():
            exclude.append(self._upstream_sha(repo))
        count = 0
        for entry in repo.get_walker(include=[head], exclude=exclude):
            if _commit_message(entry.commit).decode("utf-8", "replace").lstrip().startswith("wb:"):
                count += 1
        return count

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

    def _move_to(self, repo: Repo, target: ObjectID) -> None:
        """快进当前分支到 target：更新 ref 并把工作树/index 同步到新树。"""
        branch_ref = self._branch_ref(repo)
        old_tree = self._head_tree_id(repo)
        repo.refs[Ref(branch_ref)] = target
        new_tree = _commit_object(repo, target).tree
        self._sync_worktree(repo, old_tree, new_tree)

    def _sync_worktree(self, repo: Repo, old_tree: ObjectID | None, new_tree: ObjectID) -> None:
        """把工作树与 index 从旧树同步到新树（写/删文件 + reset index）。"""
        old_flat = self._flatten(repo, old_tree)
        new_flat = self._flatten(repo, new_tree)
        for path, (mode, sha) in new_flat.items():
            if old_flat.get(path, ("", b""))[1] != sha:
                blob = _blob_object(repo, sha)
                destination = self._path / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob.data)
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
        repo.get_worktree().reset_index(new_tree)

    @staticmethod
    def _is_ancestor(repo: Repo, ancestor: ObjectID | None, descendant: ObjectID | None) -> bool:
        """**不看 commit_time** 的图可达性：ancestor 是否为 descendant 的祖先（含相等）。

        D9：dulwich 的 ``graph.can_fast_forward`` 用 commit_time 剪枝（``WorkList`` 按
        时间戳出队），一旦远端父提交的 committer time 晚于本地提交（两台机器时钟偏差，
        或任何把提交时间写晚的来源），从 tip 出发的遍历会把整条路径剪掉 ⇒ 找不到公共
        祖先 ⇒ 误报分叉。这里只沿 parents 做 BFS，时间戳与对象是否缺失都不影响结论。
        """
        if ancestor is None or descendant is None:
            return False
        if ancestor == descendant:
            return True
        seen: set[ObjectID] = set()
        stack: list[ObjectID] = [descendant]
        while stack:
            sha = stack.pop()
            if sha in seen:
                continue
            seen.add(sha)
            if sha == ancestor:
                return True
            try:
                commit = repo.object_store[sha]
            except KeyError:
                continue  # 对象缺失（浅克隆/部分推送）时不能证明可达
            if isinstance(commit, Commit):
                stack.extend(commit.parents)
        return False

    def _push_refspec(self, repo: Repo) -> bytes | None:
        """当前分支的显式 refspec（``refs/heads/<branch>:<remote ref>``）。

        远端 ref 优先取 ``branch.<name>.merge``；没有 upstream 配置时退回同名分支。
        只作用于这一个 ref——绝不使用"无 refspec + force"的写法（那会 force 所有 ref）。
        """
        ref_name = self._head_ref_name(repo)
        if ref_name is None or not ref_name.startswith(b"refs/heads/"):
            return None
        branch = ref_name[len(b"refs/heads/") :]
        remote_ref = self._config_get(repo, (b"branch", branch), b"merge") or ref_name
        return ref_name + b":" + remote_ref

    def _push_confirmed_fast_forward(
        self, repo: Repo, remote: str, url: str, sink: Any, exc: porcelain.DivergedBranches
    ) -> None:
        """D9：dulwich 误报分叉后的复核与收敛。

        只有**图可达性复核确认远端 tip 是本地 head 的祖先**（真快进）时才显式强推这
        一个分支一次；复核不通过仍然是 typed ``GitNonFastForward``，绝不无条件 force。
        """
        if not self._is_ancestor(repo, _object_id(exc.current_sha), _object_id(exc.new_sha)):
            raise GitNonFastForward(f"push {remote} 失败（非快进被拒）") from exc
        refspec = self._push_refspec(repo)
        if refspec is None:
            raise GitNonFastForward(f"push {remote} 失败（非快进被拒）") from exc
        try:
            porcelain.push(
                repo,
                remote_location=remote,
                refspecs=[refspec],
                force=True,
                errstream=sink,
                **self.transport_kwargs(url, operation="push"),
            )
        except Exception as inner:  # noqa: BLE001 - 跨库分类
            raise _classify_remote(inner, f"push {remote} 失败", stderr=_sink_text(sink)) from inner
        # G3：把"图复核通过 ⇒ 单 refspec 强推成功"这件事写进本机服务日志
        # （只写稳定原因码与分支名，不写 URL/主机/路径）。日志是 best-effort，绝不让
        # 一次成功的推送因为写日志失败而变成失败。
        from summit_workbench.observability.server_log import log_push_confirmed_fast_forward

        branch_name = refspec.split(b":", 1)[0].decode("utf-8", "replace")
        log_push_confirmed_fast_forward(branch=branch_name.removeprefix("refs/heads/"))

    def push(self, remote: str = "origin") -> None:
        repo = self._open()
        url = self._remote_url(repo, remote)
        if is_missing_local_remote(url):
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
                # D9：先做不看时间戳的图复核，只有真快进才对该 ref 显式强推一次。
                self._push_confirmed_fast_forward(repo, remote, url, sink, exc)
            except Exception as exc:  # noqa: BLE001
                raise _classify_remote(exc, f"push {remote} 失败", stderr=_sink_text(sink)) from exc
        remote_head = self._peek_remote_head(url)
        if remote_head is not None and remote_head != head:
            raise GitNonFastForward(f"push {remote} 失败（远端拒绝非快进）")

    def _peek_remote_head(self, url: str) -> ObjectID | None:
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
        commit = _commit_object(repo, target)
        parent_tree: ObjectID | None = (
            _commit_object(repo, commit.parents[0]).tree if commit.parents else None
        )
        target_tree = commit.tree
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

    def _resolve_sha(self, repo: Repo, sha: str) -> ObjectID:
        try:
            obj = repo.object_store[_object_id(sha.encode("ascii"))]
        except (KeyError, ValueError) as exc:
            raise GitInvalidRevision(f"无法解析提交：{sha}") from exc
        if not isinstance(obj, Commit):
            raise GitInvalidRevision(f"{sha} 不是 commit 对象")
        return obj.id

    def resolve_commit(self, sha: str) -> str:
        return self._resolve_sha(self._open(), sha).decode("ascii")

    def _commit(self, repo: Repo, sha: str) -> Commit:
        return _commit_object(repo, self._resolve_sha(repo, sha))

    def commit_subject(self, sha: str) -> str:
        repo = self._open()
        return (
            _commit_message(self._commit(repo, sha))
            .decode("utf-8", "replace")
            .strip()
            .splitlines()[0]
        )

    def commit_parent_count(self, sha: str) -> int:
        return len(self._commit(self._open(), sha).parents)

    def validate_commit(self, sha: str) -> tuple[str, int]:
        resolved = self.resolve_commit(sha)
        return self.commit_subject(resolved), self.commit_parent_count(resolved)

    def files_changed_by(self, sha: str) -> list[str]:
        repo = self._open()
        commit = self._commit(repo, sha)
        parent_id = commit.parents[0] if commit.parents else None
        parent_tree = _commit_object(repo, parent_id).tree if parent_id else None
        names: set[str] = set()
        for change in tree_changes(repo.object_store, parent_tree, commit.tree):
            entry = change.new if change.new is not None else change.old
            if entry is None:
                continue
            path = entry.path
            names.add(path.decode("utf-8"))
        return sorted(names)

    def merge_base(self, left: str, right: str) -> str:
        from dulwich.graph import find_merge_base

        repo = self._open()
        bases = find_merge_base(
            repo,
            [self._resolve_sha(repo, left), self._resolve_sha(repo, right)],
        )
        if not bases:
            raise GitError("两个提交没有共同祖先")
        return sorted(base.decode("ascii") for base in bases)[0]

    def files_changed_between(self, base: str, head: str) -> list[str]:
        repo = self._open()
        base_commit = self._commit(repo, base)
        head_commit = self._commit(repo, head)
        old = self._flatten(repo, base_commit.tree)
        new = self._flatten(repo, head_commit.tree)
        return sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))

    def commit_metadata(self, sha: str) -> CommitMetadata:
        commit = self._commit(self._open(), sha)
        subject = commit.message.decode("utf-8", "replace").strip().splitlines()[0]
        authored_at = datetime.datetime.fromtimestamp(commit.author_time, datetime.UTC).isoformat()
        return CommitMetadata(
            revision=commit.id.decode("ascii"), authored_at=authored_at, subject=subject
        )

    def read_file_at(self, revision: str, path: str) -> bytes | None:
        repo = self._open()
        commit = self._commit(repo, revision)
        entry = self._flatten(repo, commit.tree).get(path)
        if entry is None:
            return None
        return _blob_object(repo, entry[1]).data

    def log_grep(self, pattern: str, limit: int) -> list[tuple[str, str, str]]:
        """grep 提交消息的最近提交，返回 ``(sha, ISO 时间, 主题)``。

        语义与 system 后端的 ``git log --grep=<pattern>`` 对齐——它是**正则**，且
        ``^``/``$`` 锚定消息的**每一行**（实测：``--grep='^wb:'`` 能命中正文里以 ``wb:``
        开头的那一行）。因此这里：

        - 匹配目标是**整条提交消息**（不只是主题），``re.MULTILINE`` 复刻 git 的按行锚定；
        - 返回的第三项仍是**主题**，按 ``git log --pretty=%s`` 的规则算（首个空行前的整段、
          换行折成空格、两端去空白；续行的缩进**保留**——实测 ``first\\n  second`` 的 %s 是
          ``first   second``）。

        2026-09-19 真实缺陷（用户可见）：这里原来是 ``needle in subject`` —— **字面子串**、
        且只匹配主题 ⇒ 生产常量 ``autocommit._WB_PREFIX_GREP = "^wb:"`` 在本后端（**打包 App
        固定的后端**）下恒不命中，``list_wb_commits()`` 恒返回 ``[]`` ⇒「撤销历史」面板空白。

        残留差异（已知，登记）：git 用 POSIX ERE，这里用 Python ``re``；``\\d`` / ``\\w`` /
        lookaround 这类写法两者含义不同。生产上只用 ``^wb:``，两种 flavour 下一致。
        """
        repo = self._open()
        head = self._head_sha(repo)
        rows: list[tuple[str, str, str]] = []
        if head is None:
            return rows
        try:
            matcher = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            # 与 system 后端对齐：非法正则是**类型化错误**，不是"静默零命中"
            # （system 走 _classify 抛 GitError）。
            raise GitError(f"log_grep 正则无效 {pattern!r}：{exc}") from None
        for entry in repo.get_walker(include=[head]):
            commit = entry.commit
            message = commit.message.decode("utf-8", "replace")
            if matcher.search(message) is None:
                continue
            when = datetime.datetime.fromtimestamp(commit.commit_time, datetime.UTC).isoformat()
            rows.append((commit.id.decode("ascii"), when, _git_subject(message)))
            if len(rows) >= limit:
                break
        return rows

    def show_patch(self, sha: str) -> str:
        """某提交的差异文本（unified diff，路径/内容可检索；与 git 文本不完全逐字一致）。"""
        import difflib

        repo = self._open()
        commit = self._commit(repo, sha)
        parent_id = commit.parents[0] if commit.parents else None
        parent_tree = _commit_object(repo, parent_id).tree if parent_id else None
        parent_flat = self._flatten(repo, parent_tree)
        blocks: list[str] = []
        for change in tree_changes(repo.object_store, parent_tree, commit.tree):
            if change.new is not None:
                path = change.new.path.decode("utf-8")
                new_data = _blob_object(repo, change.new.sha).data
                old_data = (
                    _blob_object(repo, parent_flat[path][1]).data if path in parent_flat else b""
                )
            else:
                if change.old is None:
                    continue
                path = change.old.path.decode("utf-8")
                new_data = b""
                old_data = _blob_object(repo, change.old.sha).data
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
    base_tree_id: ObjectID | None,
    overrides: dict[str, Entry | None],
) -> ObjectID:
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

    def set_file(rel: str, mode: str, sha: ObjectID) -> None:
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

    def build(node: _DirNode) -> ObjectID:
        tree = Tree()
        for name, child in sorted(node.dirs.items()):
            tree.add(name, 0o40000, build(child))
        for name, mode, sha in node.files:
            tree.add(name, int(mode, 8), sha)
        repo.object_store.add_object(tree)
        return tree.id

    return build(root)
