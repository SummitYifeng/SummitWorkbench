"""``WB_NO_AUTO_PUSH`` 开关：写入后不自动推送，且**必须可见**（不得伪装成同步成功）。

事故背景（2026-09-19）：跨端闸门加了 ``--no-push`` 仍被运行中的 App 自动推送 vault——
``mutation_runtime`` 把 ``push_after_commit`` 接在每条写路径上且没有开关。这里钉住三件事：

1. 默认**行为不变**（不设开关照常 push）；
2. 设了开关 → **不调用** ``push_after_commit``（绝不记录 ``ready``），but commit 照常；
3. 跳过时留下明确痕迹：响应说明 + 服务日志 ``auto_push_skipped``。
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from summit_workbench.config.auto_push import (
    AUTO_PUSH_DISABLE_ENV,
    auto_push_disabled,
    auto_push_skip_note,
)
from summit_workbench.observability.server_log import server_log_path
from summit_workbench.repositories.autocommit import CommitResult, CommitStatus
from summit_workbench.webapp import mutation_runtime
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.mutation_response import _mutation_fields
from summit_workbench.workflows import sync_coordinator
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, run_local_mutation


def _ctx(tmp_path: Path) -> WebContext:
    """带 active_workspace 的 WebContext（后置推送只在这种形态下被挂上）。"""
    return WebContext(
        vault_dir=tmp_path / "vault",
        work_root=tmp_path,
        timezone="UTC",
        active_workspace=SimpleNamespace(  # type: ignore[arg-type]
            profile=None,
            home=tmp_path / "home",
            workspace_id="ws-test",
        ),
    )


# ───────────────────────── 开关解析 ─────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        (" on ", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("no", False),
        ("random", False),
    ],
)
def test_auto_push_disabled_parsing(monkeypatch, value: str, expected: bool) -> None:
    monkeypatch.setenv(AUTO_PUSH_DISABLE_ENV, value)
    assert auto_push_disabled() is expected


def test_auto_push_disabled_defaults_false(monkeypatch) -> None:
    monkeypatch.delenv(AUTO_PUSH_DISABLE_ENV, raising=False)
    assert auto_push_disabled() is False


# ─────────────────── 后置推送出口：默认 push / 开关注入 ───────────────────


def test_push_after_commit_pushes_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(AUTO_PUSH_DISABLE_ENV, raising=False)
    calls: list[dict[str, object]] = []

    def fake_push(*_args: object, **kwargs: object) -> tuple[None, None]:
        calls.append(kwargs)
        return (None, None)

    monkeypatch.setattr(sync_coordinator, "push_after_commit", fake_push)
    note = mutation_runtime._push_after_commit(_ctx(tmp_path), where="test")
    assert note == ""
    assert len(calls) == 1


def test_push_after_commit_skips_and_leaves_trace(monkeypatch, tmp_path: Path) -> None:
    """开关启用：不推送、返回可见说明、写服务日志——且绝不产生同步成功状态。"""
    monkeypatch.setenv(AUTO_PUSH_DISABLE_ENV, "1")
    calls: list[object] = []
    monkeypatch.setattr(
        sync_coordinator, "push_after_commit", lambda *a, **k: calls.append(object())
    )
    note = mutation_runtime._push_after_commit(_ctx(tmp_path), where="unit-test")
    assert calls == []  # 关键：根本没有调用推送
    assert note == auto_push_skip_note()
    assert "已跳过自动推送" in note and AUTO_PUSH_DISABLE_ENV in note
    # 日志留痕：事件名可见，且不含任何 "ready" 伪装
    log_text = server_log_path(tmp_path / "home").read_text(encoding="utf-8")
    assert "auto_push_skipped" in log_text
    assert AUTO_PUSH_DISABLE_ENV in log_text


# ─────────────────── _commit_suffix（commit_suffix 写路径） ───────────────────


def _fake_commit(monkeypatch, status: CommitStatus = CommitStatus.COMMITTED) -> None:
    monkeypatch.setattr(
        mutation_runtime, "commit_paths", lambda *a, **k: CommitResult(status=status)
    )


def test_commit_suffix_pushes_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(AUTO_PUSH_DISABLE_ENV, raising=False)
    _fake_commit(monkeypatch)
    calls: list[object] = []
    monkeypatch.setattr(
        sync_coordinator, "push_after_commit", lambda *a, **k: calls.append(object())
    )
    note = mutation_runtime._commit_suffix(_ctx(tmp_path), [tmp_path / "vault" / "a.md"], "x")
    assert note == ""
    assert len(calls) == 1


def test_commit_suffix_appends_skip_note(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(AUTO_PUSH_DISABLE_ENV, "1")
    _fake_commit(monkeypatch)
    calls: list[object] = []
    monkeypatch.setattr(
        sync_coordinator, "push_after_commit", lambda *a, **k: calls.append(object())
    )
    note = mutation_runtime._commit_suffix(_ctx(tmp_path), [tmp_path / "vault" / "a.md"], "x")
    assert calls == []
    assert "已跳过自动推送" in note


# ─────────────── run_local_mutation / _mutation_fields（mutation 写路径） ───────────────


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")


def test_run_local_mutation_surfaces_push_note(tmp_path: Path) -> None:
    """后置推送回调返回的说明必须进 LocalMutationResult，并被响应字段暴露。"""
    vault = tmp_path / "vault"
    _init_repo(vault)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "a.md"
        path.write_text("x", encoding="utf-8")
        return LocalMutationOutcome(str(path), (path,))

    note = auto_push_skip_note()
    result = run_local_mutation(vault, "test", mutate, push_after_commit=lambda: note)
    assert result.commit_result.status is CommitStatus.COMMITTED
    assert result.push_note == note
    assert _mutation_fields(result)["auto_push"] == {"skipped": True, "note": note}


def test_run_local_mutation_has_no_auto_push_field_by_default(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_repo(vault)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "a.md"
        path.write_text("x", encoding="utf-8")
        return LocalMutationOutcome(str(path), (path,))

    result = run_local_mutation(vault, "test", mutate, push_after_commit=None)
    assert result.push_note == ""
    assert "auto_push" not in _mutation_fields(result)


def test_run_local_mutation_ignores_non_string_push_result(tmp_path: Path) -> None:
    """正常推送回调返回的是 (SyncState, snapshot) 元组，绝不能被塞进响应。"""
    vault = tmp_path / "vault"
    _init_repo(vault)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "a.md"
        path.write_text("x", encoding="utf-8")
        return LocalMutationOutcome(str(path), (path,))

    result = run_local_mutation(vault, "test", mutate, push_after_commit=lambda: (object(), None))
    assert result.push_note == ""
    assert "auto_push" not in _mutation_fields(result)


# ─────────── 结构性守卫：自动推送必须经过单一出口 ───────────
#
# `WB_NO_AUTO_PUSH` 只在 `mutation_runtime._push_after_commit` 这一层生效。若有人新增一条
# **绕过该出口**直接调 `sync_coordinator.push_after_commit` 的写路径，开关就失效了，而且不会有
# 任何测试变红。下面这条 AST 守卫把"允许的直接调用点"钉成白名单：
#
# - `webapp/mutation_runtime.py::_push_after_commit`：**唯一的自动推送出口**（开关在这里生效）；
# - `webapp/routers/sync_conflicts.py::api_sync_conflict_recover`：使用者显式发起的同步
#   （本就该推）。
#
# 新增直接调用点必须同时改这张名单并说明理由——那正是让下一个人"看得见"的地方。
# 变异验证：在 `src/` 下任意模块加一处 `sync_coordinator.push_after_commit(...)`，本测试变红。
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "summit_workbench"
_COORDINATOR_MODULE = "summit_workbench.workflows.sync_coordinator"
_ALLOWED_DIRECT_PUSH_CALL_SITES = {
    ("webapp/mutation_runtime.py", "_push_after_commit"),
    ("webapp/routers/sync_conflicts.py", "api_sync_conflict_recover"),
}


def _collect_push_calls(
    node: ast.AST,
    rel: str,
    imported_names: set[str],
    stack: tuple[str, ...],
    sites: set[tuple[str, str]],
) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        stack = (*stack, node.name)
    elif isinstance(node, ast.Call):
        func = node.func
        is_attr = isinstance(func, ast.Attribute) and func.attr == "push_after_commit"
        is_bound_name = isinstance(func, ast.Name) and func.id in imported_names
        if is_attr or is_bound_name:
            sites.add((rel, stack[-1] if stack else "<module>"))
    for child in ast.iter_child_nodes(node):
        _collect_push_calls(child, rel, imported_names, stack, sites)


def _direct_push_call_sites() -> set[tuple[str, str]]:
    """扫 `src/` 源码，返回 `(相对路径, 最内层函数名)` 的直接调用点集合。"""
    sites: set[tuple[str, str]] = set()
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(_SRC_ROOT).as_posix()
        imported_names = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == _COORDINATOR_MODULE
            for alias in node.names
            if alias.name == "push_after_commit"
        }
        _collect_push_calls(tree, rel, imported_names, (), sites)
    return sites


def test_auto_push_goes_through_the_single_gated_outlet() -> None:
    """只有白名单里的调用点能直接推 vault；其余必须走 `_push_after_commit`（受开关管）。"""
    assert _direct_push_call_sites() == _ALLOWED_DIRECT_PUSH_CALL_SITES


def test_the_gated_outlet_really_is_the_only_auto_push_path() -> None:
    """`mutation_runtime` 里只允许 `_push_after_commit` 一个直接调用点（防止悄悄加出口）。"""
    runtime_sites = {
        name for rel, name in _direct_push_call_sites() if rel.endswith("mutation_runtime.py")
    }
    assert runtime_sites == {"_push_after_commit"}
