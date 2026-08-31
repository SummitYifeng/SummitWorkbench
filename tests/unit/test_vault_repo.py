"""frontmatter 解析与 check_vault 集成测试。"""

from __future__ import annotations

from summit_workbench.repositories.vault import check_vault, iter_markdown_files, parse_frontmatter


def test_parse_frontmatter_ok():
    text = (
        "---\ndate: 2026-08-30\ntype: inbox\nstatus: active\nproject: global\n---\n\n# Hi\nbody\n"
    )
    meta, body, error = parse_frontmatter(text)
    assert error is None
    assert meta["type"] == "inbox"
    assert body.startswith("# Hi")


def test_parse_frontmatter_missing():
    meta, body, error = parse_frontmatter("# no frontmatter\n")
    assert meta == {}
    assert error is not None


def test_parse_frontmatter_unclosed():
    meta, body, error = parse_frontmatter("---\ndate: 2026-08-30\n")
    assert error is not None and "未闭合" in error


def test_parse_frontmatter_bad_yaml():
    meta, body, error = parse_frontmatter("---\n: : :\n bad\n---\nbody\n")
    assert error is not None


def test_check_vault_flags_bad_and_skips_signals(tmp_path):
    good = tmp_path / "inbox.md"
    good.write_text(
        "---\ndate: 2026-08-30\ntype: inbox\nstatus: active\nproject: global\n---\n\n# ok\n",
        encoding="utf-8",
    )
    bad = tmp_path / "projects" / "p.md"
    bad.parent.mkdir()
    bad.write_text(
        "---\ndate: 2026-08-30\ntype: project-main\nstatus: active\nproject: P\n---\n\n# x\n",
        encoding="utf-8",
    )
    # _signals 下的 json/md 不应被校验
    sig = tmp_path / "_signals" / "note.md"
    sig.parent.mkdir()
    sig.write_text("no frontmatter here\n", encoding="utf-8")

    results = check_vault(tmp_path)
    assert good not in results
    assert bad in results  # 缺固定区块
    assert sig not in results  # _signals 被跳过

    files = list(iter_markdown_files(tmp_path))
    assert good in files and bad in files and sig not in files
