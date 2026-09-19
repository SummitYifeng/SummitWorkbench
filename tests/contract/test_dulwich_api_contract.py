"""dulwich 传输参数契约：本仓库交给 dulwich 的关键字参数，必须被**当前安装版本**接受。

背景（2026-09-19 真机，用户可见故障）：dulwich `1.2.15` 把 ``pool_manager`` 从
``porcelain.fetch`` 的签名里移除了（fetch/push/clone 三个里只有后两者还有 ``**kwargs``），
而 ``dulwich_git.py`` 的 fetch 仍按 0.22.x 的 API 把 ``transport_kwargs()`` 交给它
⇒ ``TypeError: fetch() got an unexpected keyword argument 'pool_manager'``，被
``_classify_remote`` 兜底压成 ``unclassified``，界面只显示「未分类的同步失败」。

这条路径的坏味道在于**测试与 CLI 都看不见它**：单测要么把 ``transport_kwargs``
monkeypatch 成 ``{}``（本地路径远端走这个分支），要么只断言它返回的内容；CLI 默认走
system git 后端。于是「测试全绿 + CLI 正常 + 打包 App（固定 dulwich）× HTTPS 远端永远
同步失败」。本文件用两个角度钉住它：

1. **行为回归**：HTTPS fetch 必须把 transport kwargs 交给**接受它们**的入口
   （``get_transport_and_path``）。旧实现直接交给 ``porcelain.fetch``，本测试会红。
2. **参数面收敛**：``transport_kwargs()`` 返回的键必须都在传输入口的形参里。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dulwich import porcelain
from dulwich.client import get_transport_and_path
from dulwich.repo import Repo
from pydantic import SecretStr

from summit_workbench.repositories import dulwich_git
from summit_workbench.repositories.dulwich_git import DulwichGitBackend

_HTTPS_URL = "https://github.com/acme/private.git"


def _backend(repo_path: Path) -> DulwichGitBackend:
    return DulwichGitBackend(
        repo_path,
        workspace_id="ws-1",
        username="tester",
        # resolver 返回的对象形状必须与生产一致：``.password`` 是 SecretStr。
        credential_resolver=lambda *_: SimpleNamespace(password=SecretStr("token")),
    )


def _repo_with_https_origin(path: Path) -> Repo:
    repo = Repo.init(str(path))
    config = repo.get_config()
    config.set((b"remote", b"origin"), b"url", _HTTPS_URL.encode())
    config.write_to_path()  # fetch 会重新 open 仓库，必须落盘才可见
    return repo


def test_https_fetch_hands_transport_kwargs_to_an_entry_point_that_accepts_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTPS fetch 的 transport kwargs 必须交给能接受它们的入口（旧实现会让本测试变红）。

    旧实现：``porcelain.fetch(repo, remote_location=remote, errstream=sink, **kwargs)``
    —— dulwich 1.2.15 的 ``porcelain.fetch`` 没有 ``pool_manager`` 形参，直接 TypeError。
    """
    work = tmp_path / "work"
    work.mkdir()
    _repo_with_https_origin(work)
    backend = _backend(work)
    sentinel = object()
    monkeypatch.setattr(
        backend, "transport_kwargs", lambda url, *, operation: {"pool_manager": sentinel}
    )

    received: dict[str, Any] = {}

    class _FakeClient:
        def fetch(self, path: bytes, target: Any, progress: Any = None) -> Any:
            received["path"] = path
            return SimpleNamespace(refs={})

    def _fake_gate(url: str, **kwargs: Any) -> tuple[Any, str]:
        received["url"] = url
        received.update(kwargs)
        return _FakeClient(), "/acme/private.git"

    monkeypatch.setattr(dulwich_git, "get_transport_and_path", _fake_gate)

    backend.fetch("origin")

    assert received.get("pool_manager") is sentinel, "transport kwargs 没到达传输入口"
    assert received.get("operation") == "fetch"
    assert received.get("url") == _HTTPS_URL
    assert received.get("path") == b"/acme/private.git"


def test_https_transport_kwargs_are_all_accepted_by_the_transport_gate(tmp_path: Path) -> None:
    """``transport_kwargs()`` 的每个键都必须在传输入口的形参里（含 ``**kwargs`` 兜底）。"""
    kwargs = _backend(tmp_path).transport_kwargs(_HTTPS_URL, operation="fetch")
    signature = inspect.signature(get_transport_and_path)
    accepts_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if not accepts_var_kwargs:
        unexpected = sorted(set(kwargs) - set(signature.parameters))
        assert not unexpected, f"get_transport_and_path 不接受这些传输参数：{unexpected}"


def test_porcelain_fetch_has_no_pool_manager_which_is_why_fetch_bypasses_it() -> None:
    """钉住"为什么要自己建 client"这个前提。

    若这条断言失败，说明 dulwich 重新让 ``porcelain.fetch`` 接受传输参数——那时可以回头
    简化 ``DulwichGitBackend.fetch``（但**先确认** fetch/push/clone 三者行为一致）。
    """
    signature = inspect.signature(porcelain.fetch)
    assert "pool_manager" not in signature.parameters
    assert not any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ), "porcelain.fetch 现在接受 **kwargs 了：可简化 fetch 实现，请复核本文件的理由"
