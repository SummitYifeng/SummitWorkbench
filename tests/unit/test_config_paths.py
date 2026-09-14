"""路径解析测试。重点：不硬编码用户名，尊重 WORK_ROOT，默认派生正确。"""

from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.config.paths import (
    UserPathError,
    resolve_user_path,
    resolve_work_paths,
    resolve_work_root,
)


def test_default_work_root_under_home(monkeypatch) -> None:
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fake-home")
    assert resolve_work_root() == Path("/tmp/fake-home/Documents/Work")


def test_env_work_root_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv("WORK_ROOT", "/tmp/custom-work")
    assert resolve_work_root() == Path("/tmp/custom-work")


def test_explicit_argument_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv("WORK_ROOT", "/tmp/env-work")
    assert resolve_work_root("/tmp/arg-work") == Path("/tmp/arg-work")


def test_vault_defaults_to_underscore_vault(monkeypatch) -> None:
    monkeypatch.setenv("WORK_ROOT", "/tmp/custom-work")
    paths = resolve_work_paths()
    assert paths.work_root == Path("/tmp/custom-work")
    assert paths.vault_dir == Path("/tmp/custom-work/_vault")


def test_no_hardcoded_username_in_default(monkeypatch) -> None:
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/tmp/whoever")
    assert "/Users/" not in str(resolve_work_root())


# ---------------------------------------------------------- resolve_user_path
#
# 2026-09-14 Air 首启实测：向导里填了 `~用户名`（该用户在这台机器上不存在），
# `Path.expanduser()` 抛 `RuntimeError: Could not determine home directory.`；
# 当时受限 app 只有 422 处理器，异常直接漏出去 → 向导只拿到一个非 JSON 响应 →
# 界面显示成 WebKit 的「The string did not match the expected pattern.」。
# 下面几条锁住「同样的输入必须变成**可读的**错误文案」。


def test_resolve_user_path_expands_tilde_against_the_explicit_home(tmp_path: Path) -> None:
    assert resolve_user_path("~/Documents/Work/_vault", home=tmp_path) == (
        tmp_path / "Documents/Work/_vault"
    )


def test_resolve_user_path_treats_a_bare_tilde_as_the_home(tmp_path: Path) -> None:
    assert resolve_user_path("~", home=tmp_path) == tmp_path


def test_resolve_user_path_leaves_absolute_paths_alone() -> None:
    """绝对路径不以 `~` 开头，`Path.expanduser()` 的守卫直接返回——这也是 Air 上的绕过办法。"""
    assert resolve_user_path("/Users/air/Documents/Work/_vault") == Path(
        "/Users/air/Documents/Work/_vault"
    )


def test_resolve_user_path_reports_an_unknown_tilde_user_instead_of_raising() -> None:
    with pytest.raises(UserPathError) as excinfo:
        resolve_user_path("~nosuchuser/Documents/Work/_vault")
    message = str(excinfo.value)
    assert "nosuchuser" in message
    assert "绝对路径" in message  # 文案必须告诉使用者「怎么办」


def test_resolve_user_path_rejects_blank_input() -> None:
    with pytest.raises(UserPathError):
        resolve_user_path("   ")


def test_resolve_user_path_gives_an_actionable_error_when_no_home_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """$HOME 没有、`Path.home()` 抛错、passwd 也查不到时，同样只能是可读错误。"""
    import pwd

    monkeypatch.delenv("HOME", raising=False)

    def _no_home(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(_no_home))
    monkeypatch.setattr(
        pwd, "getpwuid", lambda _uid: (_ for _ in ()).throw(KeyError("no passwd entry"))
    )

    with pytest.raises(UserPathError, match="绝对路径"):
        resolve_user_path("~/Documents/Work/_vault")
