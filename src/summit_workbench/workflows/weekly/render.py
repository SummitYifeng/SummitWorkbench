"""周复盘 Markdown 渲染（M2-10）。事实区各条附来源；下周建议单列为提议区。"""

from __future__ import annotations

from summit_workbench.domain.weekly import WeeklyItem, WeeklyReview


def _ref(source_ref: str) -> str:
    """vault 内路径转 wiki 链接；git 引用/绝对路径等原样反引号包裹。"""
    if source_ref.endswith(".md") or ".md#" in source_ref:
        return f"[[{source_ref}]]"
    return f"`{source_ref}`"


def _section(title: str, items: tuple[WeeklyItem, ...], empty: str) -> list[str]:
    lines = [f"## {title}", ""]
    if items:
        for it in items:
            proj = f"[{it.project}] " if it.project else ""
            lines.append(f"- {proj}{it.text} — {_ref(it.source_ref)}")
    else:
        lines.append(f"- （{empty}）")
    lines.append("")
    return lines


def render_weekly(review: WeeklyReview) -> str:
    """渲染周复盘正文（不含 frontmatter，交给 repository 包裹）。"""
    lines: list[str] = [
        f"# 周复盘 {review.week}",
        "",
        f"范围：{review.start} ~ {review.end}（周一至周日）",
        "",
    ]
    if review.source_notes:
        lines.append("> ⚠ 采集提示：" + "；".join(review.source_notes))
        lines.append("")

    lines += _section("本周完成", review.completed, "本周无可追溯的完成项")
    lines += _section("关键决策", review.decisions, "本周会议未记录明确决策")
    lines += _section("未闭合信号", review.unclosed, "无未闭合信号")
    lines += _section("停滞项目", review.stalled, "无停滞项目")

    lines.append("## 下周建议（AI 建议，非事实）")
    lines.append("")
    if review.proposals:
        for p in review.proposals:
            proj = f"[{p.project}] " if p.project else ""
            lines.append(f"- {proj}{p.text} — 依据 {_ref(p.source_ref)}")
    else:
        lines.append("- （暂无建议）")

    return "\n".join(lines).rstrip() + "\n"
