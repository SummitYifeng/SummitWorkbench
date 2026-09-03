"""周复盘信号采集（M2-10）：从 git + 会议笔记 + inbox + 项目状态重新汇总。

**offline-first**：本周完成来自各项目 git 提交，关键决策来自本周会议笔记的
``## 已形成决策``，未闭合来自项目/全局 inbox 与待确认积压，停滞项目 = 本周零提交的 git 项目
+ 长期无内容更新但仍有未决/未闭环跟进的线程（P3）。逐源隔离，失败转 ``source_notes``。
飞书已完成任务可作为可选事实补充（传入）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from summit_workbench.domain.brief import EvidenceLevel
from summit_workbench.domain.weekly import WeeklyItem, WeeklySignals
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.project_scan import (
    count_inbox_pending,
    scan_projects,
    thread_projects,
)
from summit_workbench.repositories.project_view import project_archive_state
from summit_workbench.repositories.vault import load_note

# 线程内容停滞阈值（天）：超过该天数无任何内容更新（档案 frontmatter updated）且仍有
# 阻塞/未闭环跟进时，周复盘在「停滞项目」点名——与首页卡「>14 天未更新」提示同口径。
THREAD_STALL_DAYS = 14


def extract_section_bullets(body: str, heading: str) -> list[str]:
    """取 ``## <heading>`` 区块下的条目文本（去列表/复选框前缀），到下一个 ``## `` 止。"""
    out: list[str] = []
    in_section = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip() == heading
            continue
        if in_section and stripped:
            text = stripped
            for prefix in ("- [ ] ", "- [x] ", "- ", "* "):
                if text.startswith(prefix):
                    text = text[len(prefix) :]
                    break
            if text.strip():
                out.append(text.strip())
    return out


def _in_week(day_value: object, start_iso: str, end_iso: str) -> bool:
    """判断笔记 frontmatter 的 date 是否落在周内。YAML 可能已把 date 解析为 date 对象。"""
    if isinstance(day_value, date):  # datetime 是 date 子类，一并覆盖
        day_iso = day_value.isoformat()[:10]
    elif isinstance(day_value, str):
        day_iso = day_value[:10]
    else:
        return False
    return start_iso <= day_iso <= end_iso


def _collect_commits(
    signals: WeeklySignals, work_root: Path, vault_dir: Path, start_iso: str, end_iso: str
) -> list[str]:
    """各项目本周 git 提交 → 完成项；返回本周有提交的项目名（用于判定停滞）。"""
    active: list[str] = []
    for project in scan_projects(work_root, vault_dir):
        if not project.is_git:
            continue
        try:
            commits = GitRepo(project.path).commits_between(start_iso, end_iso)
        except GitError as exc:
            signals.source_notes.append(f"{project.name} git log 失败（{exc.stderr or exc}）")
            continue
        if commits:
            active.append(project.name)
        for sha, subject in commits:
            signals.completed.append(
                WeeklyItem(
                    text=subject,
                    source_ref=f"{project.name}@{sha}",
                    evidence=EvidenceLevel.E2,
                    project=project.name,
                )
            )
        # 停滞：git 项目本周零提交。
        if not commits:
            signals.stalled.append(
                WeeklyItem(
                    text=f"{project.name}（本周无提交）",
                    source_ref=str(project.path),
                    evidence=EvidenceLevel.E2,
                    project=project.name,
                )
            )
        if project.inbox_pending > 0:
            signals.unclosed.append(
                WeeklyItem(
                    text=f"{project.name} inbox 待处理 {project.inbox_pending} 条",
                    source_ref=f"{project.name}/inbox.md",
                    evidence=EvidenceLevel.E2,
                    project=project.name,
                )
            )
    return active


def _collect_meeting_decisions(
    signals: WeeklySignals, vault_dir: Path, start_iso: str, end_iso: str
) -> None:
    """本周会议笔记的 ``## 已形成决策`` → 关键决策（附来源）。"""
    notes_dir = vault_dir / "meetings" / "notes"
    if not notes_dir.is_dir():
        return
    for path in sorted(notes_dir.glob("*.md")):
        note = load_note(path)
        if note.parse_error is not None:
            continue
        if not _in_week(note.meta.get("date"), start_iso, end_iso):
            continue
        rel = f"meetings/notes/{path.name}"
        for decision in extract_section_bullets(note.body, "已形成决策"):
            signals.decisions.append(
                WeeklyItem(text=decision, source_ref=rel, evidence=EvidenceLevel.E2)
            )


def _collect_global_inbox(signals: WeeklySignals, vault_dir: Path) -> None:
    inbox = vault_dir / "inbox.md"
    if inbox.is_file():
        pending = count_inbox_pending(inbox.read_text(encoding="utf-8"))
        if pending > 0:
            signals.unclosed.append(
                WeeklyItem(
                    text=f"全局 inbox 待处理 {pending} 条",
                    source_ref="inbox.md",
                    evidence=EvidenceLevel.E2,
                )
            )


def _thread_stall_reason(blocked: str | None, followup_open: list[str]) -> tuple[str, str]:
    """线程停滞的「原因摘要 + 档案锚点」：阻塞/未闭环跟进都算未决（P3 内容停滞）。

    返回 ``(reason, anchor)``；reason 用于条目文案，anchor 指向档案中对应区块。
    """
    parts: list[str] = []
    if blocked:
        parts.append(f"阻塞：{blocked}")
    if followup_open:
        parts.append(f"{len(followup_open)} 条跟进待闭环")
    anchor = "#跟进事项" if followup_open else "#阻塞"
    return "；".join(parts) or "有未决事项", anchor


def _collect_thread_stalls(
    signals: WeeklySignals, vault_dir: Path, work_root: Path, end_iso: str
) -> None:
    """线程内容停滞点名（P3）：N 天无内容更新但仍有未决/未闭环跟进 → 停滞项目。

    线程没有 git，本周零提交的检测覆盖不到它们；改用档案 frontmatter ``updated``
    判停滞：距复盘周截止日超过 :data:`THREAD_STALL_DAYS` 天无更新，且档案仍有
    阻塞/未闭环跟进（``project_archive_state``）时，周复盘点名。仅 active 线程；
    archived 已退出工作台、不点名。
    """
    end = date.fromisoformat(end_iso)
    for project in thread_projects(vault_dir, work_root):
        if project.status != "active" or not project.updated:
            continue
        try:
            updated = date.fromisoformat(project.updated)
        except ValueError:
            continue  # updated 非法（非 YYYY-MM-DD）：无法判停滞，跳过
        days = (end - updated).days
        if days <= THREAD_STALL_DAYS:
            continue
        blocked, followup_open = project_archive_state(vault_dir, project.name)
        if blocked is None and not followup_open:
            continue  # 无未决/未闭环跟进：不点名（干净线程可由生命周期提示自行归档）
        reason, anchor = _thread_stall_reason(blocked, followup_open)
        signals.stalled.append(
            WeeklyItem(
                text=f"{project.name}（{days} 天无更新，{reason}）",
                source_ref=f"projects/{project.name}.md{anchor}",
                evidence=EvidenceLevel.E2,
                project=project.name,
            )
        )


def collect_weekly(
    work_root: Path,
    vault_dir: Path,
    *,
    start_iso: str,
    end_iso: str,
    pending_review_count: int = 0,
    completed_tasks: list[WeeklyItem] | None = None,
) -> WeeklySignals:
    """采集上一自然周的全部复盘信号（去重与分区交给 domain.build_review）。"""
    signals = WeeklySignals()

    _collect_commits(signals, work_root, vault_dir, start_iso, end_iso)
    _collect_thread_stalls(signals, vault_dir, work_root, end_iso)
    _collect_meeting_decisions(signals, vault_dir, start_iso, end_iso)
    _collect_global_inbox(signals, vault_dir)

    if pending_review_count > 0:
        signals.unclosed.append(
            WeeklyItem(
                text=f"会议提取结果待确认 {pending_review_count} 条",
                source_ref="review/meetings.md",
                evidence=EvidenceLevel.E2,
            )
        )
    if completed_tasks:
        signals.completed.extend(completed_tasks)

    return signals
