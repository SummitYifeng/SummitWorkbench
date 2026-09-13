"""入库脚本与逐字校验脚本的测试。

两个脚本都是「会真的写进使用者核心资产」的工具，因此它们的失败模式必须能被判定：

- `kb_intake.py`：幂等（重复入库不产生重复笔记）、内容去重（同内容不同文件名）、
  脏数据（同 ref 不同内容）必须**停下来报冲突**而不是覆盖；
- `kb_verify_quotes.py`：编造的逐字引用、以及归档时被改写/截断的正文，都必须被抓出来。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


intake = _load("kb_intake")
verify = _load("kb_verify_quotes")


def _material(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return target


def _entry(src: str, target: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "src": src,
        "target": target,
        "note_type": "source",
        "date": "2026-09-13",
        "title": "原文：样例",
        "workstream": "hii",
        "domain": "demo",
        "kind": "doc",
        "summary": "样例材料",
        "points": ["要点一"],
    }
    base.update(extra)
    return base


def _run(
    monkeypatch: pytest.MonkeyPatch, vault: Path, materials: Path, manifest: Path, *extra: str
):
    argv = [
        "kb_intake.py",
        "--vault",
        str(vault),
        "--manifest",
        str(manifest),
        "--materials-root",
        str(materials),
        *extra,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return intake.main()


def test_intake_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault, materials = tmp_path / "vault", tmp_path / "materials"
    vault.mkdir()
    _material(materials, "a.md", "# 原件标题\n\n## 一、章节\n\n正文。\n")
    manifest = _manifest(tmp_path, [_entry("a.md", "hii/sources/20260913-a.md")])

    assert _run(monkeypatch, vault, materials, manifest) == 0
    written = vault / "hii/sources/20260913-a.md"
    first = written.read_text(encoding="utf-8")
    assert "# 原件标题" in first
    # 标题降一级：原件的 `## 一、章节` 变成笔记里的 `### 一、章节`
    assert "### 一、章节" in first

    assert _run(monkeypatch, vault, materials, manifest) == 0
    assert written.read_text(encoding="utf-8") == first  # 幂等：内容一字不变


def test_intake_skips_byte_identical_duplicate_with_a_different_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """两份内容完全相同、文件名不同的材料（实测遇到过）不得入库两次。"""
    vault, materials = tmp_path / "vault", tmp_path / "materials"
    vault.mkdir()
    _material(materials, "one.md", "# 同一份内容\n\n正文。\n")
    _material(materials, "two.md", "# 同一份内容\n\n正文。\n")
    manifest = _manifest(
        tmp_path,
        [
            _entry("one.md", "hii/sources/20260913-one.md"),
            _entry("two.md", "hii/sources/20260913-two.md"),
        ],
    )
    assert _run(monkeypatch, vault, materials, manifest) == 0
    assert (vault / "hii/sources/20260913-one.md").is_file()
    assert not (vault / "hii/sources/20260913-two.md").exists()
    assert "完全相同" in capsys.readouterr().out


def test_intake_stops_on_dirty_data_instead_of_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同 ref 但内容变了：既不覆盖也不新建，退出码 2，交给人工决定。"""
    vault, materials = tmp_path / "vault", tmp_path / "materials"
    vault.mkdir()
    _material(materials, "a.md", "# 原件\n\n初版。\n")
    manifest = _manifest(tmp_path, [_entry("a.md", "hii/sources/20260913-a.md")])
    assert _run(monkeypatch, vault, materials, manifest) == 0
    before = (vault / "hii/sources/20260913-a.md").read_text(encoding="utf-8")

    _material(materials, "a.md", "# 原件\n\n被人改过。\n")
    changed = _manifest(tmp_path, [_entry("a.md", "hii/sources/20260913-other.md")])
    assert _run(monkeypatch, vault, materials, changed) == 2
    assert (vault / "hii/sources/20260913-a.md").read_text(encoding="utf-8") == before
    assert not (vault / "hii/sources/20260913-other.md").exists()


def _vault_with_source(tmp_path: Path, original_text: str, note_body: str) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    materials = tmp_path / "materials"
    source = vault / "hii/sources/20260913-a.md"
    source.parent.mkdir(parents=True)
    source.write_text(note_body, encoding="utf-8")
    _material(materials, "a.md", original_text)
    return vault, materials


def test_verify_quotes_passes_on_faithful_archive(tmp_path: Path) -> None:
    body = (
        "---\ndate: 2026-09-13\ntype: source\nstatus: active\nworkstream: hii\n"
        "source:\n  kind: doc\n  ref: a.md\n---\n\n"
        "## 来源\n\n- 原件：a.md\n\n## 要点\n\n- 要点一\n\n"
        "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n"
    )
    vault, materials = _vault_with_source(
        tmp_path, "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n", body
    )
    checked, findings = verify._check_verbatim(
        {"hii/sources/20260913-a": body},
        {"hii/sources/20260913-a": {"type": "source", "source": {"ref": "a.md"}}},
        materials,
        0,
        [],
    )
    assert checked == 1 and findings == []
    assert vault.is_dir()


def test_verify_quotes_catches_a_rewritten_archive(tmp_path: Path) -> None:
    """变异验证：在归档正文里插一句原件没有的话，必须被判为「未逐字包含原件」。"""
    body = (
        "---\ndate: 2026-09-13\ntype: source\nstatus: active\n"
        "source:\n  kind: doc\n  ref: a.md\n---\n\n"
        "## 来源\n\nx\n\n## 要点\n\ny\n\n"
        "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n\n附：原件其实没有这句。\n"
    )
    _vault, materials = _vault_with_source(
        tmp_path, "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n", body
    )
    _checked, findings = verify._check_verbatim(
        {"hii/sources/20260913-a": body},
        {"hii/sources/20260913-a": {"type": "source", "source": {"ref": "a.md"}}},
        materials,
        0,
        [],
    )
    assert len(findings) == 1 and "未逐字包含原件" in findings[0].reason


def test_verify_quotes_cli_flags_a_fabricated_quote(tmp_path: Path) -> None:
    """端到端跑脚本：编造的「逐字引用」必须让它以退出码 1 结束并点名那条引用。"""
    source = "# 原件\n\n## 一、章节\n\n原文只说了这一句。\n"
    note = (
        "---\ndate: 2026-09-13\ntype: note\nstatus: active\n"
        "source:\n  kind: doc\n  ref: hii/sources/20260913-a.md\n---\n\n"
        "# 派生笔记\n\n## 来源\n\n> 原文说的其实是完全不同的一句。\n"
    )
    vault = tmp_path / "vault"
    (vault / "hii/notes").mkdir(parents=True)
    (vault / "hii/sources").mkdir(parents=True)
    (vault / "hii/sources/20260913-a.md").write_text(source, encoding="utf-8")
    (vault / "hii/notes/n.md").write_text(note, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/kb_verify_quotes.py"), "--vault", str(vault)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "来源中找不到该逐字引用" in result.stdout
