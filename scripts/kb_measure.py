#!/usr/bin/env python3
"""检索度量：**动权重/词表之前先用它量一遍**。

为什么要有这个脚本：铁律是「涉及检索权重/词表的改动必须先用真实问题量一遍再决定」——
历史上有两次凭直觉的改动（BM25 ``b=0.35``、CJK 2-gram 补词）实测有害（块级命中 44%→31%）被回退。
但这条铁律此前依赖 ``/tmp/phase5/measure.py``：重启即失、不受版本控制、不受门禁保护，
等于**无法执行**。本脚本把它收进仓库，并补上「到底在量什么」的分档口径。

度量对象固定为使用者的 4 个验收问题 × 每个 4 个期望答案块 = **16 项**，
与 Phase 5 的历史数字同口径（基线 4/16 = 25% → 改造后 6–7/16 = 38–44%）。

三层口径，前两层零 token：

1. **二值命中（历史口径，判据与打印格式都不许改）**：期望块是否进了模型实际会看到的候选
   （``limit``）。改这一行会让它与 PLAN §12 记录的历史数字不可比。
2. **分档（本轮新增）**：把「没命中」再拆开——``命中 #k`` / ``同篇但块不同`` / ``未召回``。
   二值指标把这个区别抹掉了，而它正是「该调权重」还是「该改分块 / 主题通道」的分水岭。
   同时自检**期望锚点自身是否仍可解析**：那种「度量坏了」比「检索坏了」更危险，
   所以任何一项不可解析都以非零退出。
3. **召回 → 引用（``--with-model``，花 token）**：真调模型问一遍，看答案**有没有真的引用**
   期望块。与第 1 层的区别：第 1 层问「它进没进上下文」，这一层问「模型有没有用它」。
   「进了上下文但没被引用」和「根本没进上下文」要采取完全不同的修法。

权重实验**不需要改代码**：``--set topic_step=0`` 会直接覆盖 :class:`Weights` 的字段，
所以每次实验都可复现、可记录（未知字段 / 坏数值一律报错，不静默忽略）。

用法：

    .venv/bin/python scripts/kb_measure.py                        # 零 token：分档 + 二值
    .venv/bin/python scripts/kb_measure.py --no-rebuild
    .venv/bin/python scripts/kb_measure.py --project hii-affairs
    .venv/bin/python scripts/kb_measure.py --set topic_step=0 --set conclusion_boost=2.0
    .venv/bin/python scripts/kb_measure.py --with-model --only "Q3"

退出码：0 = 度量本身自检通过；1 = 有期望锚点解析不了（**度量坏了，先修度量**）；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from summit_workbench.config.profiles import resolve_active_workspace  # noqa: E402
from summit_workbench.config.secrets import resolve_credential  # noqa: E402
from summit_workbench.prompts import load_prompt  # noqa: E402
from summit_workbench.providers.llm import load_model_config  # noqa: E402
from summit_workbench.repositories.kb_index import KnowledgeIndex, default_index_path  # noqa: E402
from summit_workbench.workflows.ask.ask import answer_question  # noqa: E402
from summit_workbench.workflows.ask.fusion import Weights  # noqa: E402
from summit_workbench.workflows.ask.retrieval import build_index, retrieve_via_index  # noqa: E402

#: 模型实际会看到的候选条数。**不要改**——历史数字都建立在这个值上。
DEFAULT_LIMIT = 16

GRADE_HIT = "命中"
GRADE_SAME_NOTE = "同篇但块不同"
GRADE_MISS = "未召回"


@dataclass(frozen=True)
class MeasureCase:
    name: str
    question: str
    #: 期望的**答案块**（`路径#区块`）。每条都是「这一问应该落到哪一块」的人工判定。
    expected: tuple[str, ...]


CASES: tuple[MeasureCase, ...] = (
    MeasureCase(
        name="Q1 商标共识规范",
        question="根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？",
        expected=(
            "hii/clusters/ip-trademark#关键结论",
            "decisions/20260623-hii-registration-entity#决定",
            "hii/notes/20260912-hii-hic-ip-analysis"
            "#结论八｜正式登记主体统一为 Hoffman Institute International, Inc."
            "（含中英文名称与地址）",
            "hii/sources/20260912-hii-hic-ip-overview#六、正式名称、登记主体与关键命名口径",
        ),
    ),
    MeasureCase(
        name="Q2 Danny 来华待收口",
        question="Danny 来华目前还差哪些必须收口？下一步谁做什么？",
        expected=(
            "hii/visits/danny-kim-2026-09#未决问题",
            "hii/visits/danny-kim-2026-09#关键结论",
            "hii/clusters/relationships#关键结论",
            "hii/sources/20260913-hic-hii-current-visits#4. Danny｜当前已确认与待确认",
        ),
    ),
    MeasureCase(
        name="Q3 IT 进度与下一阶段",
        question="IT 当前的开发进度是什么，下一个阶段该怎么做？",
        expected=(
            "it/notes/20260912-hic-it-roadmap-analysis"
            "#一句话回答：IT 当前的开发进度是什么，下一个阶段该怎么做",
            "it/notes/20260912-hic-it-roadmap-analysis#2026 总体优先级与 9—12 月 Roadmap",
            "it/clusters/enrollment#关键结论",
            "it/sources/20260912-hic-it-roadmap-progress#二十七、2026 年 9 月—12 月建议 Roadmap",
        ),
    ),
    MeasureCase(
        name="Q4 活满 vs 和夫曼",
        question="「活满」与「和夫曼之旅」为什么分开管理？当时还有哪些选项？",
        expected=(
            "decisions/20260912-huoman-separate-from-hefuman#选项",
            "decisions/20260912-huoman-separate-from-hefuman#决定",
            "hii/notes/20260912-hii-hic-ip-analysis#结论五｜「活满」未来有三种真实候选路径（A/B/C），方向尚未决定",
            "hii/sources/20260912-hii-hic-ip-overview#4.2 「活满」",
        ),
    ),
)


@dataclass(frozen=True)
class Grade:
    """一个期望块的分档结果。"""

    expected: str
    grade: str
    rank: int | None  # 命中时的 1-based 排名；其余为 None
    layer: str  # "answer" / "evidence"
    resolvable: bool


def grade_block(expected: str, anchors: Sequence[str]) -> tuple[str, int | None]:
    """把期望块判成 命中 / 同篇但块不同 / 未召回。

    判定只看锚点字符串：**精确相等才算命中**。「同篇但块不同」是另一个档，不能算命中——
    否则二值口径会被悄悄放松，历史数字立刻不可比。
    """
    if expected in anchors:
        return GRADE_HIT, list(anchors).index(expected) + 1
    note = expected.split("#", 1)[0]
    if any(anchor.split("#", 1)[0] == note for anchor in anchors):
        return GRADE_SAME_NOTE, None
    return GRADE_MISS, None


def classify_layer(expected: str) -> str:
    """证据层 / 答案层。与历史口径一致：``source`` 原件的块默认不进上下文，
    与答案层混在一个分母里会低估真实水平（见脚本 docstring 第 1 层）。
    """
    return "evidence" if "/sources/" in expected else "answer"


def parse_weight_overrides(pairs: Iterable[str]) -> dict[str, float | int]:
    """解析 ``--set key=value``；未知字段或坏数值一律抛 ``ValueError``。

    这里刻意**不静默忽略**：一个拼错的字段名如果被忽略，实验会「看起来量过了」其实没生效——
    比报错危险得多。
    """
    unknown_hint = "、".join(sorted(Weights.__dataclass_fields__))
    out: dict[str, float | int] = {}
    for raw in pairs:
        key, sep, value = raw.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"--set 需要 key=value 形式，拿到 {raw!r}")
        if key not in Weights.__dataclass_fields__:
            raise ValueError(f"未知权重字段 {key!r}（可用：{unknown_hint}）")
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{key} 的值不是数字：{value.strip()!r}") from exc
        declared = Weights.__dataclass_fields__[key].type
        if declared is int or declared == "int":
            if not number.is_integer():
                raise ValueError(f"{key} 需要整数，拿到 {value.strip()!r}")
            out[key] = int(number)
        else:
            out[key] = number
    return out


def anchor_resolves(index: KnowledgeIndex, anchor: str) -> bool:
    """期望锚点在索引里是否仍解析得到（笔记在 + 块标题在）。

    只用公开 API（``notes()`` / ``chunk_at()``），不碰索引内部连接。
    没有块标题的裸路径视为可解析——那是「整篇引用」的合法写法。
    """
    source_id, _, heading = anchor.partition("#")
    if source_id not in index.notes():
        return False
    if not heading:
        return True
    return index.chunk_at(source_id, heading) is not None


def _percent(hit: int, total: int) -> str:
    return f"{hit / total:.0%}" if total else "n/a"


def _print_binary_summary(
    label: str,
    *,
    hit_total: int,
    total: int,
    answer_hits: int,
    answer_total: int,
    evidence_hits: int,
    evidence_total: int,
) -> None:
    """历史口径那一行。**格式与判据都不许改**（见脚本 docstring 第 1 层）。"""
    print(
        f"=== 命中率（{label}）：全部 {hit_total}/{total} = {_percent(hit_total, total)}"
        f"｜答案层 {answer_hits}/{answer_total}"
        f"={_percent(answer_hits, answer_total)}"
        f"｜证据层 {evidence_hits}/{evidence_total}（默认不进上下文，问「原文」时才进）==="
    )


def _print_grades(grades: Sequence[Grade]) -> int:
    """打印分档汇总，返回「不可解析的期望锚点」条数。"""
    buckets = {GRADE_HIT: 0, GRADE_SAME_NOTE: 0, GRADE_MISS: 0}
    for grade in grades:
        buckets[grade.grade] += 1
    print()
    print("--- 分档（二值指标抹掉了这个区别）---")
    print(f"  {GRADE_HIT}：{buckets[GRADE_HIT]} 项")
    print(f"  {GRADE_SAME_NOTE}：{buckets[GRADE_SAME_NOTE]} 项  ← 笔记进了上下文、答案块没进")
    print(f"  {GRADE_MISS}：{buckets[GRADE_MISS]} 项  ← 连笔记都没进")
    # 排名分布是**比二值更细的读数**：实测 `--set conclusion_boost=1.0` 时档位一项不变，
    # 只有排名会动。没有这一行，这类改动在度量上完全不可见。
    ranks = sorted(grade.rank for grade in grades if grade.rank is not None)
    if ranks:
        listed = "、".join(f"#{rank}" for rank in ranks)
        print(f"  命中排名：{listed}（均值 {sum(ranks) / len(ranks):.1f}）")
    unresolved = [grade for grade in grades if not grade.resolvable]
    print(f"  期望锚点自检：{len(grades) - len(unresolved)}/{len(grades)} 可解析")
    for grade in unresolved:
        print(f"    ✗ 解析不了：{grade.expected}")
    return len(unresolved)


def main() -> int:
    parser = argparse.ArgumentParser(description="第二大脑检索度量（先量再改）")
    parser.add_argument("--project", default=None, help="按项目过滤（管线页名）。")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="候选条数，默认 16。")
    parser.add_argument("--no-rebuild", action="store_true", help="复用现有索引（扫权重时用）。")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="覆盖 Weights 字段，可重复。例：--set topic_step=0",
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="追加第 3 层：真调模型，量「召回 → 引用」的转化率（花 token）。",
    )
    parser.add_argument("--only", default=None, help="只跑名字里含该子串的题（省 token）。")
    args = parser.parse_args()

    try:
        overrides = parse_weight_overrides(args.overrides)
    except ValueError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    weights = Weights(**overrides) if overrides else None

    active = resolve_active_workspace()
    if active.paths is None or active.config_file is None:
        print("✗ 找不到本机 active workspace（先在 App 里完成连接向导）", file=sys.stderr)
        return 2
    vault_dir = active.paths.vault_dir
    index_path = default_index_path()

    if not args.no_rebuild:
        stats = build_index(vault_dir, index_path, full=True)
        print(f"索引：{stats.summary()}")
    print(f"索引库：{index_path}")
    label = f"project={args.project}" if args.project else "全库"
    if overrides:
        shown = "、".join(f"{k}={v}" for k, v in sorted(overrides.items()))
        print(f"权重覆盖：{shown}")
    print()

    selected = [case for case in CASES if args.only is None or args.only in case.name]
    if not selected:
        print(f"✗ --only {args.only!r} 没匹配到任何题目", file=sys.stderr)
        return 2

    grades: list[Grade] = []
    hit_total = total = 0
    answer_hits = answer_total = evidence_hits = evidence_total = 0
    conversions: list[tuple[str, int, int]] = []

    cfg = api_key = prompt = None
    if args.with_model:
        cfg = load_model_config("qa", active.config_file, workspace_id=active.workspace_id)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
        assert api_key is not None and prompt is not None

    with KnowledgeIndex(vault_dir, index_path) as index:
        index.build()
        for case in selected:
            candidates, trace = retrieve_via_index(
                vault_dir,
                case.question,
                index_path=index_path,
                project=args.project,
                limit=args.limit,
                weights=weights,
            )
            anchors = [candidate.source_id for candidate in candidates]
            print(f"【{case.name}】{case.question}")
            print(
                f"  路由：{trace.route}（{trace.route_reason}）"
                f"｜命中块 {trace.hits}｜返回 {len(anchors)}"
            )
            for rank, anchor in enumerate(anchors, start=1):
                mark = "★" if anchor in case.expected else " "
                print(f"   {mark}{rank:>2}. {anchor}")
            for expected in case.expected:
                total += 1
                grade, rank = grade_block(expected, anchors)
                hit = grade == GRADE_HIT
                hit_total += 1 if hit else 0
                layer = classify_layer(expected)
                if layer == "evidence":
                    evidence_total += 1
                    evidence_hits += 1 if hit else 0
                else:
                    answer_total += 1
                    answer_hits += 1 if hit else 0
                grades.append(
                    Grade(
                        expected=expected,
                        grade=grade,
                        rank=rank,
                        layer=layer,
                        resolvable=anchor_resolves(index, expected),
                    )
                )
                where = f"命中 #{rank}" if hit else grade
                print(f"    {'✓' if hit else '✗'} {expected.split('/')[-1]} → {where}")
            if trace.expanded:
                print(f"  双链扩展：{'；'.join(f'{a} ← {b}' for a, b in trace.expanded[:4])}")
            print()

            if args.with_model:
                result = answer_question(
                    vault_dir,
                    case.question,
                    cfg,
                    api_key,
                    prompt=prompt,
                    index_path=index_path,
                )
                cited = tuple(fact.source_id for fact in result.answer.facts)
                in_context = sum(
                    1
                    for expected in case.expected
                    if grade_block(expected, anchors)[0] == GRADE_HIT
                )
                used = sum(
                    1 for expected in case.expected if grade_block(expected, cited)[0] == GRADE_HIT
                )
                conversions.append((case.name, in_context, used))
                print(
                    f"  ↳ 模型层：进上下文 {in_context}/{len(case.expected)}"
                    f"｜被引用 {used}/{len(case.expected)}"
                    f"｜unanswerable={result.answer.unanswerable}"
                )
                print()

    _print_binary_summary(
        label,
        hit_total=hit_total,
        total=total,
        answer_hits=answer_hits,
        answer_total=answer_total,
        evidence_hits=evidence_hits,
        evidence_total=evidence_total,
    )
    unresolved = _print_grades(grades)

    if conversions:
        print()
        print("--- 召回 → 引用（--with-model）---")
        for name, in_context, used in conversions:
            print(f"  {name}：进上下文 {in_context}｜被引用 {used}")

    if unresolved:
        print()
        print(f"✗ 度量自检失败：{unresolved} 个期望锚点解析不了。先修度量，再谈调参。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
