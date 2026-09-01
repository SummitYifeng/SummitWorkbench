"""工作区级跨进程咨询锁（LHF #1）。

**根治的故障类**：本项目有多个互不知情的写入触发源——``launchd`` 的
brief/weekly 定时任务、手动 CLI、Web 面板「一键触发」。它们会并发地

1. 轮换飞书 ``refresh_token`` 并回写 Keychain（read-modify-write，飞书单次轮换，
   旧 token 立即作废）；两进程同时进入这段会互相作废对方的 token，把 Keychain
   里存成一个死 token，逼出人肉重新授权。
2. 对 ``_vault`` 仓库跑 ``fetch → ff-merge → push`` / ``add → commit`` 序列；
   这些序列跨多条 git 命令，git 自身的 ``index.lock`` 保护不了「读状态→决策→写」
   的窗口。

对策：给「所有会改动共享持久状态的临界区」加一道 **工作区级** 总闸。锁文件固定在
``<work_root>/.wb.lock``，用 ``fcntl.flock`` 做独占咨询锁（macOS 原生，零新增依赖）。

设计要点：

- **全局单锁**：默认锁在 :func:`resolve_work_root` 解析出的 work_root，无论哪个
  临界区获取，序列化的都是「整个 wb 进程的写动作」——单用户本地工具下这是正确粒度。
- **按线程重入**：``flock`` 的锁与 *打开文件描述* 绑定，同一进程用不同 fd 再次
  ``LOCK_EX`` 会自锁死。真实调用链存在同线程嵌套（Web endpoint → run_brief →
  ``access_token``），故用 **线程内** 重入计数：同线程已持有则直接放行，不再真正
  flock；而 uvicorn 里 *不同线程* 的并发请求各自 ``open`` 独立 fd，仍会在内核层
  互斥，从而被正确串行化。
- **带超时**：``launchd`` 任务不能无限挂起。默认阻塞等待有限时长，超时抛
  :class:`LockBusy`，由调用方转成可见状态而非静默卡死。
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from summit_workbench.config.paths import resolve_work_root

_LOCK_FILENAME = ".wb.lock"
_DEFAULT_TIMEOUT = 60.0  # 等待另一 wb 进程释放锁的上限（秒）
_POLL_INTERVAL = 0.1

# 线程内重入状态：{(thread_id, 锁文件绝对路径): (fd, 持有深度)}。由 _GUARD 保护。
_HELD: dict[tuple[int, str], tuple[int, int]] = {}
_GUARD = threading.Lock()


class LockBusy(RuntimeError):
    """在超时时间内未能取得工作区锁（另一 wb 任务正持有）。"""


def _lock_key(work_root: Path | None) -> str:
    root = work_root if work_root is not None else resolve_work_root()
    # 不依赖文件是否存在：expanduser + absolute + normpath 得到稳定的规范键。
    path = (root / _LOCK_FILENAME).expanduser()
    return os.path.normpath(str(path if path.is_absolute() else path.absolute()))


def _acquire(fd: int, timeout: float | None, sleep: Callable[[float], None]) -> None:
    """在 ``timeout`` 内取得 ``LOCK_EX``；超时抛 :class:`LockBusy`。

    ``timeout is None`` 无限阻塞（用 flock 阻塞模式，最省 CPU）；
    ``timeout == 0`` 只试一次；``>0`` 非阻塞轮询到超时。
    """
    if timeout is None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise LockBusy("另一个 wb 任务正持有工作区锁，本次未获取") from None
            sleep(_POLL_INTERVAL)


@contextmanager
def workspace_lock(
    work_root: Path | None = None,
    *,
    timeout: float | None = _DEFAULT_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[None]:
    """获取工作区独占锁的上下文管理器。

    :param work_root: 锁归属的工作根；``None`` 时取 :func:`resolve_work_root`。
    :param timeout: 等待上限（秒）。``None`` 无限等待；``0`` 只试一次；``>0`` 轮询到超时。
        超时抛 :class:`LockBusy`。
    :param sleep: 轮询用休眠函数，便于测试注入。

    同一 **线程** 已持有该锁时直接放行（重入计数 +1），避免 flock 自锁死。
    """
    lock_id = _lock_key(work_root)
    key = (threading.get_ident(), lock_id)

    # 同线程已持有 → 重入，不再真正 flock。
    with _GUARD:
        held = _HELD.get(key)
        if held is not None:
            _HELD[key] = (held[0], held[1] + 1)
            reentered = True
        else:
            reentered = False

    if reentered:
        try:
            yield
        finally:
            with _GUARD:
                fd, depth = _HELD[key]
                if depth <= 1:
                    del _HELD[key]
                else:
                    _HELD[key] = (fd, depth - 1)
        return

    lock_file = Path(lock_id)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _acquire(fd, timeout, sleep)
    except BaseException:
        os.close(fd)
        raise

    with _GUARD:
        _HELD[key] = (fd, 1)
    try:
        yield
    finally:
        with _GUARD:
            entry = _HELD[key]
            release = entry[1] <= 1
            if release:
                del _HELD[key]
            else:
                _HELD[key] = (entry[0], entry[1] - 1)
        if release:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
