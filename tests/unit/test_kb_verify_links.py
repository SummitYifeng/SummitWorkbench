"""Regression tests for vault link and anchor verification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kb_verify_links", ROOT / "scripts" / "kb_verify_links.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
