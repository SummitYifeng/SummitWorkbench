"""Regression tests for vault link and anchor verification."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    """按**源码**执行脚本，绕过 `__pycache__`。

    为什么不用 `spec.loader.exec_module`：它走 `cache_from_source` 的字节码缓存，
    而 pyc 头里的源 mtime 只有 1 秒粒度——**同秒内等长改动**（例如 `fail` ↔ `warn`）
    会命中过期 pyc，变异验证就会得出错误结论（2026-09-19 实测踩到）。
    """
    path = ROOT / "scripts" / "kb_verify_links.py"
    module = ModuleType("kb_verify_links")
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


verify = _load()


def _write(vault: Path, rel: str, body: str) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _run(vault: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    result = verify.main([str(vault)])
    return result, capsys.readouterr().out


def test_h2_path_reference_passes_but_h3_path_reference_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sources/rules.md", "# Rules\n\n## H2\ntext\n\n### H3\ntext\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n`# H2`\n\n`sources/rules.md#H2`\n\n`sources/rules.md#H3`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 1
    assert "rules.md#H3" in output
    assert "rules.md#H2" not in output


def test_wikilink_to_h3_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "sources/rules.md", "# Rules\n\n## H2\ntext\n\n### H3\ntext\n")
    _write(tmp_path, "notes/n.md", "# Note\n\n[[sources/rules#H3]]\n")
    result, output = _run(tmp_path, capsys)
    assert result == 1
    assert "[[sources/rules#H3]]" in output


def test_unique_source_context_resolves_bare_anchor_and_bad_anchor_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sources/rules.md", "# Rules\n\n## H2\ntext\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n来源：`sources/rules.md`\n\n`# H2`\n`# Missing`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 1
    assert "Missing" in output
    assert "# H2" not in output


def test_multiple_source_contexts_are_reported_ambiguous(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "sources/a.md", "# A\n\n## Same\n")
    _write(tmp_path, "sources/b.md", "# B\n\n## Same\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n来源：`sources/a.md`；另一个来源：`sources/b.md`\n\n`# Same`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 1
    assert "来源上下文有歧义" in output


def test_bare_tags_without_source_and_fenced_examples_are_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "notes/n.md", "# Note\n\n`#ignore` `#项目名`\n\n```\n`# Missing`\n```\n")
    result, output = _run(tmp_path, capsys)
    assert result == 0
    assert "裸锚点" in output


# ───────── 2026-09-19 覆盖回归：来源推断必须扫过"首块只剩 H1"的形态 ─────────


def test_source_marker_in_second_block_still_resolves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """回归守卫：来源标记行在**第二个块**（第一个 `##` 区块）里也必须能推断出来。

    第五阶段把 H1 之前的前言并进第一个 `##` 后，`chunks[0]` 只剩 H1；旧实现只看首块，
    于是两页来源推不出来、裸锚点计数 56 → 0（静默不再校验）。本测试钉住放宽后的行为。
    变异验证：把 `source_context` 改回"只看 `chunks[0]`"，本用例立刻变红。
    """
    _write(tmp_path, "sources/rules.md", "# Rules\n\n## H2\ntext\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n## 一页版结论\n\n来源：`sources/rules.md`\n\n`# H2`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 0
    assert "裸锚点 1 条" in output


def test_source_marker_in_a_later_block_still_resolves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """来源只在更靠后的区块里被提到（全篇唯一）时，也要能推断出来。"""
    _write(tmp_path, "sources/rules.md", "# Rules\n\n## H2\ntext\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n## 甲\n\n正文。\n\n## 乙\n\n来源：`sources/rules.md`\n\n`# H2`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 0
    assert "裸锚点 1 条" in output


def test_page_is_not_its_own_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`source` 页的「vault 内副本」是自指，不得被当成本页的来源上下文。

    变异验证：去掉"排除本页自身"的过滤，本用例会把裸锚点算到本页上并报失效锚点（变红）。
    """
    _write(
        tmp_path,
        "sources/rules.md",
        "# Rules\n\n## 来源\n\n"
        "- **原件**：`/Users/someone/Desktop/Original Copy - source-rules-v9.md`\n"
        "- **vault 内副本**：`sources/rules.md`\n\n"
        "## 要点\n\n`# Missing`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 0
    assert "裸锚点 0 条" in output
    assert "Missing" not in output


def test_multiple_sources_narrow_to_the_opening_declaration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """全篇多个来源时，用开头区块声明的那个（`结论层出处` 惯例），不误报歧义。"""
    _write(tmp_path, "sources/a.md", "# A\n\n## Same\n")
    _write(tmp_path, "sources/b.md", "# B\n\n## Other\n")
    _write(
        tmp_path,
        "notes/n.md",
        "# Note\n\n## 现在在哪\n\n> 结论层出处：`sources/a.md`\n\n"
        "## 下一步\n\n出处：`sources/b.md`\n\n`# Same`\n",
    )
    result, output = _run(tmp_path, capsys)
    assert result == 0
    assert "裸锚点 1 条" in output
