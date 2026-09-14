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


def test_verify_quotes_accepts_the_real_source_page_shape(tmp_path: Path) -> None:
    """真形状回归：逐字原文之后跟一个 `## 关联` 页尾区块，必须判为合格。

    真库里 `## 关联` 前面**没有** `---` 分隔线，而旧判据只剥「``\\n---\\n\\n## 关联``」，
    于是全库 6 个 `source` 页被集体误报成「在原件后面另加了内容」（2026-09-14 在真库上发现）。
    这条用真形状而非简化 fixture，就是为了让那种口径错误再也不会溜过去。
    """
    original = "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n"
    body = (
        "---\ndate: 2026-09-13\ntype: source\nstatus: active\n"
        "source:\n  kind: doc\n  ref: a.md\n---\n\n"
        "# 原文：原件标题\n\n## 来源\n\n- 原件：a.md\n\n## 要点\n\n- 要点一\n\n"
        "## 原文（逐字，未改写）\n\n"
        "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n"
        "\n## 关联\n\n- [[20260913-analysis|分析笔记]] —— 本页是这篇分析笔记的逐字出处。\n"
    )
    _vault, materials = _vault_with_source(tmp_path, original, body)
    checked, findings = verify._check_verbatim(
        {"hii/sources/20260913-a": body},
        {"hii/sources/20260913-a": {"type": "source", "source": {"ref": "a.md"}}},
        materials,
        0,
        [],
    )
    assert checked == 1 and findings == []


def test_verify_quotes_catches_a_block_inserted_before_the_association_tail(
    tmp_path: Path,
) -> None:
    """变异验证：在原件与页尾 `## 关联` 之间插一个区块，必须被判为「另加了内容」。

    放行 `## 关联` 之后必须守住的就是这条线：**页尾区块以外**，原件后面不许有东西。
    """
    original = "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n"
    body = (
        "---\ndate: 2026-09-13\ntype: source\nstatus: active\n"
        "source:\n  kind: doc\n  ref: a.md\n---\n\n"
        "## 原文（逐字，未改写）\n\n"
        "# 原件标题\n\n## 一、章节\n\n商标共识规范如下。\n"
        "\n## 编者按\n\n原件里没有这一段。\n"
        "\n## 关联\n\n- [[20260913-analysis|分析笔记]]\n"
    )
    _vault, materials = _vault_with_source(tmp_path, original, body)
    _checked, findings = verify._check_verbatim(
        {"hii/sources/20260913-a": body},
        {"hii/sources/20260913-a": {"type": "source", "source": {"ref": "a.md"}}},
        materials,
        0,
        [],
    )
    assert len(findings) == 1 and "未逐字包含原件" in findings[0].reason


def test_verify_quotes_accepts_an_original_that_ends_with_the_association_heading(
    tmp_path: Path,
) -> None:
    """原件自己最后一个小节就叫 `## 关联`、笔记没有额外页尾区块时，也必须合格。

    这条守住「按标题一刀切掉页尾区块」那种更省事的写法：切在原件内部会把
    合格归档误判成改写（真库里的长原件完全可能自带同名小节）。
    """
    original = "# 原件标题\n\n## 一、章节\n\n正文。\n\n## 关联\n\n原件自带的关系段。\n"
    body = (
        "---\ndate: 2026-09-13\ntype: source\nstatus: active\n"
        "source:\n  kind: doc\n  ref: a.md\n---\n\n"
        "## 原文（逐字，未改写）\n\n"
        "# 原件标题\n\n## 一、章节\n\n正文。\n\n## 关联\n\n原件自带的关系段。\n"
    )
    _vault, materials = _vault_with_source(tmp_path, original, body)
    checked, findings = verify._check_verbatim(
        {"hii/sources/20260913-a": body},
        {"hii/sources/20260913-a": {"type": "source", "source": {"ref": "a.md"}}},
        materials,
        0,
        [],
    )
    assert checked == 1 and findings == []


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


# ---- 决策台账聚合（kb_index_decisions）----

decisions_index = _load("kb_index_decisions")

PAGE_TEMPLATE = """---
id: 2026-09-14-c021
title: 决策台账
area: work
workstream: cross
project: global
type: index
domain: system
status: active
created: 2026-09-14
updated: 2026-09-14
date: 2026-09-14
summary: 跨项目的决策台账。
tags: [index, decisions]
---

# 决策台账

> 本页是跨项目台账。

## 生效中

_（暂无。）_

## 待复核

_（暂无。）_

## 已被替代

_（暂无。）_

## 维护规则

- 一决策一篇。
"""


def _decision_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "_vault"
    (vault / "index").mkdir(parents=True)
    (vault / "decisions").mkdir(parents=True)
    (vault / "index/decisions.md").write_text(PAGE_TEMPLATE, encoding="utf-8")
    return vault


def _decision(vault: Path, stem: str, **meta: object) -> None:
    base: dict[str, object] = {
        "id": "2026-09-14-a900",
        "title": f"决定：{stem}",
        "area": "work",
        "workstream": "hii",
        "project": "hii-affairs",
        "type": "decision",
        "status": "active",
        "decision_status": "effective",
        "decided_on": "2026-03-24",
        "created": "2026-09-14",
        "updated": "2026-09-14",
        "date": "2026-03-24",
        "summary": f"{stem} 的一句话摘要",
    }
    base.update(meta)
    front = "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        if isinstance(value, str)
        else f"{key}: {value}"
        for key, value in base.items()
    )
    path = vault / "decisions" / f"{stem}.md"
    path.write_text(f"---\n{front}\n---\n\n# 决定：{stem}\n\n## 背景\n", encoding="utf-8")


def test_decisions_ledger_reads_yaml_dates(tmp_path: Path) -> None:
    """回归：YAML 会把 `decided_on: 2026-03-24` 解析成 `date` 而不是 `str`。

    第一版 `_text()` 只认 `str`，于是**所有决策都被渲染成「（日期未记）」**——
    台账彻底失去按时间排序与复核能力，而且不会有任何报错。这条测试就是为了钉住它。
    """
    vault = _decision_vault(tmp_path)
    _decision(vault, "20260324-sample-decision")
    page = vault / "index/decisions.md"

    body = decisions_index.render(
        decisions_index._split_frontmatter(page.read_text(encoding="utf-8"))[2],
        decisions_index.collect(vault / "decisions", today="2026-09-14"),
    )
    assert "- 2026-03-24 " in body
    assert "（日期未记）" not in body


def test_decisions_ledger_keeps_page_frontmatter_and_rules(tmp_path: Path) -> None:
    """台账页的 frontmatter（含 id/area/workstream/summary）与「维护规则」不得被脚本抹掉。

    这是与旧 `kb_index_people.py` 的关键差别：那个脚本自造 frontmatter，会把新规范的
    叠加必填字段整段删掉（见 PLAN 的 Phase 5 遗留项）。
    """
    vault = _decision_vault(tmp_path)
    _decision(vault, "20260324-sample-decision")
    assert decisions_index.main(["--vault", str(tmp_path)]) == 0
    text = (vault / "index/decisions.md").read_text(encoding="utf-8")
    for needle in (
        "id: 2026-09-14-c021",
        "area: work",
        "workstream: cross",
        "summary: 跨项目的决策台账。",
    ):
        assert needle in text
    assert "## 维护规则" in text and "- 一决策一篇。" in text
    assert "20260324-sample-decision" in text


def test_decisions_ledger_groups_by_status_and_check_flags_stale(tmp_path: Path) -> None:
    """三组分流 + `--check` 必须能判过期。"""
    vault = _decision_vault(tmp_path)
    _decision(vault, "20260101-effective")
    _decision(vault, "20260102-superseded", decision_status="superseded", status="superseded")
    _decision(vault, "20260103-review", decision_status="under-review")

    # 页面还没重生成 → --check 必须红
    assert decisions_index.main(["--vault", str(tmp_path), "--check"]) == 1
    assert decisions_index.main(["--vault", str(tmp_path), "--today", "2026-09-14"]) == 0

    body = decisions_index._split_frontmatter(
        (vault / "index/decisions.md").read_text(encoding="utf-8")
    )[2]
    effective = body.split("## 生效中", 1)[1].split("## 待复核", 1)[0]
    review = body.split("## 待复核", 1)[1].split("## 已被替代", 1)[0]
    superseded = body.split("## 已被替代", 1)[1]
    assert "20260101-effective" in effective and "20260103-review" not in effective
    assert "20260103-review" in review
    assert "20260102-superseded" in superseded

    # 重生成后再查一次：必须绿（否则「可再生成」是空话）
    assert decisions_index.main(["--vault", str(tmp_path), "--check", "--today", "2026-09-14"]) == 0
