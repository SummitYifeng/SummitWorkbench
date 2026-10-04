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

from summit_workbench.repositories._atomic import atomic_write_bytes, atomic_write_text

_WRITE_CASES = [
    pytest.param(atomic_write_text, "data", id="text"),
    pytest.param(atomic_write_bytes, b"data", id="bytes"),
]


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_writes_content(tmp_path, writer, payload):
    path = tmp_path / "a.txt"
    value = "你好 🌍" if isinstance(payload, str) else "你好 🌍".encode()
    writer(path, value)
    assert path.read_bytes() == "你好 🌍".encode()


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_overwrites_existing(tmp_path, writer, payload):
    path = tmp_path / "a.txt"
    path.write_text("old", encoding="utf-8")
    value = "new" if isinstance(payload, str) else b"new"
    writer(path, value)
    assert path.read_bytes() == b"new"


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_no_tmp_left_behind(tmp_path, writer, payload):
    path = tmp_path / "note.md"
    writer(path, payload)
    assert not (tmp_path / "note.md.tmp").exists()
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_ensure_parents_creates_dirs(tmp_path, writer, payload):
    path = tmp_path / "deep" / "nested" / "f.json"
    writer(path, payload, ensure_parents=True)
    assert path.read_bytes() == (payload if isinstance(payload, bytes) else payload.encode("utf-8"))


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_missing_parent_without_ensure_raises(tmp_path, writer, payload):
    path = tmp_path / "missing" / "f.txt"
    try:
        writer(path, payload)
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


@pytest.mark.parametrize(
    ("writer", "payload_type"),
    [(atomic_write_text, str), (atomic_write_bytes, bytes)],
    ids=["text", "bytes"],
)
def test_concurrent_writers_never_splice_or_truncate(tmp_path, writer, payload_type):
    """两个并发 atomic writer 不共用临时路径；最终文件是任一完整版本而非拼接/半截。"""
    target = tmp_path / "shared.txt"
    payloads = [f"writer-{i}:" + ("x" * 200_000) for i in range(6)]
    values = [payload if payload_type is str else payload.encode("utf-8") for payload in payloads]
    errors: list[BaseException] = []

    def write_many(payload: str | bytes) -> None:
        try:
            for _ in range(20):
                writer(target, payload)
        except BaseException as exc:  # noqa: BLE001 - 测试线程内收集后主线程重抛
            errors.append(exc)

    threads = [threading.Thread(target=write_many, args=(payload,)) for payload in values]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), "并发写入线程超时未结束"
    if errors:
        raise errors[0]
    assert target.read_bytes() in [payload.encode("utf-8") for payload in payloads]
    assert [p.name for p in tmp_path.iterdir()] == ["shared.txt"]


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_replace_failure_keeps_original_and_cleans_only_own_temp(
    tmp_path, monkeypatch, writer, payload
):
    """os.replace 失败：原文件完整，只清理本次临时文件，不动其他进程的临时文件。"""
    target = tmp_path / "f.txt"
    target.write_text("original", encoding="utf-8")
    foreign = tmp_path / ".f.txt.otherprocess.tmp"  # 另一进程遗留
    foreign.write_text("other", encoding="utf-8")

    def boom(src: str, dst: str) -> None:
        raise OSError("模拟 replace 失败")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        writer(target, payload)
    assert target.read_text(encoding="utf-8") == "original"
    # 目录里只剩原文件与“别的进程”的临时文件：本次临时文件已清理
    assert sorted(p.name for p in tmp_path.iterdir()) == [".f.txt.otherprocess.tmp", "f.txt"]


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_fsync_failure_cleans_temp_and_keeps_original(tmp_path, monkeypatch, writer, payload):
    """写入 fsync 抛错：原文件完整，本次临时文件被清理，无残留。"""
    target = tmp_path / "f.txt"
    target.write_text("original", encoding="utf-8")

    def boom(_fd: int) -> None:
        raise OSError("模拟 fsync 失败")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        writer(target, payload)
    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["f.txt"]


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_mock_fsync_verifies_file_then_dir_durability(tmp_path, monkeypatch, writer, payload):
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

    writer(target, payload)

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


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_replace_preserves_existing_file_mode(tmp_path, writer, payload):
    """替换已有文件时尽量保留原 mode（含可执行位）。"""
    target = tmp_path / "f.sh"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, 0o751)
    writer(target, payload)
    assert target.read_bytes() == (
        payload if isinstance(payload, bytes) else payload.encode("utf-8")
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o751


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_new_file_uses_ordinary_create_mode_not_mkstemp_0600(tmp_path, writer, payload):
    """新建文件沿用普通创建语义（0666 & ~umask），不因唯一临时文件变成 0600。"""
    target = tmp_path / "fresh.txt"
    writer(target, payload)
    old_umask = os.umask(0)
    os.umask(old_umask)
    assert stat.S_IMODE(target.stat().st_mode) == (0o666 & ~old_umask)


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_new_mode_applies_only_to_new_file(tmp_path, writer, payload):
    target = tmp_path / "private.bin"
    writer(target, payload, new_mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    os.chmod(target, 0o640)
    writer(target, payload, new_mode=0o777)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.parametrize(("writer", "payload"), _WRITE_CASES)
def test_cleanup_removes_own_temp_before_replace_error_knows_path(
    tmp_path, monkeypatch, writer, payload
):
    """失败清理的是本次创建的临时文件：用目录前后快照证明本次临时文件消失。"""
    target = tmp_path / "g.txt"
    target.write_text("old", encoding="utf-8")

    def boom(_src: str, _dst: str) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        writer(target, payload)
    # 原文件仍在且内容未变；无任何隐藏临时残留（_atomic 实现的本次 temp 名以 .g.txt. 开头）
    assert target.read_text(encoding="utf-8") == "old"
    for p in tmp_path.iterdir():
        assert not p.name.startswith(".g.txt."), f"本次临时文件未清理：{p.name}"


@pytest.mark.parametrize(
    ("writer", "payload"),
    [
        pytest.param(atomic_write_text, "标题\n- 你好 🌍\nline\r\n末尾", id="text"),
        pytest.param(atomic_write_bytes, "标题\n- 你好 🌍\nline\r\n末尾".encode(), id="bytes"),
    ],
)
def test_payload_roundtrip_preserves_exact_bytes(tmp_path, writer, payload):
    """文本与字节路径都原样保存 UTF-8、CRLF、换行与 emoji。"""
    target = tmp_path / "data.md"
    writer(target, payload)
    expected = payload.encode("utf-8") if isinstance(payload, str) else payload
    assert target.read_bytes() == expected
