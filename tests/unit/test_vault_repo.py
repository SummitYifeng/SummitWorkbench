"""frontmatter 解析与 check_vault 集成测试。"""

from __future__ import annotations

from datetime import date, datetime

from summit_workbench.repositories.vault import (
    check_vault,
    iter_markdown_files,
    load_note,
    meta_date_iso,
    parse_frontmatter,
)


def test_meta_date_iso_normalizes_forms():
    # YAML 会把未加引号的 2026-09-03 解析成 date 对象；加引号保留 str。两者应归一到同一串。
    assert meta_date_iso("2026-09-03") == "2026-09-03"
    assert meta_date_iso(" 2026-09-03 ") == "2026-09-03"
    assert meta_date_iso(date(2026, 9, 3)) == "2026-09-03"
    assert meta_date_iso(datetime(2026, 9, 3, 8, 30)) == "2026-09-03"
    assert meta_date_iso(None) is None
    assert meta_date_iso("不是日期") is None
    assert meta_date_iso(20260903) is None


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


def test_templates_dir_is_skipped_by_check_and_iter(tmp_path):
    """库内 `templates/` 是骨架模板，占位符 frontmatter 既不该被校验也不该被索引。

    模板里的 `date: {{date}}` 过不了 `YYYY-MM-DD` 校验；若不过滤，`wb vault check` 会在
    任何带模板的库上变红，检索也会把骨架当成知识笔记召回（变异验证：把 `templates` 从
    `repositories/ignore.py` 的 `MACHINE_DIRNAMES` 移除，本用例必须变红）。
    """
    tpl = tmp_path / "templates" / "note-template.md"
    tpl.parent.mkdir()
    tpl.write_text(
        "---\ndate: {{date}}\ntype: note\nstatus: active\n---\n\n# {{title}}\n",
        encoding="utf-8",
    )
    real = tmp_path / "index" / "projects.md"
    real.parent.mkdir()
    real.write_text(
        "---\ndate: 2026-09-13\ntype: index\nstatus: active\nproject: global\n---\n\n# 项目索引\n",
        encoding="utf-8",
    )

    results = check_vault(tmp_path)
    assert tpl not in results  # 模板不参与 schema 校验
    assert real not in results

    files = list(iter_markdown_files(tmp_path))
    assert real in files and tpl not in files


def test_load_note_reports_non_utf8_instead_of_raising(tmp_path):
    """非 UTF-8 文件（例如误放进 vault 的二进制）必须走 parse_error 通道。

    2026-09-11 真实浏览器验收发现：二进制来源会让 ``load_note`` 抛出 UnicodeDecodeError，
    审批来源面板因此显示 500 的兜底文案「服务内部错误」，而不是明确的不可读提示。
    """
    binary = tmp_path / "projects" / "binary.md"
    binary.parent.mkdir()
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff\xfe binary payload")

    note = load_note(binary)
    assert note.parse_error is not None
    assert note.meta == {}
    assert note.body == ""

    # 批量校验应把它汇总成一条问题，而不是让整次扫描崩溃。
    results = check_vault(tmp_path)
    assert binary in results


def test_check_vault_flags_duplicate_citable_heading(tmp_path):
    """检索就绪契约已进 `wb vault check`：重复的 ## 标题必须被标出。

    变异验证：把 ``check_vault`` 里的 ``validate_retrieval_readiness`` 调用删掉，
    本用例必须变红（只有 vault schema 检查时，重复 H2 不会被发现）。
    """
    page = tmp_path / "notes" / "dup.md"
    page.parent.mkdir()
    page.write_text(
        "---\ndate: 2026-09-14\ntype: note\nstatus: active\n---\n\n"
        "# 主题\n\n## 关键结论\n\na\n\n## 关键结论\n\nb\n",
        encoding="utf-8",
    )
    results = check_vault(tmp_path)
    assert page in results
    assert any("检索就绪" in str(issue) for issue in results[page])


def test_check_vault_ignores_duplicate_headings_in_evidence_layer(tmp_path):
    """逐字稿里的重复 `##` 是原件内容，不进检索就绪结构判定之外的约束。

    证据层不可变：`wb vault check` 不因逐字稿正文里的 Markdown 形态而变红。
    """
    page = tmp_path / "meetings" / "transcripts" / "t.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ndate: 2026-09-14\ntype: meeting-transcript\nstatus: archived\n"
        "projects: [P]\n---\n\n# 逐字稿\n\n## 说话人\n\n原文，未改写。\n",
        encoding="utf-8",
    )
    assert check_vault(tmp_path) == {}
