"""`scripts/kb_acceptance.py` 的判定逻辑。

这个脚本是「第二大脑答得对不对」的裁决者，它自己的判据改过几轮，而**此前没有单测**——
最严重的一轮是「摘要冒充证据层」：会议笔记（`type: meeting-note`）曾和逐字稿一起被算作
「追溯到了证据」，于是「笔记 → 会议笔记」这条链就能让验收通过，看起来走到了证据，
其实停在派生摘要上，摘要里的内容是不是原件说的根本没有被校验。

这些断言把裁决者的判据钉死：证据层只认 `meeting-transcript` 与 `source`。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from summit_workbench.repositories.kb_index import KnowledgeIndex

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


acceptance = _load("kb_acceptance")


def _note(vault: Path, rel: str, body: str, **front: object) -> Path:
    meta: dict[str, object] = {"date": "2026-09-13", "type": "note", "status": "active"}
    meta.update(front)
    lines = "\n".join(f"{key}: {value}" for key, value in meta.items())
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{lines}\n---\n\n{body}\n", encoding="utf-8")
    return path


@pytest.fixture()
def index(tmp_path: Path) -> KnowledgeIndex:
    vault = tmp_path / "vault"
    _note(
        vault,
        "hii/notes/analysis.md",
        "# 分析笔记\n\n## 商标共识规范\n\n所有商标登记在 HII 名下。\n\n"
        "## 证据索引\n\n- 原文：[[overview|原文]]\n- 会议：[[meeting|会议笔记]]\n",
        workstream="hii",
        aliases="[商标共识]",
    )
    _note(
        vault,
        "hii/sources/overview.md",
        "# 原文：总结\n\n## 六、正式名称\n\n所有商标登记在 HII 名下。\n",
        type="source",
        workstream="hii",
    )
    _note(
        vault,
        "meetings/notes/meeting.md",
        "# 对齐会\n\n## 一分钟摘要\n\n商标口径已确认。\n\n"
        "## 证据索引\n\n- 逐字稿：[[transcript|逐字稿]]\n",
        type="meeting-note",
        workstream="hii",
    )
    _note(
        vault,
        "meetings/transcripts/transcript.md",
        "# 2026-09-07 会议逐字稿\n\n00:02 罗艺峰：商标登记在 HII。\n",
        type="meeting-transcript",
        workstream="hii",
        status="archived",
    )
    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as built:
        built.build()
    return KnowledgeIndex(vault, tmp_path / "kb.sqlite")


def _case(**over: object) -> object:
    base: dict[str, object] = {
        "name": "T",
        "question": "q",
        "expect_route": "decision",
        "must_recall": "hii/notes/analysis",
    }
    base.update(over)
    return acceptance.Case(**base)


# --------------------------------------------------------------- 证据层判据


def test_meeting_note_does_not_count_as_evidence(index: KnowledgeIndex) -> None:
    """回归 2026-09-13 的踩坑：摘要（会议笔记）不得冒充证据层。"""
    chains, transcripts = acceptance.evidence_chains(index, ("meetings/notes/meeting",))
    # 会议笔记只链到逐字稿，而逐字稿是证据层——所以这里拿到的是「会议室→逐字稿」。
    assert all(not chain.endswith("meetings/notes/meeting") for chain in chains)
    assert "meetings/notes/meeting → meetings/transcripts/transcript" in chains
    assert "meetings/notes/meeting → meetings/transcripts/transcript" in transcripts


def test_source_counts_as_evidence_and_transcript_is_separated(index: KnowledgeIndex) -> None:
    chains, transcripts = acceptance.evidence_chains(index, ("hii/notes/analysis",))
    assert "hii/notes/analysis → hii/sources/overview" in chains
    assert "hii/notes/analysis → meetings/transcripts/transcript" in chains
    # source 是证据层但不是逐字稿：不能混进 transcripts（否则「走到逐字稿」会被原文冒充）
    assert "hii/notes/analysis → hii/sources/overview" not in transcripts
    assert set(transcripts) < set(chains)


def test_evidence_types_exclude_derived_summaries() -> None:
    assert acceptance.EVIDENCE_TYPES == {"meeting-transcript", "source"}
    assert "meeting-note" not in acceptance.EVIDENCE_TYPES


# --------------------------------------------------------------- audit_case


def test_audit_passes_on_a_good_observation(index: KnowledgeIndex) -> None:
    observation = acceptance.Observation(
        route="decision",
        anchors=("hii/notes/analysis#商标共识规范",),
        fused=("hii/notes/analysis",),
    )
    assert acceptance.audit_case(_case(), observation, index) == []


def test_audit_flags_wrong_route(index: KnowledgeIndex) -> None:
    observation = acceptance.Observation(
        route="point", anchors=("hii/notes/analysis#商标共识规范",)
    )
    failures = acceptance.audit_case(_case(), observation, index)
    assert any("路由 point != 期望 decision" in item for item in failures)


def test_audit_flags_missing_key_evidence(index: KnowledgeIndex) -> None:
    observation = acceptance.Observation(
        route="decision", anchors=("hii/sources/overview#六、正式名称",)
    )
    failures = acceptance.audit_case(
        _case(must_recall="hii/notes/does-not-exist"), observation, index
    )
    assert any("未召回关键证据" in item for item in failures)


def test_audit_flags_a_fabricated_anchor(index: KnowledgeIndex) -> None:
    """模型编一个不存在的区块名 → 必须红，这是防止「引用看起来对」的关键一条。"""
    observation = acceptance.Observation(
        route="decision",
        anchors=("hii/notes/analysis#根本不存在的区块", "hii/notes/ghost#结论"),
    )
    failures = acceptance.audit_case(_case(), observation, index)
    assert any("区块不存在" in item for item in failures)
    assert any("笔记不存在" in item for item in failures)


def test_audit_requires_a_block_level_anchor(index: KnowledgeIndex) -> None:
    """只引用整篇（无 `#区块`）不算通过：答案必须能定位到节。"""
    observation = acceptance.Observation(route="decision", anchors=("hii/notes/analysis",))
    failures = acceptance.audit_case(_case(), observation, index)
    assert any("没有任何块级" in item for item in failures)


def test_audit_requires_an_evidence_chain(index: KnowledgeIndex) -> None:
    """引用了一篇走不到证据层的笔记 → 必须红。"""
    _note(index.vault_dir, "hii/notes/orphan.md", "# 孤儿笔记\n\n## 结论\n\n无任何双链。\n")
    index.build()
    observation = acceptance.Observation(
        route="decision", anchors=("hii/notes/orphan#结论",), fused=("hii/notes/analysis",)
    )
    failures = acceptance.audit_case(_case(), observation, index)
    assert any("走到证据层" in item for item in failures)


def test_audit_requires_a_transcript_when_the_material_has_one(index: KnowledgeIndex) -> None:
    """材料里有逐字稿时，只停在 `source` 原文不算通过。"""
    observation = acceptance.Observation(
        route="decision", anchors=("hii/sources/overview#六、正式名称",)
    )
    failures = acceptance.audit_case(_case(expect_transcript=True), observation, index)
    assert any("没有走到逐字稿" in item for item in failures)


# --------------------------------------------------------------- 清单本身


def test_case_list_covers_the_three_priority_scenarios() -> None:
    routes = {case.expect_route for case in acceptance.CASES}
    assert {"retrospect", "decision", "review"} <= routes
    assert len(acceptance.CASES) >= 6


def test_only_the_two_acceptance_questions_call_the_model() -> None:
    """扩充回归清单不能悄悄把 token 成本也扩了。"""
    model_cases = [case for case in acceptance.CASES if case.use_model]
    assert len(model_cases) == 2
    assert [case.name for case in model_cases] == [
        "Q1 商标共识规范（决策）",
        "Q2 IT 进度与下一阶段（点查）",
    ]


# --------------------------------------------------------------- 已安装 App 的口径
# `scripts/kb_acceptance_installed.py` 通过**装到 /Applications 之后的** App 自己的服务发问。
# 它必须用与 Swift 侧 `RuntimeRecord.candidateURLs` 相同的候选集合找 runtime record——
# 只查 `profiles/**` 会让打包 App（记录写在 app_support 根）永远找不到（同一类错误让
# `install-macos-app.sh` 误报过 readiness 失败）。


def _installed_module() -> ModuleType:
    return _load("kb_acceptance_installed")


def test_installed_harness_finds_the_record_at_the_app_support_root(tmp_path: Path) -> None:
    module = _installed_module()
    root = tmp_path / "SummitWorkbench"
    root.mkdir()
    (root / "runtime.json").write_text("{}", encoding="utf-8")
    assert module.runtime_records(root) == [root / "runtime.json"]


def test_installed_harness_finds_the_record_under_profiles(tmp_path: Path) -> None:
    module = _installed_module()
    root = tmp_path / "SummitWorkbench"
    record = root / "profiles" / "ws-1" / "runtime" / "runtime.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}", encoding="utf-8")
    assert module.runtime_records(root) == [record]


def test_installed_harness_returns_both_locations_with_root_first(tmp_path: Path) -> None:
    module = _installed_module()
    root = tmp_path / "SummitWorkbench"
    (root / "profiles" / "ws-1" / "runtime").mkdir(parents=True)
    (root / "runtime.json").write_text("{}", encoding="utf-8")
    (root / "profiles" / "ws-1" / "runtime" / "runtime.json").write_text("{}", encoding="utf-8")
    found = module.runtime_records(root)
    assert found[0] == root / "runtime.json"
    assert root / "profiles" / "ws-1" / "runtime" / "runtime.json" in found
