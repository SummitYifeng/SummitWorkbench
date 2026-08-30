"""路径解析测试。重点：不硬编码用户名，尊重 WORK_ROOT，默认派生正确。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.config.paths import resolve_work_paths, resolve_work_root


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
    assert paths.vault_dir == Path("/tmp/custom-work/_vault")
    assert paths.projects_dir == Path("/tmp/custom-work/_vault/projects")
    assert paths.inbox_file == Path("/tmp/custom-work/_vault/inbox.md")


def test_no_hardcoded_username_in_default(monkeypatch) -> None:
    monkeypatch.delenv("WORK_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/tmp/whoever")
    assert "/Users/" not in str(resolve_work_root())
