"""工作区锁（LHF #1）单元测试。

覆盖：正常获取/释放、跨「打开文件描述」的真实互斥、同线程重入不自锁、
跨线程互斥、以及超时语义（立即失败 / 等待后获得 / 超时抛错）。
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from pathlib import Path

import pytest

from summit_workbench.config.locking import LockBusy, workspace_lock


def _lockfile(root: Path) -> Path:
    return root / ".wb.lock"


def test_acquire_creates_lockfile_and_releases(tmp_path: Path) -> None:
    with workspace_lock(tmp_path, timeout=0):
        assert _lockfile(tmp_path).is_file()
    # 释放后应能立即以非阻塞方式再次获取。
    with workspace_lock(tmp_path, timeout=0):
        pass


def test_busy_when_held_by_another_open_description(tmp_path: Path) -> None:
    """外部持有者（独立 fd）持锁时，非阻塞获取应抛 LockBusy。"""
    path = _lockfile(tmp_path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(LockBusy):
            with workspace_lock(tmp_path, timeout=0):
                pass
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    # 外部释放后应恢复可获取。
    with workspace_lock(tmp_path, timeout=0):
        pass


def test_same_thread_reentrant_does_not_deadlock(tmp_path: Path) -> None:
    """同线程嵌套获取（endpoint → runner → access_token 场景）不得自锁死。"""
    with workspace_lock(tmp_path, timeout=0):
        with workspace_lock(tmp_path, timeout=0):  # 若非重入，flock 会阻塞/失败
            assert _lockfile(tmp_path).is_file()


def test_reentrant_inner_exit_keeps_lock_until_outer_exit(tmp_path: Path) -> None:
    """内层退出不得提前释放；只有最外层退出才真正解锁。"""
    path = _lockfile(tmp_path)
    with workspace_lock(tmp_path, timeout=0):
        with workspace_lock(tmp_path, timeout=0):
            pass
        # 内层已退出，但外层仍持有：另一 fd 仍应被挡住。
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)


def test_cross_thread_mutual_exclusion(tmp_path: Path) -> None:
    """不同线程各自独立 fd，必须真正互斥（覆盖 uvicorn 并发请求）。"""
    acquired = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with workspace_lock(tmp_path, timeout=0):
            acquired.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert acquired.wait(timeout=5)
        with pytest.raises(LockBusy):
            with workspace_lock(tmp_path, timeout=0):
                pass
    finally:
        release.set()
        t.join(timeout=5)
    # 持有线程退出后应恢复可获取。
    with workspace_lock(tmp_path, timeout=0):
        pass


def test_blocking_acquire_after_holder_releases(tmp_path: Path) -> None:
    """带正超时的获取：持有者短暂占用后释放，等待方应成功获得。"""
    release_after = 0.2
    holding = threading.Event()

    def holder() -> None:
        with workspace_lock(tmp_path, timeout=0):
            holding.set()
            time.sleep(release_after)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert holding.wait(timeout=5)
        start = time.monotonic()
        with workspace_lock(tmp_path, timeout=5):
            waited = time.monotonic() - start
        assert waited >= release_after - 0.05  # 确实等到对方释放才拿到
    finally:
        t.join(timeout=5)


def test_timeout_raises_when_never_released(tmp_path: Path) -> None:
    """超时窗口内始终无法获取应抛 LockBusy，而非无限挂起。"""
    path = _lockfile(tmp_path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        start = time.monotonic()
        with pytest.raises(LockBusy):
            with workspace_lock(tmp_path, timeout=0.3):
                pass
        assert time.monotonic() - start >= 0.3
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_default_work_root_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """work_root 省略时锁落在 resolve_work_root()（WORK_ROOT 环境变量）。"""
    monkeypatch.setenv("WORK_ROOT", str(tmp_path))
    with workspace_lock(timeout=0):
        assert _lockfile(tmp_path).is_file()
