"""真实问题回归清单：与 `scripts/kb_acceptance.py` **同一组问题**，跑在合成 vault 上。

为什么需要这一组：检索的启发式常量（路由关键词权重、导航型区块降权 `NAV_HEADINGS`、
`max_chunks_per_note=3`、`source_penalty=0.55`、`same_origin_penalty=0.35`、`link_seed_ratio=0.6`）
全是经验值，而此前只有 `kb_acceptance.py` 的两个真实问题做回归——那两题都在「点查/决策」，
回溯与回顾一旦被改坏没有任何断言会红。

设计要点：

- **问题清单不重复写**：直接从 `kb_acceptance.CASES` 取，只有 `must_recall` 换成合成 vault 里
  对应的那篇。`test_regression_list_covers_every_acceptance_case` 保证新增验收题时这里必须跟上，
  否则两组清单会悄悄漂移。
- 合成 vault 刻意照着真实库的形态搭：分析笔记 `##` 分节 + 链接原文与会议笔记，
  会议笔记用 `## 证据索引` 链到逐字稿，索引页与决策页各就各位；正文用真实问法里出现的说法
  （「开发进度」「下一个阶段该怎么做」「有哪些系统」…），因为检索是词法的、不是语义的。

每题断言（与 `kb_acceptance.audit_case` 同口径）：

1. **路由没被改坏**；
2. **关键证据被召回**；
3. **引用是块级**：至少一条命中锚点是 `路径#区块`；
4. **能走到证据层**：被引用笔记 ≤2 跳内能走到 `meeting-transcript` / `source`；
   有逐字稿的材料必须真的走到逐字稿。
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from summit_workbench.repositories.kb_index import KnowledgeIndex
from summit_workbench.workflows.ask.retrieval import retrieve_via_index

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# 复用验收脚本的证据层判定（同一口径，避免「测试自己发明一套宽松判据」）
acceptance = _load("kb_acceptance")
evidence_chains = acceptance.evidence_chains


# --------------------------------------------------------------------------- vault


def _note(vault: Path, rel: str, body: str, **front: object) -> Path:
    meta: dict[str, object] = {"date": "2026-09-13", "type": "note", "status": "active"}
    meta.update(front)
    lines = "\n".join(f"{key}: {value}" for key, value in meta.items())
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{lines}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"

    # ---- 索引层：MOC 只做导航 ----
    _note(
        root,
        "index/workstreams.md",
        "# 工作线索引\n\n## 进行中\n\n- [[hii-loyalty|HII 忠诚度与 IP]]\n"
        "- [[it-roadmap|HIC IT 路线图]]\n",
        type="index",
        project="global",
        aliases="[工作线索引, workstreams]",
    )
    _note(
        root,
        "index/decisions.md",
        "# 决策台账\n\n## 本月\n\n"
        "本月的结论都记在下面；这段时间的决策复盘可以直接从这里读。\n\n"
        "- [[20260623-registration-entity-is-hii|登记主体为 HII]]\n"
        "- [[20260911-royalty-tier-restart-on-first-payment|royalty 分层重启口径]]\n"
        "- [[20260913-china-visit-three-stage-sop|访华三段式 SOP]]\n",
        type="index",
        project="global",
    )

    # ---- 工作线主页 ----
    _note(
        root,
        "hii/hii-loyalty.md",
        "# HII 忠诚度与 IP 工作线\n\n## 当前状态\n\n商标与 royalty 口径已基本收敛，"
        "剩余四套版权材料待归档。\n\n## 关联\n\n"
        "- [[20260912-hii-hic-ip-analysis|IP 关系与治理分析]]\n",
        type="workstream",
        workstream="hii",
        project="global",
    )
    _note(
        root,
        "it/it-roadmap.md",
        "# HIC IT 路线图工作线\n\n## 当前状态\n\n报名系统与门户 CMS 进入收尾，"
        "权限模型与账户治理是下一阶段第一重点。\n\n## 关联\n\n"
        "- [[20260912-hic-it-roadmap-analysis|IT 开发计划与进度分析]]\n",
        type="workstream",
        workstream="it",
        project="global",
    )

    # ---- HII 分析笔记：`##` 分节，链接原文 ----
    _note(
        root,
        "hii/notes/20260912-hii-hic-ip-analysis.md",
        "# HII × HIC IP 关系与治理 · 分析笔记\n\n"
        "## 商标共识规范\n\n"
        "经过 2026-06-23 与 Kate Mayer 的邮件沟通，双方达成的商标共识是："
        "所有商标注册登记在 HII（Hoffman Institute International）名下；"
        "活满（Huoman）归 HIC 自有；和夫曼之旅归 HII 且正在注册。"
        "登记主体名称统一为 Hoffman Institute International。"
        "这段商标共识是怎么走到今天这一步的，来龙去脉见时间线一节。\n\n"
        "## 关联\n\n"
        "- [[20260912-hii-hic-ip-overview|原文：HII × HIC IP 总结]]\n"
        "- [[20260623-registration-entity-is-hii|登记主体为 HII]]\n",
        workstream="hii",
        domain="ip-licensing",
        aliases="[商标共识, 商标共识规范, trademark consensus, IP 时间线]",
        people="[Kate Mayer, 曹木子]",
        org="[HII]",
    )
    _note(
        root,
        "hii/sources/20260912-hii-hic-ip-overview.md",
        "# 原文：HII × HIC IP 关系与治理总结\n\n"
        "## 六、正式名称与商标归属\n\n"
        "All trademark registrations shall be filed under HII. "
        "所有商标注册登记在 HII 名下；活满归 HIC；和夫曼之旅归 HII。\n",
        type="source",
        workstream="hii",
        source="\n  kind: doc\n  ref: hii/sources/raw.md",
    )
    _note(
        root,
        "hii/notes/20260911-hic-hii-royalty-analysis.md",
        "# HIC × HII Royalty 分析笔记\n\n"
        "## Royalty 分层口径与依据\n\n"
        "royalty 分层的口径与依据：累计层级在学员首次实际付款时重启；"
        "奖学金折扣不计入 royalty 基数。三次口径修正见下节。\n\n"
        "## 关联\n\n"
        "- [[20260911-hic-hii-royalty-rules|原文：Royalty 规则]]\n"
        "- [[20260911-royalty-tier-restart-on-first-payment|royalty 分层重启口径]]\n",
        workstream="hii",
        domain="royalty",
        aliases="[royalty 口径, Royalty 分析]",
        people="[Trish Barney]",
    )
    _note(
        root,
        "hii/sources/20260911-hic-hii-royalty-rules.md",
        "# 原文：HIC × HII Royalty 规则\n\n## 一、分层规则\n\nroyalty 分层在首次付款时重启。\n",
        type="source",
        workstream="hii",
    )

    # ---- IT 分析笔记 + 原文 + 会议笔记 + 逐字稿 ----
    _note(
        root,
        "it/notes/20260912-hic-it-roadmap-analysis.md",
        "# HIC IT 开发计划与进度 · 分析笔记\n\n"
        "## HIC IT 开发进度与当前状态\n\n"
        "IT 当前的开发进度：报名系统进入收尾，门户 CMS 内容已逐项分配到人，"
        "权限模型仍停在类型级、需要把颗粒度做细到「角色 × 项目 × 课程」。\n\n"
        "## 下一个阶段该怎么做\n\n"
        "下一个阶段该怎么做：Phase 2（9–12 月）第一重点是权限体系与 IT 账户治理，"
        "其次是业务电子化，再次是本地 AI 与手机端。\n\n"
        "## 系统现状一览\n\n"
        "目前有哪些系统，分别是什么状态：报名系统收尾中；门户 CMS 内容分配完成；"
        "网课模块待绑定老师账户；手机端与本地 AI 尚未启动。\n\n"
        "## 关联\n\n"
        "- [[20260912-hic-it-roadmap-progress|原文：HIC IT 开发计划与当前进度总结]]\n"
        "- [[20260907-portal-permission-alignment|门户权限与网课老师绑定 2026-09-07]]\n",
        workstream="it",
        domain="it-roadmap",
        aliases="[IT 开发计划, 开发进度, IT Roadmap]",
        people="[罗艺峰, 韩文博]",
        org="[HIC]",
    )
    _note(
        root,
        "it/sources/20260912-hic-it-roadmap-progress.md",
        "# 原文：HIC IT 开发计划与当前进度总结 V1.0\n\n"
        "## 三、当前进度\n\n报名系统与门户 CMS 收尾；权限模型需细化。\n",
        type="source",
        workstream="it",
        source="\n  kind: doc\n  ref: it/sources/raw.md",
    )
    _note(
        root,
        "meetings/notes/20260907-portal-permission-alignment.md",
        "# 门户权限与网课老师绑定 2026-09-07\n\n"
        "## 一分钟摘要\n\n"
        "门户权限「不同项目各自管理员」这个方向最早由罗艺峰提出；"
        "后来定下来的口径是每个项目各自有管理员。"
        "网课需绑定老师账户并由老师放腾讯会议链接。\n\n"
        "## 证据索引\n\n"
        "- 逐字稿：\n"
        "  [[2026-09-07-luo-yifeng-video-meeting-2-transcript|2026-09-07 视频会议（2）逐字稿]]\n",
        type="meeting-note",
        workstream="it",
        projects="[hic-portal-cms, hic-enrollment]",
        people="[罗艺峰, 韩文博]",
    )
    _note(
        root,
        "meetings/transcripts/2026-09-07-luo-yifeng-video-meeting-2-transcript.md",
        "# 2026-09-07 罗艺峰 × 韩文博 视频会议（2）· 完整逐字稿\n\n"
        "2026-09-07 17:50:34 CST\n\n"
        "00:02 罗艺峰：门户内容我都分配下去了。\n"
        "05:52 韩文博：权限现在只到类型级。\n",
        type="meeting-transcript",
        workstream="it",
        status="archived",
        projects="[hic-portal-cms, hic-enrollment]",
    )

    # ---- 决策层 ----
    _note(
        root,
        "decisions/20260623-registration-entity-is-hii.md",
        "# 决策：商标登记主体为 HII\n\n## 结论\n\n所有商标注册登记在 HII 名下。\n\n"
        "## 依据\n\n2026-06-23 Kate Mayer 邮件。\n",
        type="decision",
        workstream="hii",
        aliases="[登记主体为 HII]",
    )
    _note(
        root,
        "decisions/20260911-royalty-tier-restart-on-first-payment.md",
        "# 决策：royalty 分层在首次付款时重启\n\n## 结论\n\n"
        "royalty 累计层级在学员首次实际付款时重启；奖学金折扣不计入 royalty 基数。\n\n"
        "## 依据\n\n2026-09-11 与 Trish Barney 的沟通。\n",
        type="decision",
        workstream="hii",
        aliases="[royalty 分层重启, royalty 口径]",
    )
    _note(
        root,
        "decisions/20260913-china-visit-three-stage-sop.md",
        "# 决策：访华三段式 SOP\n\n## 结论\n\n访华按触发条件分三段执行。\n",
        type="decision",
        workstream="hii",
    )

    # ---- 回顾层 ----
    _note(
        root,
        "reviews/weekly/2026-W37.md",
        "# 周回顾 2026-W37\n\n"
        "## 本周进展\n\n"
        "这周有哪些进展：IT 侧门户权限方向确认、报名系统收尾；"
        "HII 侧商标共识规范与 royalty 口径定稿。\n\n"
        "## 下周重点\n\n权限模型细化、账户治理启动。\n\n"
        "## 关联\n\n- [[it-roadmap|HIC IT 路线图]]\n- [[hii-loyalty|HII 忠诚度与 IP]]\n",
        type="weekly-review",
        project="global",
    )
    return root


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return _vault(tmp_path)


# --------------------------------------------------------------------------- cases


@dataclass(frozen=True)
class Regression:
    name: str
    question: str
    expect_route: str
    must_recall: str
    expect_transcript: bool = False


# 问题原文 / 期望路由 / 逐字稿要求来自验收清单；「哪篇是关键证据」按本合成 vault 映射。
#
# ⚠️ 这里**只收合成 vault 里真有对应材料的题**：4 个对外验收题（Q1–Q4）跑真实库
# （`scripts/kb_acceptance.py`），不该为了迁就一个小 fixture 去伪造 Danny / 活满 / 主题簇页材料——
# 那样测的是 fixture 而不是库。职责划分：合成库管「路由 + 块级锚点 + 追溯链」的机制回归，
# 真实库管「答案对不对」。
_MUST_RECALL: dict[str, str] = {
    "R1 商标共识的来龙去脉（回溯）": "hii/notes/20260912-hii-hic-ip-analysis",
    "R2 门户权限方向的由来（回溯）": "meetings/notes/20260907-portal-permission-alignment",
    "D1 royalty 分层口径与依据（决策）": "hii/notes/20260911-hic-hii-royalty-analysis",
    "V1 近期进展回顾（回顾）": "reviews/weekly/2026-W37",
    "S1 系统现状一览（综合）": "it/notes/20260912-hic-it-roadmap-analysis",
}

REGRESSIONS: tuple[Regression, ...] = tuple(
    Regression(
        name=case.name,
        question=case.question,
        expect_route=case.expect_route,
        must_recall=_MUST_RECALL[case.name],
        expect_transcript=case.expect_transcript,
    )
    for case in acceptance.CASES
    if case.name in _MUST_RECALL
)


def test_regression_list_covers_every_synthetic_vault_case() -> None:
    """合成库回归必须覆盖**所有非模型题**；4 个对外验收题由真实库那条链路覆盖。"""
    cheap = {case.name for case in acceptance.CASES if not case.use_model}
    assert set(_MUST_RECALL) == cheap, set(_MUST_RECALL) ^ cheap


def test_regression_list_covers_the_three_scenarios() -> None:
    # 合成库只跑非模型题（当前 5 道）；4 个对外验收题在真实库上跑，见 kb_acceptance.py。
    assert len(REGRESSIONS) >= 5
    routes = {case.expect_route for case in REGRESSIONS}
    assert {"retrospect", "decision", "review"} <= routes


@pytest.mark.parametrize("case", REGRESSIONS, ids=[case.name for case in REGRESSIONS])
def test_regression_question_recalls_key_evidence_with_block_anchors(
    vault: Path, tmp_path: Path, case: Regression
) -> None:
    index_path = tmp_path / "kb.sqlite"
    candidates, trace = retrieve_via_index(vault, case.question, index_path=index_path)

    # 1) 路由没被改坏
    assert trace.route == case.expect_route, f"{case.name}: {trace.route_reason}"
    assert trace.degraded == ""

    anchors = [candidate.source_id for candidate in candidates]
    assert anchors, f"{case.name}：没有任何召回"

    # 2) 关键证据被召回（融合结果或块级引用任意一处出现即可）
    recalled = {chunk.source_id for chunk in trace.fused} | {
        anchor.split("#", 1)[0] for anchor in anchors
    }
    assert any(case.must_recall in item for item in recalled), (
        f"{case.name}：未召回关键证据 {case.must_recall}；实际召回 {sorted(recalled)}"
    )

    # 3) 引用是块级（`路径#区块`），答案才能精确到节
    block_level = [anchor for anchor in anchors if "#" in anchor]
    assert block_level, f"{case.name}：没有任何块级引用；实际 {anchors}"

    # 4) 能走到证据层（`meeting-transcript` / `source`）；有逐字稿的必须真的走到逐字稿
    with KnowledgeIndex(vault, index_path) as index:
        index.build()
        chains, transcripts = evidence_chains(index, tuple(anchors))
    assert chains, f"{case.name}：没有任何被引用笔记能在 2 跳内走到证据层"
    if case.expect_transcript:
        assert transcripts, f"{case.name}：没有走到逐字稿"
