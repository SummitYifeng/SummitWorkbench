"""检索度量脚本（`scripts/kb_measure.py`）的判据测试。

这个脚本本身是「调参前先量一遍」这条铁律的**执行工具**，所以它自己的判据必须被锁住：
度量悄悄变松，比检索变差更危险——那时人会拿着一个虚高的数字去改权重。

两条最关键的锁定：
1. 「同篇但块不同」**不能**算命中（算了会让 44% 立刻虚高）；
2. `CASES` 的形状（4 问 × 4 块 = 16，其中证据层 4 / 答案层 12）不能变，
   否则与 PLAN §12 记录的历史数字不可比。
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


measure = _load("kb_measure")


# ------------------------------------------------------------------ 分档判据


def test_grade_block_counts_an_exact_anchor_as_a_hit_with_its_rank() -> None:
    anchors = ["a#一", "b#二", "c#三"]
    assert measure.grade_block("b#二", anchors) == (measure.GRADE_HIT, 2)


def test_grade_block_does_not_count_a_same_note_different_block_as_a_hit() -> None:
    """**这条是度量不许放松的关键守卫。**

    「同篇但块不同」如果算命中，二值口径立刻虚高（本机那次度量的分档是
    命中 7 / 同篇不同块 3，一旦算命中就变成 10/16），
    而历史数字（基线 4/16 = 25% → 改造后 6–7/16 = 38–44%）就全部不可比了。
    """
    anchors = ["b#二", "b#三"]
    assert measure.grade_block("b#一", anchors) == (measure.GRADE_SAME_NOTE, None)


def test_grade_block_reports_miss_when_not_even_the_note_is_recalled() -> None:
    assert measure.grade_block("b#二", ["a#一", "c#三"]) == (measure.GRADE_MISS, None)


def test_grade_block_rank_is_one_based_and_uses_the_first_occurrence() -> None:
    assert measure.grade_block("a#一", ["a#一", "a#一"]) == (measure.GRADE_HIT, 1)


def test_grade_block_on_empty_candidates_is_a_miss() -> None:
    assert measure.grade_block("a#一", []) == (measure.GRADE_MISS, None)


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("hii/sources/overview#六、正式名称", "evidence"),
        ("hii/notes/analysis#关键结论", "answer"),
        ("decisions/x#决定", "answer"),
    ],
)
def test_classify_layer_matches_the_historical_split(anchor: str, expected: str) -> None:
    assert measure.classify_layer(anchor) == expected


# ------------------------------------------------------------------ 权重覆盖


def test_parse_weight_overrides_accepts_float_and_int_fields() -> None:
    parsed = measure.parse_weight_overrides(["topic_step=0", "conclusion_boost=3.25"])
    assert parsed == {"topic_step": 0.0, "conclusion_boost": 3.25}
    # 覆盖结果必须真的能构造出 Weights（字段名漂移会在这里炸）
    weights = measure.Weights(**parsed)
    assert weights.topic_step == 0.0


def test_parse_weight_overrides_casts_integer_fields_to_int() -> None:
    parsed = measure.parse_weight_overrides(["max_chunks_per_note=5"])
    assert parsed["max_chunks_per_note"] == 5
    assert isinstance(parsed["max_chunks_per_note"], int)
    assert measure.Weights(**parsed).max_chunks_per_note == 5


def test_parse_weight_overrides_rejects_a_fractional_integer_field() -> None:
    with pytest.raises(ValueError, match="需要整数"):
        measure.parse_weight_overrides(["max_chunks_per_note=2.5"])


def test_parse_weight_overrides_rejects_an_unknown_field() -> None:
    """拼错的字段名如果被静默忽略，实验就会「看起来量过了」其实没生效。"""
    with pytest.raises(ValueError, match="未知权重字段"):
        measure.parse_weight_overrides(["topic_steps=0.4"])


def test_parse_weight_overrides_rejects_a_non_numeric_value() -> None:
    with pytest.raises(ValueError, match="不是数字"):
        measure.parse_weight_overrides(["topic_step=大一点"])


def test_parse_weight_overrides_rejects_a_malformed_pair() -> None:
    with pytest.raises(ValueError, match="key=value"):
        measure.parse_weight_overrides(["topic_step"])


# ------------------------------------------------------------------ CASES 形状


def test_cases_shape_is_frozen_so_historical_numbers_stay_comparable() -> None:
    """4 问 × 4 期望块 = 16；证据层 4 / 答案层 12。

    这三个数字一改，PLAN §12 里记录的「4/16 = 25%」「6–7/16 = 38–44%」就不再可比，
    所以刻意把它们锁在这里——要扩清单就得同时说明历史数字怎么对齐。
    """
    assert len(measure.CASES) == 4
    assert all(len(case.expected) == 4 for case in measure.CASES)
    flat = [anchor for case in measure.CASES for anchor in case.expected]
    assert len(flat) == 16
    assert sum(1 for anchor in flat if measure.classify_layer(anchor) == "evidence") == 4
    assert sum(1 for anchor in flat if measure.classify_layer(anchor) == "answer") == 12


def test_every_expected_anchor_is_block_level() -> None:
    """期望必须精确到块——裸路径会让「命中」退化成「整篇进来了」。"""
    for case in measure.CASES:
        for anchor in case.expected:
            assert "#" in anchor, f"{case.name} 的期望不是块级：{anchor}"


def test_default_limit_is_the_historical_value() -> None:
    assert measure.DEFAULT_LIMIT == 16


# ------------------------------------------------------------------ 锚点自检


@pytest.fixture()
def index(tmp_path: Path) -> KnowledgeIndex:
    vault = tmp_path / "vault"

    def note(rel: str, body: str, **front: object) -> None:
        meta: dict[str, object] = {"date": "2026-09-13", "type": "note", "status": "active"}
        meta.update(front)
        lines = "\n".join(f"{key}: {value}" for key, value in meta.items())
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{lines}\n---\n\n{body}\n", encoding="utf-8")

    note(
        "hii/notes/analysis.md",
        "# 分析\n\n## 关键结论\n\n登记在 HII。\n\n## 背景\n\n历史原因。\n",
    )
    note("hii/sources/overview.md", "# 原文\n\n## 六、正式名称\n\n登记在 HII。\n", type="source")

    with KnowledgeIndex(vault, tmp_path / "kb.sqlite") as built:
        built.build()
    return KnowledgeIndex(vault, tmp_path / "kb.sqlite")


def test_anchor_resolves_accepts_an_existing_note_and_block(index: KnowledgeIndex) -> None:
    assert measure.anchor_resolves(index, "hii/notes/analysis#关键结论") is True


def test_anchor_resolves_accepts_a_bare_note_path_as_a_whole_note_reference(
    index: KnowledgeIndex,
) -> None:
    assert measure.anchor_resolves(index, "hii/notes/analysis") is True


def test_anchor_resolves_rejects_a_missing_block(index: KnowledgeIndex) -> None:
    """块改名了而期望没跟着改——这正是「度量坏了」，必须能自检出来。"""
    assert measure.anchor_resolves(index, "hii/notes/analysis#早已改名的区块") is False


def test_anchor_resolves_rejects_a_missing_note(index: KnowledgeIndex) -> None:
    assert measure.anchor_resolves(index, "hii/notes/不存在#关键结论") is False


# ------------------------------------------------------------------ 汇总输出


def test_print_grades_reports_the_rank_line_and_counts_unresolved(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """排名行是**比二值更细的读数**，实测 `--set conclusion_boost=1.0` 时只有它会动。

    没有这一行，那类「档位没翻转但在变差」的改动在度量上完全不可见。
    """
    grades = [
        measure.Grade("a#一", measure.GRADE_HIT, 3, "answer", True),
        measure.Grade("b#二", measure.GRADE_SAME_NOTE, None, "answer", True),
        measure.Grade("c#三", measure.GRADE_MISS, None, "evidence", False),
    ]

    unresolved = measure._print_grades(grades)

    out = capsys.readouterr().out
    assert unresolved == 1  # 有一条期望锚点解析不了 → 调用方据此非零退出
    assert "#3" in out  # 命中排名被打印
    assert "解析不了：c#三" in out
