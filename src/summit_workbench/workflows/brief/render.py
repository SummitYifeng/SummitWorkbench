"""简报 Markdown 渲染（M2-5 + M2-9）。

版式（PRD 3.4）：首行健康度 → 事实区（原文直取）→ 需要行动（≤5，附分组标签与依据）→
提议区（E3，附依据）→ 最近完成（精简）。渲染是纯函数：同 :class:`Brief` 同输出，
事实区逐字来自采集，便于 G1 回归比对。
"""

from __future__ import annotations

from summit_workbench.domain.brief import CATEGORY_LABELS, ActionSignal, Brief

_EVIDENCE_BADGES = {"E1": "✅已完成", "E2": "🔧进行中", "E3": "💭待确认"}


def _evidence_badge(evidence_value: str) -> str:
    return _EVIDENCE_BADGES.get(evidence_value, evidence_value)


def _ref_link(source_ref: str) -> str:
    """把依据渲染成可核查引用。vault 内路径转 wiki 链接，其余原样反引号包裹。"""
    if source_ref.endswith(".md") or ".md#" in source_ref or source_ref.startswith("projects/"):
        return f"[[{source_ref}]]"
    return f"`{source_ref}`"


def _render_action(index: int, action: ActionSignal, group_label: str) -> str:
    badge = _evidence_badge(action.evidence.value)
    due = f" ｜截止 {action.due_date}" if action.due_date else ""
    return (
        f"{index}. [{group_label}] {action.title}{due} "
        f"（{badge}） — 依据 {_ref_link(action.source_ref)}"
    )


def render_brief(brief: Brief, groups: dict[str, str]) -> str:
    """渲染简报正文（不含锚点，交给 daily_note 包裹）。"""
    lines: list[str] = [f"# 晨间简报 {brief.date}", "", brief.health.line(), ""]

    # —— 事实区 ——
    lines.append("## 事实区")
    lines.append("")
    lines.append("### 今日会议")
    if brief.meetings:
        for m in brief.meetings:
            lines.append(f"- {m.start_time} · {m.title}")
    else:
        lines.append("- （今日无会议）")
    lines.append("")
    lines.append("### 待办任务")
    if brief.tasks:
        for t in brief.tasks:
            due = f"（截止 {t.due_date}）" if t.due_date else "（无截止）"
            lines.append(f"- {t.summary} {due}")
    else:
        lines.append("- （无待办任务）")
    if brief.pending_review_count > 0:
        lines.append("")
        lines.append(
            f"> ⏳ 另有 **{brief.pending_review_count}** 条会议提取结果待确认"
            "（见 `review/meetings.md`，未确认内容不计入事实）"
        )
    lines.append("")

    # —— 需要行动（≤5）——
    lines.append(f"## 需要行动（{len(brief.actions)}/5）")
    lines.append("")
    if brief.actions:
        for i, action in enumerate(brief.actions, start=1):
            label = groups.get(action.signal_id) or CATEGORY_LABELS.get(
                action.category, action.category.value
            )
            lines.append(_render_action(i, action, label))
    else:
        lines.append("- （今日无需要行动的信号）")
    lines.append("")

    # —— 提议区（E3，附依据）——
    if brief.proposals:
        lines.append("## 提议区（AI 建议，非事实）")
        lines.append("")
        for p in brief.proposals:
            lines.append(f"- {p.title} — 依据 {_ref_link(p.source_ref)}")
        lines.append("")

    # —— 最近完成（精简）——
    lines.append("## 最近完成")
    lines.append("")
    if brief.completions:
        for c in brief.completions:
            lines.append(f"- {c.text} — {_ref_link(c.source_ref)}")
    else:
        lines.append("- （近期无已完成条目）")

    return "\n".join(lines).rstrip() + "\n"
