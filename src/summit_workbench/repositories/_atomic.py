"""单文件原子落盘：写唯一临时文件、fsync、``os.replace``、fsync 父目录。

**根治的故障类**：直接 ``path.write_text(...)`` 覆盖写不是原子的——进程在写到一半时
被 kill / 断电，会留下一个 **半截文件**，把原本完好的持久状态（笔记 frontmatter、
错误队列、通知去重表……）损坏成不可解析。先写旁挂的唯一临时文件（与目标**同一目录**，
``os.replace`` 的同目录换名才是原子的），完整刷盘后再换名覆盖，读者要么看到旧全量、
要么看到新全量，绝无半截中间态。

耐久性（P0-06）：
- 临时文件名含随机串（``.`` + 目标名 + ``.<hex>.tmp``），并发写者各写各的临时文件，
  绝不共用固定 ``.tmp`` 名；两个并发 atomic writer 最终文件是任一完整版本，不是拼接/半截。
- 写入完成后 ``flush + fsync(file)``，再 ``os.replace``；replace 后在支持的平台
  ``fsync(parent directory)``，把“目录项落盘”也刷下去（断电后不丢新文件名）。
- 替换已有文件时尽量保留原文件 mode；新建文件沿用普通创建语义（``0666 & ~umask``），
  不因唯一临时文件退化成 mkstemp 的 0600。
- 任何异常路径只清理**本次**临时文件，绝不删除其他进程的临时文件。

此前八个仓库各自手写这段 ``with_name(+".tmp") → write_text → replace``，逐字重复；
统一到一处，行为不变（NFR-3 非破坏性），是 LHF #2 容错读在写侧的对称补位。
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

_TEMP_SUFFIX = ".tmp"
_TEMP_ATTEMPTS = 100


def _existing_mode(path: Path) -> int | None:
    """目标已存在时取其权限位；不存在（或 stat 失败）返回 None。"""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def _open_unique_temp(path: Path) -> tuple[int, Path]:
    """在目标同目录创建一个**唯一**临时文件（``O_CREAT|O_EXCL``），返回 (fd, 路径)。

    随机名 + ``O_EXCL``：并发写者不会撞到同一临时路径；创建时沿用 ``0666 & ~umask``，
    与普通文件创建语义一致。理论上的命名冲突用有限次重试后放弃。
    """
    parent = path.parent
    for _ in range(_TEMP_ATTEMPTS):
        candidate = parent / f".{path.name}.{secrets.token_hex(8)}{_TEMP_SUFFIX}"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            return fd, candidate
        except FileExistsError:
            continue
    raise FileExistsError(f"无法为目标 {path} 创建唯一临时文件（多次命名冲突）")


def _fsync_directory(directory: Path) -> None:
    """replace 后刷父目录目录项；平台/文件系统不支持时静默跳过。

    macOS/Linux 上可对以只读打开的目录 fd 调 ``fsync``；部分文件系统（如某些网络盘）
    会抛 ``OSError``，此时放弃目录 fsync（文件本身已刷盘，耐久性尽力而为）。
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)


def _atomic_write_payload(
    path: Path,
    payload: str | bytes,
    *,
    ensure_parents: bool = False,
    new_mode: int | None = None,
) -> None:
    """执行文本与字节写入共用的原子落盘流程。"""
    if ensure_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    mode = _existing_mode(path)
    fd, temporary = _open_unique_temp(path)
    try:
        with os.fdopen(fd, "wb") as handle:
            if mode is not None:
                os.fchmod(handle.fileno(), mode)
            elif new_mode is not None:
                os.fchmod(handle.fileno(), new_mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        # 只清理本次创建的临时文件；异常（含 replace/fsync 失败）时原文件保持完整。
        # fd 由 fdopen 的 with 块负责关闭，这里绝不再 os.close（避免误关复用 fd 的并发线程）。
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    ensure_parents: bool = False,
    new_mode: int | None = None,
) -> None:
    """把 ``text`` 原子写入 ``path``（UTF-8）：唯一临时文件 + fsync + replace + 目录 fsync。

    :param ensure_parents: 为真时先 ``mkdir(parents=True)`` 建好父目录。默认 False——
        调用方若已保证父目录存在（如「就地改写既有文件」）则无需重复建。
    :param new_mode: 仅当目标**不存在**（新建）时生效的权限位（如本机 0600 文件，
        P0-07）；目标已存在时一律保留原 mode，忽略本参数。
    """
    _atomic_write_payload(
        path,
        text,
        ensure_parents=ensure_parents,
        new_mode=new_mode,
    )


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    ensure_parents: bool = False,
    new_mode: int | None = None,
) -> None:
    """把二进制内容以同样的唯一临时文件 + fsync + replace 语义落盘。"""
    _atomic_write_payload(
        path,
        data,
        ensure_parents=ensure_parents,
        new_mode=new_mode,
    )
