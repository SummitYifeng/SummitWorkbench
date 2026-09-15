"""「知识沉淀」落点（`RouteTarget.KNOWLEDGE_NOTE`）：把结论写回指定页面的指定区块。

为什么单独测：这是审批链路上**唯一一个会把内容写进「知识层」而不是「执行层」的落点**
（主题簇页 / 项目主页），也是唯一一个目标由使用者显式指定（`sink_target`）的落点，
因此两条边界必须钉死：① 只允许 vault 相对路径（不得越出库）；② 目标页与区块不存在时
必须拒批并给出可读原因，而不是静默创建或写坏。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from summit_workbench.domain.review import (
    ApprovalCandidate,
    CandidateDecision,
    CandidateKind,
    EvidenceRef,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.repositories.review_page import (
    parse_review_page,
    refresh_review_page,
    render_review_page,
)
from summit_workbench.repositories.writeback import (
    append_knowledge_note,
    parse_sink_target,
)
from summit_workbench.workflows.review_apply import apply_meeting_review

_NOTE_REL = "meetings/notes/2026-09-02-沟通对齐会"


def _cluster_page(vault: Path, rel: str = "hii/clusters/ip-trademark") -> Path:
    path = vault / f"{rel}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: 2026-09-14-c010\ntitle: 商标 IP\narea: work\nworkstream: hii\n"
        "project: hii-affairs\ntype: note\nstatus: active\ncreated: 2026-09-14\n"
        "updated: 2026-09-14\ndate: 2026-09-14\nsummary: s\n---\n\n"
        "# 商标 IP\n\n## 现在在哪\n\n状态。\n\n## 关键结论\n\n## 未决问题\n\n## 关联\n",
        encoding="utf-8",
    )
    return path


def _meeting_note(vault: Path) -> None:
    path = vault / f"{_NOTE_REL}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "date: 2026-09-02\n"
        "type: meeting-note\n"
        "status: pending-review\n"
        "idem_key: 'm:n'\n"
        "transcript: '[[2026-09-02-沟通对齐会-transcript]]'\n"
        "projects:\n"
        "- unresolved\n"
        "---\n\n"
        "# 沟通对齐会\n\n"
        "## 一分钟摘要\n\n摘\n\n"
        "## 会议信息\n\n- 原文：[[2026-09-02-沟通对齐会-transcript]]\n\n"
        "## 事实与进展\n\n## 已形成决策\n\n## 明确行动项\n\n## 未决问题\n\n"
        "## AI 建议\n\n## 关联项目\n\n- unresolved\n\n"
        "## 证据索引\n\n- [[2026-09-02-沟通对齐会-transcript]] · 木子 00:01\n",
        encoding="utf-8",
    )


def _entry(
    stable_id: str,
    *,
    decision: CandidateDecision,
    sink_target: str | None,
    description: str = "商标共识：登记主体统一为 HII",
) -> ReviewEntry:
    candidate = ApprovalCandidate(
        candidate_id=stable_id,
        kind=CandidateKind.DECISION,
        description=description,
        target_project=None,
        route=RouteTarget.KNOWLEDGE_NOTE,
        evidence=EvidenceRef(anchor="木子 00:03"),
        sink_target=sink_target,
        decision=decision,
    )
    return ReviewEntry(
        candidate,
        description,
        "2026-09-02",
        "沟通对齐会",
        f"[[{_NOTE_REL}]]",
        "[[2026-09-02-沟通对齐会-transcript]]",
    )


# ---- parse_sink_target：目标口径与安全边界 ----


def test_parse_sink_target_defaults_block_and_strips_md_suffix() -> None:
    rel, heading = parse_sink_target("hii/clusters/ip-trademark.md")
    assert rel.as_posix() == "hii/clusters/ip-trademark"
    assert heading == "## 关键结论"  # 缺区块时默认落到「关键结论」


def test_parse_sink_target_accepts_plain_or_hashed_block() -> None:
    for raw in ("hii/clusters/royalty#未决问题", "hii/clusters/royalty#未决问题"):
        rel, heading = parse_sink_target(raw)
        assert rel.as_posix() == "hii/clusters/royalty"
        assert heading == "## 未决问题"
    _, hashed = parse_sink_target("index/sop##第 ① 步 · 上传")
    assert hashed == "## 第 ① 步 · 上传"


@pytest.mark.parametrize(
    "bad",
    ["../outside#关键结论", "/etc/passwd#关键结论", "hii/../../outside#x", "", "   ", "#只有区块"],
)
def test_parse_sink_target_rejects_escaping_or_empty_targets(bad: str) -> None:
    """安全边界：一条审批写回不得把内容写到 vault 之外，也不得没有页面。

    变异验证：把 `parse_sink_target` 里的 `..` / 绝对路径检查删掉，本用例必须变红。
    """
    with pytest.raises(ValueError):
        parse_sink_target(bad)


# ---- append_knowledge_note：写入与幂等 ----


def test_append_knowledge_note_writes_dated_line_with_source(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    page = _cluster_page(vault)
    path, written = append_knowledge_note(
        vault,
        "hii/clusters/ip-trademark#关键结论",
        "登记主体统一为 HII",
        "m:n#decision-0",
        source_ref="meetings/notes/2026-09-02-沟通对齐会#已形成决策",
        today="2026-09-14",
    )
    assert written is True
    assert path == page
    text = page.read_text(encoding="utf-8")
    assert (
        "- 2026-09-14 登记主体统一为 HII（出处：meetings/notes/2026-09-02-沟通对齐会#已形成决策）"
        in text
    )
    # 写进的是「关键结论」区块，不是文末也不是别的区块
    body = text.split("## 关键结论", 1)[1]
    assert "登记主体统一为 HII" in body.split("## 未决问题", 1)[0]


def test_append_knowledge_note_is_idempotent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    page = _cluster_page(vault)
    for _ in range(3):
        _path, written = append_knowledge_note(
            vault, "hii/clusters/ip-trademark#关键结论", "同一条结论", "m:n#decision-0"
        )
    assert written is False  # 第三次已存在
    assert page.read_text(encoding="utf-8").count("同一条结论") == 1


def test_append_knowledge_note_rejects_missing_page_or_block(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _cluster_page(vault)
    with pytest.raises(ValueError, match="写回目标不存在"):
        append_knowledge_note(vault, "hii/clusters/nope#关键结论", "x", "id")
    with pytest.raises(ValueError, match="缺少固定区块"):
        append_knowledge_note(vault, "hii/clusters/ip-trademark#不存在的区块", "x", "id")


# ---- is_actionable：没有沉淀目标就不该可勾选 ----


def test_knowledge_note_requires_a_sink_target_to_be_actionable() -> None:
    with_target = _entry("a#1", decision=CandidateDecision.PENDING, sink_target="index/sop#一图流")
    without = _entry("a#2", decision=CandidateDecision.PENDING, sink_target=None)
    assert with_target.candidate.is_actionable() is True
    assert without.candidate.is_actionable() is False


# ---- 审批页往返：sink_target 不丢 ----


def test_review_page_round_trips_sink_target(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True)
    entries = [
        _entry(
            "m:n#decision-0",
            decision=CandidateDecision.APPROVED,
            sink_target="hii/clusters/ip-trademark#关键结论",
        )
    ]
    text = render_review_page(entries)
    assert "sink_target: hii/clusters/ip-trademark#关键结论" in text
    parsed = parse_review_page(text)
    assert parsed.errors == []
    assert parsed.entries[0].candidate.sink_target == "hii/clusters/ip-trademark#关键结论"


# ---- 端到端：批准 → 写进主题簇页 ----


def test_apply_writes_knowledge_note_into_cluster_page(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _meeting_note(vault)
    page = _cluster_page(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#decision-0",
                decision=CandidateDecision.APPROVED,
                sink_target="hii/clusters/ip-trademark#关键结论",
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True, now=datetime(2026, 9, 14, tzinfo=UTC))
    assert report.applied == 1
    assert report.failed == 0
    text = page.read_text(encoding="utf-8")
    assert "登记主体统一为 HII" in text
    # T3：出处必须是**可解析**的 `路径#区块`（契约 §2 的 anchor），证据锚点作补充。
    assert "出处：meetings/notes/2026-09-02-沟通对齐会#已形成决策 · 木子 00:03" in text
    source_id, _, heading = "meetings/notes/2026-09-02-沟通对齐会#已形成决策".partition("#")
    assert (vault / f"{source_id}.md").is_file()
    assert f"## {heading}" in (vault / f"{source_id}.md").read_text(encoding="utf-8")


def test_knowledge_note_source_ref_falls_back_to_evidence_without_note_file(
    tmp_path: Path,
) -> None:
    """会议笔记文件不在库内时，不编造指向不存在文件的引用，退回可读证据锚点。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    page = _cluster_page(vault)  # 刻意不建 _meeting_note(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#decision-0",
                decision=CandidateDecision.APPROVED,
                sink_target="hii/clusters/ip-trademark#关键结论",
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True, now=datetime(2026, 9, 14, tzinfo=UTC))
    assert report.applied == 1
    text = page.read_text(encoding="utf-8")
    assert "出处：木子 00:03" in text
    assert "meetings/notes/" not in text  # 不产生悬空引用


def test_apply_reports_a_clear_reason_when_sink_page_is_missing(tmp_path: Path) -> None:
    """目标页不存在时必须拒批并给出可读原因，而不是静默创建或写坏。"""
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _meeting_note(vault)
    refresh_review_page(
        vault,
        [
            _entry(
                "m:n#decision-0",
                decision=CandidateDecision.APPROVED,
                sink_target="hii/clusters/never-created#关键结论",
            )
        ],
    )
    report = apply_meeting_review(vault, work, apply=True, now=datetime(2026, 9, 14, tzinfo=UTC))
    assert report.applied == 0
    assert any(action.reason and "写回目标不存在" in action.reason for action in report.actions)


# ---- T3：写回前拒绝重复目标标题与无法解析的 anchor ----


def test_append_knowledge_note_rejects_duplicate_target_block(tmp_path: Path) -> None:
    """重复区块标题会让「写回哪一节」不确定；必须拒批，且不动页面。"""
    vault = tmp_path / "vault"
    page = vault / "hii" / "clusters" / "dup.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ndate: 2026-09-14\ntype: note\nstatus: active\n---\n\n"
        "# 重复区块\n\n## 关键结论\n\na\n\n## 关键结论\n\nb\n",
        encoding="utf-8",
    )
    before = page.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="重复区块标题"):
        append_knowledge_note(vault, "hii/clusters/dup#关键结论", "新结论ABC", "m:n#decision-0")
    assert page.read_text(encoding="utf-8") == before  # 失败不留下部分修改


@pytest.mark.parametrize(
    "bad",
    [
        "hii/clusters/x#a#b",  # 多余的 # ⇒ 拼不出合法标题
        "hii/clusters/x#关键#结论",
        "hii/clusters/x\n#关键结论",  # 目标里夹换行
    ],
)
def test_parse_sink_target_rejects_unparseable_anchor(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_sink_target(bad)
