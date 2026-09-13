#!/usr/bin/env python3
"""端到端验收：§8.0 的两个真实问题（可重复运行，失败即非零退出）。

这是「第二大脑答得对不对」的可判定版本——不是看答案读起来像不像，而是断言：

1. 两题都**不能**是 unanswerable（答不出来必须红，不许用模型编的答案冒充通过）；
2. 每条事实的出处都是 **`路径#区块`** 形式，且该锚点在索引里真实存在、能解析回原文；
3. 检索轨迹存在，且路由与预期一致；
4. **追溯链**：至少一条被引用的笔记能沿双链（≤2 跳）走到会议笔记或逐字稿；
5. 题目要求的关键证据笔记必须被召回（Q1 → 商标共识；Q2 → IT Roadmap）。

用法：

    .venv/bin/python scripts/kb_acceptance.py           # 真调模型
    .venv/bin/python scripts/kb_acceptance.py --no-model  # 只验检索，不问模型
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


@dataclass(frozen=True)
class Case:
    name: str
    question: str
    expect_route: str
    must_recall: str
    expect_transcript: bool = False


CASES = (
    Case(
        name="Q1 商标共识规范",
        question="根据之前和 HII 的沟通，请告诉我当前我们达成的商标共识规范是什么？",
        expect_route="decision",
        must_recall="hii/notes/20260912-hii-hic-ip-analysis",
    ),
    Case(
        name="Q2 IT 进度与下一阶段",
        question="IT 当前的开发进度是什么，下一个阶段该怎么做？",
        expect_route="point",
        must_recall="it/notes/20260912-hic-it-roadmap-analysis",
        # IT 侧有会议逐字稿，因此「走得到逐字稿」这条必须真的成立
        expect_transcript=True,
    ),
)


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

    # 模型配置在这里解析一次（--no-model 时完全不需要，因此不提前调用）
    cfg = api_key = prompt = None
    if not args.no_model:
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
            if args.no_model:
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
            if trace.route != case.expect_route:
                failures.append(f"{case.name}：路由 {trace.route} != 期望 {case.expect_route}")

            # 2) 关键证据必须被召回
            recalled = {c.source_id for c in trace.fused} | set(anchors)
            if not any(case.must_recall in item for item in recalled):
                failures.append(f"{case.name}：未召回关键证据 {case.must_recall}")

            # 3) 引用必须是块级且锚点真实存在
            block_level = [a for a in anchors if "#" in a]
            print(f"块级引用：{len(block_level)}/{len(anchors)}")
            for anchor in anchors:
                ok, reason = _check_anchor(index, anchor)
                if not ok:
                    failures.append(f"{case.name}：{reason}")
            if anchors and not block_level:
                failures.append(f"{case.name}：没有任何块级（路径#区块）引用")

            # 4) 追溯链：被引用笔记 ≤2 跳内能走到**证据层**。
            #    证据层只认「逐字稿」或「原始材料」：
            #    `type: meeting-transcript` / `type: source`。
            #    会议笔记是派生摘要，不算证据层——否则「走得到逐字稿」会被摘要冒充。
            #    HII 侧没有会议逐字稿（证据是邮件与汇总文档），因此也要接受 `type: source`。
            notes = index.notes()
            evidence_types = {"meeting-transcript", "source"}
            chains: list[str] = []
            for anchor in block_level:
                source_id = anchor.split("#", 1)[0]
                for neighbour in index.neighbours(source_id, hops=2):
                    info = notes.get(neighbour)
                    if info is not None and info.type in evidence_types:
                        chains.append(f"{source_id} → {neighbour}")
            transcripts = [
                chain
                for chain in chains
                if (notes.get(chain.split(" → ")[-1]) is not None)
                and notes[chain.split(" → ")[-1]].type == "meeting-transcript"
            ]
            print(f"追溯到证据层：{chains[0] if chains else '（未走出）'}（共 {len(chains)} 条）")
            print(f"其中走到逐字稿：{transcripts[0] if transcripts else '（无）'}")
            if not chains:
                failures.append(
                    f"{case.name}：没有任何被引用笔记能在 2 跳内走到证据层"
                    "（type: meeting-transcript 或 source）"
                )
            if case.expect_transcript and not transcripts:
                failures.append(f"{case.name}：没有走到逐字稿（本材料有逐字稿，不应只停在原文）")
            if answer_facts:
                print(f"事实条数：{len(answer_facts)}")

    print("\n" + "=" * 78)
    if failures:
        print(f"✗ 验收未通过，{len(failures)} 项：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("✓ 验收通过：两题都答出来了，逐条带块级出处，且能追到证据层。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
