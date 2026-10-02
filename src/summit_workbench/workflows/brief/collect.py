"""信号采集（M2-1 + M2-2）：逐源隔离地汇总事实、行动候选与最近完成。

**单源失败不阻断其余来源**（PRD §7.1）：飞书日历/任务与本地项目扫描各自 try/except，
失败只记入 ``source_failures`` 并降级，绝不让整份简报失败。

**事实区原文直取**（G1=0）：会议标题/时间、任务名/截止、git 状态、inbox 计数直接来自
飞书原始响应与文件系统。日期/时间的格式化是**确定性变换**（同输入同输出），不经模型。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from summit_workbench.domain.brief import (
    ActionCategory,
    ActionSignal,
    CollectedSignals,
    CompletionItem,
    EvidenceLevel,
    MeetingFact,
    TaskFact,
)
from summit_workbench.providers.feishu.calendar import CalendarEvent
from summit_workbench.providers.feishu.tasks import TaskItem
from summit_workbench.repositories.project_scan import (
    ProjectState,
    scan_all_projects,
)
from summit_workbench.repositories.project_view import project_archive_state


class FactsSource(Protocol):
    """飞书事实来源的结构化协议（便于测试注入，隔离网络）。

    每个方法失败时应抛异常；采集层负责逐源兜底。
    """

    def meetings(self) -> list[CalendarEvent]: ...
    def open_tasks(self) -> list[TaskItem]: ...
    def completed_tasks(self) -> list[TaskItem]: ...


def format_event_time(event: CalendarEvent, timezone: str) -> str:
    """把事件起始时间确定性地格式化为展示串（全天/HH:MM）；非法则原样返回。"""
    if event.is_all_day:
        return f"全天 {event.start_time}"
    try:
        moment = datetime.fromtimestamp(int(event.start_time), tz=ZoneInfo(timezone))
    except (ValueError, OSError):
        return event.start_time
    return moment.strftime("%H:%M")


def _meeting_facts(events: list[CalendarEvent], timezone: str) -> list[MeetingFact]:
    facts: list[MeetingFact] = []
    for e in events:
        display = format_event_time(e, timezone)
        start_ts = e.start_time if not e.is_all_day else None
        end_ts = e.end_time if (e.end_time and not e.is_all_day) else None
        facts.append(
            MeetingFact(
                title=e.title,
                start_time=display,
                event_id=e.event_id or None,
                start_ts=start_ts,
                end_ts=end_ts,
            )
        )
    return facts


def _task_facts(tasks: list[TaskItem]) -> list[TaskFact]:
    return [TaskFact(summary=t.summary, due_date=t.due_date, task_id=t.guid) for t in tasks]


def _commitment_signals(tasks: list[TaskItem]) -> list[ActionSignal]:
    """有截止日期的未完成任务 → 近期承诺候选（承诺不能丢）。"""
    signals: list[ActionSignal] = []
    for t in tasks:
        if t.due_date is None:
            continue
        signals.append(
            ActionSignal(
                signal_id=f"task-{t.guid}",
                title=t.summary,
                category=ActionCategory.COMMITMENT,
                evidence=EvidenceLevel.E2,
                source_ref=f"feishu-task:{t.guid}",
                due_date=t.due_date,
            )
        )
    return signals


def _completion_items(tasks: list[TaskItem]) -> list[CompletionItem]:
    """已完成任务 → 最近完成（E1，机器可验证闭合）。"""
    return [CompletionItem(text=t.summary, source_ref=f"feishu-task:{t.guid}") for t in tasks]


def _project_signals(project: ProjectState) -> list[ActionSignal]:
    """把一个项目的离线状态映射为行动候选：主线推进 + 至多一条防止停摆。"""
    signals: list[ActionSignal] = []

    # 主线推进：主笔记「下一步」。
    if project.next_step and project.next_step_ref:
        signals.append(
            ActionSignal(
                signal_id=f"next-{project.name}",
                title=project.next_step,
                category=ActionCategory.MAIN_PUSH,
                evidence=EvidenceLevel.E2,  # 主笔记明确状态更新（L26）
                source_ref=project.next_step_ref,
                project=project.name,
            )
        )

    # 防止停摆只依据工作库中明确记录的待处理输入。
    stall = _anti_stall_signal(project)
    if stall is not None:
        signals.append(stall)
    return signals


def _anti_stall_signal(project: ProjectState) -> ActionSignal | None:
    name = project.name
    if project.inbox_pending > 0:
        return ActionSignal(
            signal_id=f"stall-{name}-inbox",
            title=f"清理 {name} inbox（{project.inbox_pending} 条待处理）",
            category=ActionCategory.ANTI_STALL,
            evidence=EvidenceLevel.E2,
            source_ref=f"{name}/inbox.md",
            project=name,
            detail=f"{project.inbox_pending} 条 inbox 待处理",
        )
    return None


def _thread_extra_signals(vault_dir: Path, project: ProjectState) -> list[ActionSignal]:
    """知识线程（及带档案的仓库项目）的内容信号：阻塞 → 防停摆；未闭环跟进 → 主线推进。

    仓库项目以 git 状态为主、内容信号为补充；线程项目没有 git，内容信号就是它的
    「推进/停摆」事实来源。只对已建档且 active 的项目取档案内容。
    """
    if not project.registered or project.status != "active":
        return []
    blocked, followup_open = project_archive_state(vault_dir, project.name)
    # 2026-09-14：信号标题是直接给使用者看的，用档案里的中文显示名（`title`），
    # 不用项目 ID——否则简报上会出现「hii-affairs 阻塞：…」这种中英混杂（真实数据验证发现）。
    display = (project.title or "").strip() or project.name
    signals: list[ActionSignal] = []
    if blocked:
        signals.append(
            ActionSignal(
                signal_id=f"block-{project.name}",
                title=f"{display} 阻塞：{blocked}",
                category=ActionCategory.ANTI_STALL,
                evidence=EvidenceLevel.E2,
                source_ref=f"projects/{project.name}.md#阻塞",
                project=project.name,
            )
        )
    if followup_open:
        signals.append(
            ActionSignal(
                signal_id=f"follow-{project.name}",
                title=f"跟进 {display}：{followup_open[0]}",
                category=ActionCategory.MAIN_PUSH,
                evidence=EvidenceLevel.E2,
                source_ref=f"projects/{project.name}.md#跟进事项",
                project=project.name,
                detail=f"共 {len(followup_open)} 条待闭环跟进"
                if len(followup_open) > 1
                else "他人承诺待闭环",
            )
        )
    return signals


def collect_signals(
    work_root: Path,
    vault_dir: Path,
    *,
    timezone: str,
    facts_source: FactsSource | None,
    pending_review_count: int = 0,
) -> CollectedSignals:
    """采集当日全部信号。``facts_source`` 为 None 时跳过飞书（纯本地降级）。"""
    collected = CollectedSignals(pending_review_count=pending_review_count)

    # —— 飞书日历（今日会议）——
    if facts_source is not None:
        try:
            events = facts_source.meetings()
            collected.meetings.extend(_meeting_facts(events, timezone))
        except Exception as exc:  # noqa: BLE001 - 逐源隔离，转成可见降级
            collected.source_failures.append(f"飞书日历（{type(exc).__name__}）")

        # —— 飞书任务（待办 + 最近完成）——
        try:
            open_tasks = facts_source.open_tasks()
            collected.tasks.extend(_task_facts(open_tasks))
            collected.candidates.extend(_commitment_signals(open_tasks))
        except Exception as exc:  # noqa: BLE001
            collected.source_failures.append(f"飞书任务（{type(exc).__name__}）")

        try:
            done = facts_source.completed_tasks()
            collected.completions.extend(_completion_items(done))
        except Exception as exc:  # noqa: BLE001
            collected.source_failures.append(f"飞书已完成任务（{type(exc).__name__}）")
    else:
        collected.source_failures.append("飞书未配置（纯本地降级）")

    # —— 本地项目全集扫描（仓库项目 + 知识线程）——
    # scan_all_projects 内部已把 git 失败转成 project.git_error。
    try:
        for project in scan_all_projects(work_root, vault_dir):
            # 已归档项目不产生行动信号（退出工作台 = 不再推进提醒）。
            if project.status != "archived":
                collected.candidates.extend(_project_signals(project))
                collected.candidates.extend(_thread_extra_signals(vault_dir, project))
            if project.git_error:
                collected.source_failures.append(f"{project.name} git（{project.git_error}）")
    except OSError as exc:
        collected.source_failures.append(f"本地项目扫描（{type(exc).__name__}）")

    return collected
