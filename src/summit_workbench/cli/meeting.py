"""``wb meeting`` 子命令：会议归档与云端结构化处理（M1-2/M1-3）。

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

from summit_workbench.config.secrets import CredentialError, resolve_credential
from summit_workbench.config.settings import default_config_file, load_settings
from summit_workbench.domain.pipeline import SourceKind
from summit_workbench.observability.status import load_budget_settings
from summit_workbench.prompts import load_prompt
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
from summit_workbench.providers.llm import LLMError, load_model_config
from summit_workbench.repositories.usage_ledger import monthly_totals
from summit_workbench.workflows.meetings import (
    ArchiveReport,
    DiscoveredMeeting,
    archive_meeting,
    process_archived_transcript,
)
from summit_workbench.workflows.meetings.backfill import (
    MAX_TRANSCRIPT_BYTES,
    oversized_transcripts,
    plan_backfill,
    run_backfill,
    scan_for_import,
    scan_local_transcripts,
)

meeting_app = typer.Typer(
    name="meeting",
    help="会议归档与结构化处理（archive / archive-local / import / process / backfill）。",
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


def _warn_oversized(source: Path) -> None:
    """显式列出被体积上限跳过的逐字稿。

    静默跳过会使用户以为已经导入，所以这里必须说话。上限由 workflow 层统一执行
    （``MAX_TRANSCRIPT_BYTES``），web 抽屉与 CLI 共用同一数值。
    """
    oversized = oversized_transcripts(source)
    if not oversized:
        return
    limit_mib = MAX_TRANSCRIPT_BYTES // (1024 * 1024)
    typer.echo(f"⚠ 已跳过 {len(oversized)} 个超过 {limit_mib} MiB 的逐字稿（未送模型）：")
    for path in oversized:
        size_mib = path.stat().st_size / (1024 * 1024)
        typer.echo(f"    {path.name}（{size_mib:.1f} MiB）")


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
    report = archive_meeting(_vault_dir(), meeting, lambda _m: text, projects=list(project) or None)
    _echo_report(title, report)


@meeting_app.command("import")
def import_transcripts(
    source: Path = typer.Argument(..., help="本地逐字稿文件或目录（.md/.txt，带讲话人+时间戳）。"),
    include_actions: bool = typer.Option(
        False, "--include-actions", help="同时生成审批候选（默认只沉淀知识）。"
    ),
    yes: bool = typer.Option(False, "--yes", help="跳过开始前的费用确认。"),
    force_budget: bool = typer.Option(
        False, "--force-budget", help="即使预计跨越月度软预算也继续。"
    ),
) -> None:
    """「妙记按需 + 手动兜底」常态入口：把手动下载的逐字稿一条命令归档+结构化。

    无需日期区间；日期取 frontmatter/文件名前缀，缺失回退文件修改日期。幂等可续跑。
    文件名建议 ``YYYY-MM-DD-会议标题.txt``（标题用于笔记标题与去重展示）。
    """
    if not source.exists():
        typer.echo(f"来源不存在：{source}")
        raise typer.Exit(code=2)
    vault_dir = _vault_dir()
    _warn_oversized(source)
    try:
        cfg = load_model_config("meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"✗ 导入未启动：{exc}")
        raise typer.Exit(code=2) from exc

    items = scan_for_import(vault_dir, source)
    if not items:
        typer.echo(f"未发现可导入的逐字稿（.md/.txt）：{source}")
        raise typer.Exit(code=0)

    month = datetime.now(_tz()).strftime("%Y-%m")
    month_spent = monthly_totals(vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(default_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)
    typer.echo(
        f"待导入 {est.pending} 场（已存在跳过 {est.already_done} 场）；"
        f"预估输入 {est.est_input_tokens} / 输出 {est.est_output_tokens} token，"
        f"约 {est.est_cost} {est.currency}。"
    )
    if est.pending == 0:
        typer.echo("• 全部已导入，幂等空转。")
        raise typer.Exit(code=0)
    if not yes:
        typer.confirm(f"开始导入 {est.pending} 场？", abort=True)
    if est.crosses_soft_budget and not force_budget:
        typer.confirm("⚠ 预计将跨越本月软预算，仍继续？", abort=True)

    report = run_backfill(
        vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=include_actions,
    )
    typer.echo(
        f"✓ 导入完成：处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}"
        + (f"、生成候选 {report.candidates}" if include_actions else "")
    )
    for result in report.results:
        prefix = "✗" if result.action == "failed" else "•"
        detail = f"：{result.reason}" if result.reason else ""
        typer.echo(f"  {prefix} {result.item.date} {result.item.title}{detail}")
    if report.failed:
        raise typer.Exit(code=1)


@meeting_app.command("process")
def process(
    transcript_file: Path = typer.Argument(..., help="已归档的 meeting-transcript Markdown。"),
    task_key: str = typer.Option(
        "", "--task-key", help="可选；旧本地归档缺少 idem_key 时显式指定状态账本键。"
    ),
) -> None:
    """把已归档逐字稿可靠处理为结构化会议笔记；失败进入错误队列。"""
    if not transcript_file.is_file():
        typer.echo(f"逐字稿文件不存在：{transcript_file}")
        raise typer.Exit(code=2)
    try:
        cfg = load_model_config("meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
        report = process_archived_transcript(
            _vault_dir(),
            transcript_file,
            cfg,
            api_key,
            prompt=prompt,
            merger_prompt=merger_prompt,
            task_key=task_key or None,
        )
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"✗ 结构化处理未启动：{exc}")
        raise typer.Exit(code=2) from exc

    if report.action == "failed":
        typer.echo(f"✗ 模型处理失败，原文已保留：{report.reason}")
        typer.echo(f"  错误队列：{report.error_path}")
        raise typer.Exit(code=1)
    if report.action == "skipped-existing":
        typer.echo(f"• 已处理，幂等空转：{report.task_key}（{report.state.value}）")
        raise typer.Exit(code=0)
    typer.echo(f"✓ 结构化会议笔记已生成：{report.note_path}")
    typer.echo(
        f"  状态={report.state.value}  分段={report.chunks}  成功模型调用={report.model_calls}"
    )


@meeting_app.command("backfill")
def backfill(
    source: Path = typer.Argument(..., help="本地逐字稿目录或单个文件。"),
    since: str = typer.Option(..., "--since", help="补导起始日期 YYYY-MM-DD（含）。"),
    until: str = typer.Option(..., "--until", help="补导结束日期 YYYY-MM-DD（含）。"),
    include_actions: bool = typer.Option(
        False, "--include-actions", help="同时生成带 historical 标记的审批候选（默认只沉淀知识）。"
    ),
    yes: bool = typer.Option(False, "--yes", help="跳过开始前的确认。"),
    force_budget: bool = typer.Option(
        False, "--force-budget", help="即使预计跨越月度软预算也继续（否则需再次确认）。"
    ),
) -> None:
    """按显式日期范围补导本地逐字稿：先预估费用，确认后逐场处理，可中断续跑。"""
    for label, value in (("--since", since), ("--until", until)):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            typer.echo(f"{label} 格式应为 YYYY-MM-DD")
            raise typer.Exit(code=2) from exc
    if not source.exists():
        typer.echo(f"来源不存在：{source}")
        raise typer.Exit(code=2)

    vault_dir = _vault_dir()
    _warn_oversized(source)
    try:
        cfg = load_model_config("meeting")
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("meeting-processor")
        merger_prompt = load_prompt("meeting-merger")
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"✗ 补导未启动：{exc}")
        raise typer.Exit(code=2) from exc

    items = scan_local_transcripts(vault_dir, source, since=since, until=until)
    if not items:
        typer.echo(f"区间 [{since}, {until}] 内没有可补导的本地逐字稿。")
        raise typer.Exit(code=0)

    month = datetime.now(_tz()).strftime("%Y-%m")
    month_spent = monthly_totals(vault_dir, month).estimated_cost
    soft_limit, _currency = load_budget_settings(default_config_file())
    est = plan_backfill(items, cfg, month_spent=month_spent, soft_limit=soft_limit)

    typer.echo(
        f"待补导 {est.pending} 场（已存在跳过 {est.already_done} 场）；"
        f"预估输入 {est.est_input_tokens} / 输出 {est.est_output_tokens} token，"
        f"约 {est.est_cost} {est.currency}。"
    )
    if soft_limit is not None:
        typer.echo(
            f"本月已用 {est.month_spent} {est.currency}，预计累计 {est.projected_month_cost} "
            f"/ 软预算 {soft_limit} {est.currency}。"
        )
    if est.pending == 0:
        typer.echo("• 全部已补导，幂等空转。")
        raise typer.Exit(code=0)

    if not yes:
        typer.confirm(f"开始补导 {est.pending} 场？", abort=True)
    if est.crosses_soft_budget and not force_budget:
        typer.confirm("⚠ 预计将跨越本月软预算，仍继续？", abort=True)

    report = run_backfill(
        vault_dir,
        items,
        cfg,
        api_key,
        prompt=prompt,
        merger_prompt=merger_prompt,
        include_actions=include_actions,
    )
    typer.echo(
        f"✓ 补导完成：处理 {report.processed}、跳过 {report.skipped}、失败 {report.failed}"
        + (f"、生成候选 {report.candidates}" if include_actions else "")
    )
    for result in report.results:
        if result.action == "failed":
            typer.echo(f"  ✗ {result.item.date} {result.item.title}：{result.reason}")
    if report.failed:
        raise typer.Exit(code=1)


def _to_discovered(summary: MeetingSummary, tz: ZoneInfo) -> DiscoveredMeeting:
    return DiscoveredMeeting(
        title=summary.topic or "(无主题)",
        date=_date_of(summary.start_time, tz),
        source=SourceKind.FEISHU_NOTE,
        meeting_id=summary.meeting_id,
        note_id=summary.note_id,
    )
