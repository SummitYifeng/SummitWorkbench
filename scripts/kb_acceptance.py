#!/usr/bin/env python3
"""端到端验收：真实问题回归清单（可重复运行，失败即非零退出）。

这是「第二大脑答得对不对」的可判定版本——不是看答案读起来像不像，而是断言：

1. 问题**不能**是 unanswerable（答不出来必须红，不许用模型编的答案冒充通过）；
2. 每条事实的出处都是 **`路径#区块`** 形式，且该锚点在索引里真实存在、能解析回原文；
3. 检索轨迹存在，且路由与预期一致；
4. **追溯链**：至少一条被引用笔记能沿双链（≤2 跳）走到**证据层**（逐字稿或原始材料）；
5. 题目要求的关键证据笔记必须被召回。

清单覆盖使用者指定的三个优先场景 ① 回溯 / ② 决策 / ⑤ 回顾，外加点查与综合两个基础形态。
只有 `Q1` / `Q2` 会真的调用模型（它们是对外验收口径）；其余各题**只验检索**
（`use_model=False`），因此扩充清单不增加任何 token 成本。

用法：

    .venv/bin/python scripts/kb_acceptance.py           # Q1/Q2 真调模型 + 其余只验检索
    .venv/bin/python scripts/kb_acceptance.py --no-model  # 全部只验检索，不问模型
"""

from __future__ import annotations

import argparse
import sys
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
from summit_workbench.workflows.ask.retrieval import build_index  # noqa: E402

# 什么算「证据层」：**逐字稿**或**原始材料**。
#
# `meeting-note` 是派生摘要，故意不在集合里——这一条是踩过坑的：早先版本把会议笔记也算作
# 证据层，于是「笔记 → 会议笔记」这条链会让验收通过，看起来走到了证据，其实停在摘要上，
# 摘要里的内容是不是原件说的并没有被校验。判据必须只认原件。
EVIDENCE_TYPES = frozenset({"meeting-transcript", "source"})


@dataclass(frozen=True)
class Case:
    name: str
    question: str
    expect_route: str
    must_recall: str = ""
    expect_transcript: bool = False
    # 只有对外验收的题真调模型；其余是检索回归，不花 token
    use_model: bool = False
    # 关键证据的**等价入口**：与 must_recall 取并集后按 any-of 判。同一个答案既可能落在
    # 主题簇页、也可能落在项目主页的入口版（两页内容等价）；写死唯一正解会把等价答案判成失败——
    # 2026-09-14 实测：Q1 答出完整商标共识清单、出处是 `projects/hii-affairs#关键结论`，
    # 只因上下文里没出现簇页而红了。
    must_recall_any: tuple[str, ...] = ()
    # 答案层期望：**块级**锚点，命中任意一个即通过（理由同上）。
    must_recall_blocks: tuple[str, ...] = ()


CASES = (
    # ---- 使用者指定的 4 个验收问题（2026-09-14 对齐时的原话）----
    Case(
        name="Q1 商标共识规范",
        question="根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？",
        expect_route="decision",
        must_recall="hii/clusters/ip-trademark",
        must_recall_any=("projects/hii-affairs",),
        must_recall_blocks=(
            "hii/clusters/ip-trademark#关键结论",
            "projects/hii-affairs#关键结论",
        ),
        use_model=True,
    ),
    Case(
        name="Q2 Danny 来华待收口",
        question="Danny 来华目前还差哪些必须收口？下一步谁做什么？",
        expect_route="point",
        must_recall="hii/visits/danny-kim-2026-09",
        must_recall_blocks=(
            "hii/visits/danny-kim-2026-09#未决问题",
            "hii/visits/danny-kim-2026-09#关键结论",
        ),
        use_model=True,
    ),
    Case(
        name="Q3 IT 进度与下一阶段",
        question="IT 当前的开发进度是什么，下一个阶段该怎么做？",
        expect_route="point",
        must_recall="it/notes/20260912-hic-it-roadmap-analysis",
        # IT 侧有会议逐字稿，「走得到逐字稿」这条必须真的成立
        expect_transcript=True,
        must_recall_blocks=(
            # 这一节的标题很长（它是「一句话回答」那一节），拆成两行只为过 lint
            "it/notes/20260912-hic-it-roadmap-analysis"
            "#一句话回答：IT 当前的开发进度是什么，下一个阶段该怎么做",
            "it/notes/20260912-hic-it-roadmap-analysis#2026 总体优先级与 9—12 月 Roadmap",
            "projects/it-development#关键结论",
        ),
        use_model=True,
    ),
    Case(
        name="Q4 活满 vs 和夫曼",
        question="「活满」与「和夫曼之旅」为什么分开管理？当时还有哪些选项？",
        expect_route="decision",
        must_recall="decisions/20260912-huoman-separate-from-hefuman",
        must_recall_blocks=(
            "decisions/20260912-huoman-separate-from-hefuman#选项",
            "decisions/20260912-huoman-separate-from-hefuman#决定",
        ),
        use_model=True,
    ),
    # ---- 零 token 的检索回归（路由 + 追溯链），扩充它们不增加成本 ----
    Case(
        name="R1 商标共识的来龙去脉（回溯）",
        question="HII 与 HIC 的商标共识是怎么走到今天这一步的？来龙去脉是什么？",
        expect_route="retrospect",
        must_recall="hii/notes/20260912-hii-hic-ip-analysis",
    ),
    Case(
        name="R2 门户权限方向的由来（回溯）",
        question="门户权限「不同项目各自管理员」这个方向最早是怎么提出的？后来怎么定下来的？",
        expect_route="retrospect",
        must_recall="meetings/notes/20260907-portal-permission-alignment",
    ),
    Case(
        name="D1 royalty 分层口径与依据（决策）",
        question="royalty 分层的口径与依据是什么？",
        expect_route="decision",
        # β 架构下**主题簇页是答案层**、分析笔记是明细层：分层口径的入口版在簇页的
        # `## 关键结论`（实测召回里同时还有 3 篇 royalty 决策的 `#选项`/`#决定`）。
        must_recall="hii/clusters/royalty",
        must_recall_blocks=(
            "hii/clusters/royalty#关键结论",
            "hii/notes/20260911-hic-hii-royalty-analysis#完整计算公式（HIC 当前执行版）",
        ),
    ),
    Case(
        name="V1 近期进展回顾（回顾）",
        question="这周 IT 和 HII 这边都有哪些进展？回顾一下。",
        expect_route="review",
        must_recall="it/notes/20260912-hic-it-roadmap-analysis",
    ),
    Case(
        name="S1 系统现状一览（综合）",
        question="目前有哪些系统，分别是什么状态？",
        expect_route="synthesis",
        must_recall="it/notes/20260912-hic-it-roadmap-analysis",
    ),
)


@dataclass(frozen=True)
class Observation:
    """一次运行的客观事实：模型回答与纯检索都能产出同样的形状。

    把它与 :func:`audit_case` 分开，是为了让判定逻辑可以脱离模型、脱离真实 vault 被单测。
    """

    route: str
    anchors: tuple[str, ...] = ()  # 事实级引用（`路径#区块`）；纯检索时为召回锚点
    fused: tuple[str, ...] = ()  # 融合排序给出的 source_id（不含区块）
    fused_anchors: tuple[str, ...] = ()  # 融合排序给出的完整锚点（含区块）
    recalled: tuple[str, ...] = ()  # 额外计入「已召回」的 source_id（追问固定来源等）


def _check_anchor(index: KnowledgeIndex, anchor: str) -> tuple[bool, str]:
    """锚点必须能在索引里找到对应的块（否则引用是编的）。"""
    source_id, _, heading = anchor.partition("#")
    if source_id not in index.notes():
        return False, f"笔记不存在：{source_id}"
    if not heading:
        return True, ""
    for row in index._connection.execute(
        "SELECT heading FROM chunks WHERE source_id = ?", (source_id,)
    ):
        if row["heading"] == heading:
            return True, ""
    return False, f"区块不存在：{anchor}"


def evidence_chains(
    index: KnowledgeIndex, anchors: tuple[str, ...], *, hops: int = 2
) -> tuple[list[str], list[str]]:
    """被引用笔记 ≤``hops`` 跳内能走到的证据层。

    返回 ``(全部证据链, 其中走到逐字稿的链)``。链的写法是 ``笔记 → 证据``，
    类型判定只看**链尾**——走到哪一层算哪一层，不做「链上出现过就算」的宽松判定。
    """
    notes = index.notes()
    chains: list[str] = []
    transcripts: list[str] = []
    for anchor in anchors:
        source_id = anchor.split("#", 1)[0]
        if source_id not in notes:
            continue
        for neighbour in sorted(index.neighbours(source_id, hops=hops)):
            info = notes.get(neighbour)
            if info is None or info.type not in EVIDENCE_TYPES:
                continue
            chain = f"{source_id} → {neighbour}"
            chains.append(chain)
            if info.type == "meeting-transcript":
                transcripts.append(chain)
    return chains, transcripts


def audit_case(case: Case, observation: Observation, index: KnowledgeIndex) -> list[str]:
    """把一条验收（路由 / 关键证据 / 块级锚点 / 追溯链）判成失败清单。

    纯函数：只读索引，不调模型、不写盘。空列表即通过。
    """
    failures: list[str] = []

    # 1) 路由
    if observation.route != case.expect_route:
        failures.append(f"{case.name}：路由 {observation.route} != 期望 {case.expect_route}")

    # 2) 关键证据必须被召回（融合结果或事实引用任意一处出现即可）。
    #    等价入口之间是 any-of：命中其中一个即可。
    wanted_notes = ((case.must_recall,) if case.must_recall else ()) + case.must_recall_any
    recalled = set(observation.fused) | set(observation.recalled)
    recalled |= {anchor.split("#", 1)[0] for anchor in observation.anchors}
    if wanted_notes and not any(note in item for note in wanted_notes for item in recalled):
        failures.append(f"{case.name}：未召回关键证据（任一即可）：{'、'.join(wanted_notes)}")

    # 2.5) 答案层块级期望：候选或引用里必须出现**其中一个**（任一即可，见 Case 的说明）
    if case.must_recall_blocks:
        seen = set(observation.anchors) | set(observation.fused_anchors)
        if not any(block in seen for block in case.must_recall_blocks):
            wanted = "、".join(case.must_recall_blocks)
            failures.append(f"{case.name}：未召回答案块（任一即可）：{wanted}")

    # 3) 引用必须是块级，且锚点真实存在（编造的区块必须红）
    block_level = [anchor for anchor in observation.anchors if "#" in anchor]
    for anchor in observation.anchors:
        ok, reason = _check_anchor(index, anchor)
        if not ok:
            failures.append(f"{case.name}：{reason}")
    if observation.anchors and not block_level:
        failures.append(f"{case.name}：没有任何块级（路径#区块）引用")

    # 4) 追溯链：被引用笔记 ≤2 跳内能走到证据层；有逐字稿的材料必须真的走到逐字稿
    chains, transcripts = evidence_chains(index, observation.anchors)
    if not chains:
        failures.append(
            f"{case.name}：没有任何被引用笔记能在 2 跳内走到证据层"
            "（type: meeting-transcript 或 source）"
        )
    if case.expect_transcript and not transcripts:
        failures.append(f"{case.name}：没有走到逐字稿（本材料有逐字稿，不应只停在原文）")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="第二大脑端到端验收")
    parser.add_argument("--no-model", action="store_true", help="只验检索与引用，不调用模型。")
    args = parser.parse_args()

    active = resolve_active_workspace()
    if active.paths is None or active.config_file is None:
        print("✗ 找不到本机 active workspace（先在 App 里完成连接向导）", file=sys.stderr)
        return 2
    vault_dir = active.paths.vault_dir
    index_path = default_index_path()

    stats = build_index(vault_dir, index_path, full=True)
    print(f"索引：{stats.summary()}")
    print(f"索引库：{index_path}\n")

    # 模型配置在这里解析一次（--no-model 或全部题目都不调模型时完全不需要）
    any_model = (not args.no_model) and any(case.use_model for case in CASES)
    cfg = api_key = prompt = None
    if any_model:
        cfg = load_model_config("qa", active.config_file, workspace_id=active.workspace_id)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")

    failures: list[str] = []
    with KnowledgeIndex(vault_dir, index_path) as index:
        index.build()
        for case in CASES:
            print("=" * 78)
            print(f"【{case.name}】{case.question}")
            print("-" * 78)
            if args.no_model or not case.use_model:
                from summit_workbench.workflows.ask.retrieval import retrieve_via_index

                candidates, trace = retrieve_via_index(
                    vault_dir, case.question, index_path=index_path
                )
                print(f"路由：{trace.route}（{trace.route_reason}）")
                print("召回：" + "、".join(c.source_id for c in candidates))
                anchors = [c.source_id for c in candidates]
                answer_facts: list[str] = []
            else:
                assert cfg is not None and api_key is not None and prompt is not None
                result = answer_question(
                    vault_dir,
                    case.question,
                    cfg,
                    api_key,
                    prompt=prompt,
                    index_path=index_path,
                )
                trace = result.trace
                anchors = [fact.source_id for fact in result.answer.facts]
                answer_facts = [fact.text for fact in result.answer.facts]
                print(f"\n{result.answer.summary}\n")
                for fact in result.answer.facts:
                    print(f"  • {fact.text}\n      ← {fact.source_id}")
                if result.answer.unanswerable:
                    failures.append(f"{case.name}：模型判为 unanswerable")
                if not result.answer.facts:
                    failures.append(f"{case.name}：没有任何带出处的事实")

            # 1) 路由
            assert trace is not None
            print(f"\n检索轨迹：路由={trace.route}（{trace.route_reason}）")
            fused = tuple(chunk.source_id for chunk in trace.fused)
            fused_anchors = tuple(chunk.anchor for chunk in trace.fused)
            if case.must_recall_blocks:
                hit = [
                    block
                    for block in case.must_recall_blocks
                    if block in set(anchors) | set(fused_anchors)
                ]
                print(f"答案块期望：{'✓ ' + hit[0] if hit else '✗ 一个都没进候选/引用'}")

            # 2) 关键证据必须被召回（fused 已在上方算好）

            # 3) 引用必须是块级且锚点真实存在
            block_level = [a for a in anchors if "#" in a]
            print(f"块级引用：{len(block_level)}/{len(anchors)}")

            # 4) 追溯链：被引用笔记 ≤2 跳内能走到**证据层**（逐字稿 / 原始材料）
            observation = Observation(
                route=trace.route,
                anchors=tuple(anchors),
                fused=fused,
                fused_anchors=fused_anchors,
            )
            case_failures = audit_case(case, observation, index)
            failures.extend(case_failures)

            chains, transcripts = evidence_chains(index, tuple(anchors))
            print(f"追溯到证据层：{chains[0] if chains else '（未走出）'}（共 {len(chains)} 条）")
            print(f"其中走到逐字稿：{transcripts[0] if transcripts else '（无）'}")
            if answer_facts:
                print(f"事实条数：{len(answer_facts)}")

    print("\n" + "=" * 78)
    if failures:
        print(f"✗ 验收未通过，{len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    model_cases = [case for case in CASES if case.use_model and not args.no_model]
    if model_cases:
        print(
            f"✓ 验收通过：{len(CASES)} 题检索全部合格（其中 {len(model_cases)} 题真调模型并答出），"
            "逐条带块级出处，且能追到证据层。"
        )
    else:
        print(
            f"✓ 验收通过：{len(CASES)} 题检索全部合格（未调用模型），"
            "逐条带块级出处，且能追到证据层。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
