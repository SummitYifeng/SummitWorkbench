"""周复盘信号采集（M2-10）：从 git + 会议笔记 + inbox + 项目状态重新汇总。

**offline-first**：本周完成来自各项目 git 提交，关键决策来自本周会议笔记的
``## 已形成决策``，未闭合来自项目/全局 inbox 与待确认积压，停滞项目 = 本周零提交的 git 项目。
逐源隔离，失败转 ``source_notes``。飞书已完成任务可作为可选事实补充（传入）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from summit_workbench.domain.brief import EvidenceLevel
from summit_workbench.domain.weekly import WeeklyItem, WeeklySignals
from summit_workbench.repositories.git import GitError, GitRepo
from summit_workbench.repositories.project_scan import count_inbox_pending, scan_projects
from summit_workbench.repositories.vault import load_note


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


def _collect_commits(signals: WeeklySignals, work_root: Path, vault_dir: Path,
                     start_iso: str, end_iso: str) -> list[str]:
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


def _collect_meeting_decisions(signals: WeeklySignals, vault_dir: Path,
                               start_iso: str, end_iso: str) -> None:
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
