"""原子写测试：临时文件不残留、父目录按需创建、覆盖既有内容。"""

from __future__ import annotations

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
