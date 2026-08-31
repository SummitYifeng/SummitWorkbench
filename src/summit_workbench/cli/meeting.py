"""``wb meeting`` 子命令：会议发现与原文归档（M1-2）。

- ``archive``：飞书主链路。按会议号 + 时间范围发现会议，对有 note_id 者取回完整逐字稿，
  在模型调用之前落盘证据层；幂等防重，重复运行不产生重复归档。
- ``archive-local``：本地兜底。把一份本地逐字稿文件归档为证据层（Note 不可用时）。

结构化处理（模型调用）属 M1-3，本组命令只负责「先证据、后建议」的证据侧。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.providers.feishu import (
    FeishuClient,
    FeishuConfig,
    FeishuError,
    FeishuNoteSource,
    FeishuSession,
    list_meetings_by_no,
    load_feishu_config,
)
from summit_workbench.providers.feishu.meetings import MeetingSummary
from summit_workbench.workflows.meetings import (
    ArchiveReport,
    DiscoveredMeeting,
    archive_meeting,
)

meeting_app = typer.Typer(
    name="meeting",
    help="会议发现与原文归档（archive / archive-local）。",
    no_args_is_help=True,
    add_completion=False,
)


def _config() -> FeishuConfig:
    try:
        return load_feishu_config()
    except FeishuError as exc:
        typer.echo(f"配置错误：{exc}")
        raise typer.Exit(code=2) from exc


def _vault_dir() -> Path:
    return load_settings().work_paths().vault_dir


def _tz() -> ZoneInfo:
    return ZoneInfo(load_settings().timezone)


def _date_of(start_time: str | None, tz: ZoneInfo) -> str:
    """把飞书会议开始时间（unix 秒字符串）转成配置时区下的 YYYY-MM-DD；缺失则用今天。"""
    if start_time and start_time.isdigit():
        return datetime.fromtimestamp(int(start_time), tz).strftime("%Y-%m-%d")
    return datetime.now(tz).strftime("%Y-%m-%d")


def _echo_report(meeting_label: str, report: ArchiveReport) -> None:
    icon = {"archived": "✓", "skipped-existing": "•", "unavailable": "⚠"}.get(report.action, "?")
    detail = f"  状态={report.state.value}  key={report.idem_key}"
    if report.path is not None:
        detail += f"\n    → {report.path}"
    if report.reason:
        detail += f"\n    原因：{report.reason}"
    typer.echo(f"{icon} {meeting_label}  [{report.action}]{detail}")


@meeting_app.command("archive")
def archive(
    meeting_no: str = typer.Option(..., "--meeting-no", help="9 位会议号（Feishu 会议里可见）。"),
    since: str = typer.Option(..., "--since", help="起始日期 YYYY-MM-DD。"),
    until: str = typer.Option(..., "--until", help="结束日期 YYYY-MM-DD（含当天）。"),
    project: list[str] = typer.Option(
        [], "--project", help="已知关联项目（可多次）；不给则留 unresolved 待模型识别。"
    ),
) -> None:
    """飞书主链路：发现会议 → 取回完整逐字稿 → 模型调用前落盘证据层（幂等）。"""
    cfg = _config()
    meeting_no = meeting_no.replace(" ", "")
    tz = _tz()
    try:
        start = int(datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=tz).timestamp())
        end_dt = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)
        end = int(end_dt.timestamp()) - 1
    except ValueError as exc:
        typer.echo("日期格式应为 YYYY-MM-DD")
        raise typer.Exit(code=2) from exc

    client = FeishuClient(cfg, FeishuSession(cfg).tenant_access_token())
    note_source = FeishuNoteSource(client)

    try:
        found = list_meetings_by_no(client, meeting_no, start, end)
    except FeishuError as exc:
        typer.echo(f"✗ 列会议失败：{exc}")
        raise typer.Exit(code=1) from exc

    if not found:
        typer.echo(f"会议号 {meeting_no} 在 {since}~{until} 内没有会议")
        raise typer.Exit(code=0)

    vault_dir = _vault_dir()
    projects = list(project) or None

    def fetch(m: DiscoveredMeeting) -> str:
        assert m.note_id is not None  # 无 note_id 的会议不会进入取稿分支
        return note_source.fetch_transcript(m.note_id).text

    failures = 0
    for summary in found:
        meeting = _to_discovered(summary, tz)
        label = summary.topic or "(无主题)"
        try:
            report = archive_meeting(vault_dir, meeting, fetch, projects=projects)
        except FeishuError as exc:
            failures += 1
            typer.echo(f"✗ {label}  取稿失败（可稍后重试）：{exc}")
            continue
        _echo_report(label, report)

    if failures:
        raise typer.Exit(code=1)


@meeting_app.command("archive-local")
def archive_local(
    file: Path = typer.Argument(..., help="本地逐字稿文件路径（Note API 不可用时的兜底）。"),
    title: str = typer.Option(..., "--title", help="会议标题（用于文件名与笔记标题）。"),
    date: str = typer.Option(..., "--date", help="会议日期 YYYY-MM-DD。"),
    meeting_id: str = typer.Option(
        "", "--meeting-id", help="可选：为该逐字稿指定稳定会议 ID（无则按内容哈希防重）。"
    ),
    project: list[str] = typer.Option([], "--project", help="已知关联项目（可多次）。"),
) -> None:
    """本地兜底：把一份本地逐字稿文件归档为证据层（不联网、不做结构化）。"""
    if not file.is_file():
        typer.echo(f"文件不存在：{file}")
        raise typer.Exit(code=2)
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        typer.echo("日期格式应为 YYYY-MM-DD")
        raise typer.Exit(code=2) from exc

    text = file.read_text(encoding="utf-8")
    if not text.strip():
        typer.echo(f"逐字稿文件为空：{file}")
        raise typer.Exit(code=2)

    meeting = DiscoveredMeeting(
        title=title,
        date=date,
        source=SourceKind.LOCAL_FILE,
        meeting_id=meeting_id or None,
    )
    report = archive_meeting(
        _vault_dir(), meeting, lambda _m: text, projects=list(project) or None
    )
    _echo_report(title, report)


def _to_discovered(summary: MeetingSummary, tz: ZoneInfo) -> DiscoveredMeeting:
    return DiscoveredMeeting(
        title=summary.topic or "(无主题)",
        date=_date_of(summary.start_time, tz),
        source=SourceKind.FEISHU_NOTE,
        meeting_id=summary.meeting_id,
        note_id=summary.note_id,
    )
