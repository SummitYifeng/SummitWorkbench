"""原子写测试：临时文件不残留、父目录按需创建、覆盖既有内容。

P0-06 追加：目标同目录唯一临时文件（无固定 ``.tmp`` 名）、并发写者不产生拼接/半截、
replace 失败后原文件完整且只清理本次临时文件、mock ``fsync`` 验证文件与目录耐久步骤、
替换时保留原文件 mode、新文件沿用普通创建语义（umask）。
"""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path

import pytest

from summit_workbench.repositories._atomic import atomic_write_text


def test_writes_content(tmp_path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "你好")
    assert path.read_text(encoding="utf-8") == "你好"


def test_overwrites_existing(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("old", encoding="utf-8")
    atomic_write_text(path, "new")
    assert path.read_text(encoding="utf-8") == "new"


def test_no_tmp_left_behind(tmp_path):
    path = tmp_path / "note.md"
    atomic_write_text(path, "x")
    assert not (tmp_path / "note.md.tmp").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_ensure_parents_creates_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "f.json"
    atomic_write_text(path, "{}", ensure_parents=True)
    assert path.read_text(encoding="utf-8") == "{}"


def test_missing_parent_without_ensure_raises(tmp_path):
    path = tmp_path / "missing" / "f.txt"
    try:
        atomic_write_text(path, "x")
    except (FileNotFoundError, OSError):
        return
    raise AssertionError("父目录不存在且未 ensure_parents 时应抛错")


# ---- P0-06：目标同目录唯一临时文件 + 耐久性 + mode + 异常清理 ----


def test_temp_name_is_unique_and_never_fixed(tmp_path):
    """临时文件名含随机部分：两次写不留任何 ``.tmp`` 固定名残留。"""
    path = tmp_path / "note.md"
    atomic_write_text(path, "v1")
    atomic_write_text(path, "v2")
    assert path.read_text(encoding="utf-8") == "v2"
    assert not (tmp_path / "note.md.tmp").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["note.md"]


def test_concurrent_writers_never_splice_or_truncate(tmp_path):
    """两个并发 atomic writer 不共用临时路径；最终文件是任一完整版本而非拼接/半截。"""
    target = tmp_path / "shared.txt"
    payloads = [f"writer-{i}:" + ("x" * 200_000) for i in range(6)]
    errors: list[BaseException] = []

    def writer(payload: str) -> None:
        try:
            for _ in range(20):
                atomic_write_text(target, payload)
        except BaseException as exc:  # noqa: BLE001 - 测试线程内收集后主线程重抛
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), "并发写入线程超时未结束"
    if errors:
        raise errors[0]
    assert target.read_text(encoding="utf-8") in payloads
    assert [p.name for p in tmp_path.iterdir()] == ["shared.txt"]


def test_replace_failure_keeps_original_and_cleans_only_own_temp(tmp_path, monkeypatch):
    """os.replace 失败：原文件完整，只清理本次临时文件，不动其他进程的临时文件。"""
    target = tmp_path / "f.txt"
    target.write_text("original", encoding="utf-8")
    foreign = tmp_path / ".f.txt.otherprocess.tmp"  # 另一进程遗留
    foreign.write_text("other", encoding="utf-8")

    def boom(src: str, dst: str) -> None:
        raise OSError("模拟 replace 失败")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "original"
    # 目录里只剩原文件与“别的进程”的临时文件：本次临时文件已清理
    assert sorted(p.name for p in tmp_path.iterdir()) == [".f.txt.otherprocess.tmp", "f.txt"]


def test_fsync_failure_cleans_temp_and_keeps_original(tmp_path, monkeypatch):
    """写入 fsync 抛错：原文件完整，本次临时文件被清理，无残留。"""
    target = tmp_path / "f.txt"
    target.write_text("original", encoding="utf-8")

    def boom(_fd: int) -> None:
        raise OSError("模拟 fsync 失败")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


def test_mock_fsync_verifies_file_then_dir_durability(tmp_path, monkeypatch):
    """mock fsync：写临时文件后先 fsync(file)，os.replace 后 fsync(parent directory)。"""
    target = tmp_path / "a.txt"
    events: list[tuple[str, str]] = []  # (step, path)
    fd_to_path: dict[int, str] = {}
    real_open = os.open
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        fd_to_path[fd] = os.fspath(path)
        return fd

    def spy_fsync(fd: int) -> None:
        events.append(("fsync", fd_to_path.get(fd, "?")))
        real_fsync(fd)

    def spy_replace(src: str, dst: str) -> None:
        events.append(("replace", os.fspath(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)

    atomic_write_text(target, "data")

    fsyncs = [(step, path) for step, path in events if step == "fsync"]
    replaces = [(step, path) for step, path in events if step == "replace"]
    assert len(fsyncs) == 2, f"应恰好 fsync(file)+fsync(dir)，实际 {events}"
    assert len(replaces) == 1

    # 文件 fsync：目标同目录内唯一临时文件，发生在 replace 之前
    tmp_path_str = str(tmp_path)
    assert fsyncs[0][1] != tmp_path_str
    assert Path(fsyncs[0][1]).parent == tmp_path
    assert Path(fsyncs[0][1]).name.startswith(".a.txt.")  # 同目录唯一临时文件
    assert events.index(("fsync", fsyncs[0][1])) < events.index(("replace", replaces[0][1]))
    # 目录 fsync：replace 之后对父目录执行
    assert fsyncs[1][1] == tmp_path_str
    assert events.index(("fsync", fsyncs[1][1])) > events.index(("replace", replaces[0][1]))
    # 写入内容正确
    assert target.read_text(encoding="utf-8") == "data"


def test_replace_preserves_existing_file_mode(tmp_path):
    """替换已有文件时尽量保留原 mode（含可执行位）。"""
    target = tmp_path / "f.sh"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, 0o751)
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o751


def test_new_file_uses_ordinary_create_mode_not_mkstemp_0600(tmp_path):
    """新建文件沿用普通创建语义（0666 & ~umask），不因唯一临时文件变成 0600。"""
    target = tmp_path / "fresh.txt"
    atomic_write_text(target, "x")
    old_umask = os.umask(0)
    os.umask(old_umask)
    assert stat.S_IMODE(target.stat().st_mode) == (0o666 & ~old_umask)


def test_cleanup_removes_own_temp_before_replace_error_knows_path(tmp_path, monkeypatch):
    """失败清理的是本次创建的临时文件：用目录前后快照证明本次临时文件消失。"""
    target = tmp_path / "g.txt"
    target.write_text("old", encoding="utf-8")

    def boom(_src: str, _dst: str) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "x")
    # 原文件仍在且内容未变；无任何隐藏临时残留（_atomic 实现的本次 temp 名以 .g.txt. 开头）
    assert target.read_text(encoding="utf-8") == "old"
    for p in tmp_path.iterdir():
        assert not p.name.startswith(".g.txt."), f"本次临时文件未清理：{p.name}"


def test_write_bytes_roundtrip_with_crlf_and_emoji(tmp_path):
    """UTF-8 文本（含换行/emoji/中文）完整往返，不因临时文件编码损坏。"""
    target = tmp_path / "data.md"
    text = "标题\n- 你好 🌍\nline\r\n末尾"
    atomic_write_text(target, text)
    # 逐字节比对：避免 Path.read_text 的通用换行归一化（\r\n → \n）
    assert target.read_bytes().decode("utf-8") == text
