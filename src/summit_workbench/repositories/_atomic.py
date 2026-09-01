"""单文件原子落盘：写临时文件再 ``os.replace`` 换名（同一目录内换名是原子的）。

**根治的故障类**：直接 ``path.write_text(...)`` 覆盖写不是原子的——进程在写到一半时
被 kill / 断电，会留下一个 **半截文件**，把原本完好的持久状态（笔记 frontmatter、
错误队列、通知去重表……）损坏成不可解析。先写旁挂的 ``<name>.tmp`` 再 ``replace`` 换名，
读者要么看到旧全量、要么看到新全量，绝无半截中间态。

此前八个仓库各自手写这段 ``with_name(+".tmp") → write_text → replace``，逐字重复；
统一到一处，行为不变（NFR-3 非破坏性），是 LHF #2 容错读在写侧的对称补位。
"""

from __future__ import annotations

from pathlib import Path


def atomic_write_text(path: Path, text: str, *, ensure_parents: bool = False) -> None:
    """把 ``text`` 原子写入 ``path``（UTF-8）：写 ``<name>.tmp`` 再换名覆盖。

    :param ensure_parents: 为真时先 ``mkdir(parents=True)`` 建好父目录。默认 False——
        调用方若已保证父目录存在（如「就地改写既有文件」）则无需重复建。
    """
    if ensure_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
