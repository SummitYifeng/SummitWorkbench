"""``wb feishu`` 子命令：授权、登录、鉴权冒烟与本地逐字稿导入。

联网命令（login / smoke）只有在配置齐全且 Keychain 已存凭据时才实际调用飞书；
凭据由用户自行存入 Keychain，本 CLI 只引用，绝不打印任何 token。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from zoneinfo import ZoneInfo

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.providers.feishu import (
    FeishuClient,
    FeishuConfig,
    FeishuError,
    FeishuNoteSource,
    FeishuSession,
    import_local_transcript,
    list_meetings_by_no,
    load_feishu_config,
    verify_identity,
)

feishu_app = typer.Typer(
    name="feishu",
    help="飞书身份与会议接入（authorize-url / login / smoke / note-transcript / import-local）。",
    no_args_is_help=True,
    add_completion=False,
)


def _config() -> FeishuConfig:
    try:
        return load_feishu_config()
    except FeishuError as exc:
        typer.echo(f"配置错误：{exc}")
        raise typer.Exit(code=2) from exc


@feishu_app.command("authorize-url")
def authorize_url() -> None:
    """打印用户授权 URL。在浏览器打开并同意后，用回调里的 code 运行 wb feishu login。"""
    from summit_workbench.providers.feishu.auth import build_authorize_url

    cfg = _config()
    state = token_urlsafe(16)
    typer.echo(build_authorize_url(cfg, state))
    typer.echo("")
    typer.echo(f"state={state}（回调返回时应一致，用于防 CSRF）")
    typer.echo(f"申请 scope：{cfg.scope_param}")


@feishu_app.command("login")
def login(
    code: str = typer.Option(..., "--code", help="授权回调返回的一次性 code（5 分钟内有效）。"),
) -> None:
    """用授权码换取令牌，并把 refresh_token 存入 Keychain。"""
    cfg = _config()
    try:
        session = FeishuSession(cfg)
        tokens = session.complete_authorization(code)
    except FeishuError as exc:
        typer.echo(f"登录失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("✓ 授权成功，refresh_token 已写入 Keychain")
    typer.echo(f"  access_token 有效期约 {tokens.expires_in} 秒；scope={tokens.scope}")


@feishu_app.command("smoke")
def smoke() -> None:
    """鉴权冒烟：刷新 token → 调 user_info，证明授权链路与 token 刷新可用。"""
    cfg = _config()
    try:
        session = FeishuSession(cfg)
        access = session.access_token()
        client = FeishuClient(cfg, access)
        profile = verify_identity(client)
    except FeishuError as exc:
        typer.echo(f"✗ 冒烟失败：{exc}")
        raise typer.Exit(code=1) from exc
    name = profile.get("name") or profile.get("en_name") or "(未知)"
    open_id = profile.get("open_id", "(无)")
    typer.echo("✓ 鉴权冒烟通过：user_access_token 有效")
    typer.echo(f"  身份：{name}  open_id={open_id}")


@feishu_app.command("import-local")
def import_local(
    file: Path = typer.Argument(..., help="本地逐字稿文件路径（Note API 不可用时的兜底）。"),
    meeting_id: str = typer.Option(..., "--meeting-id", help="为该逐字稿指定稳定会议 ID。"),
) -> None:
    """本地兜底：读入一份本地逐字稿并报告其规模（不联网，不做结构化）。"""
    try:
        result = import_local_transcript(file, meeting_id)
    except FeishuError as exc:
        typer.echo(f"导入失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ 已读入本地逐字稿（{len(result.text)} 字符）")
    typer.echo(f"  meeting_id={result.meeting_id}  来源={result.origin_path}")


@feishu_app.command("meetings")
def meetings(
    meeting_no: str = typer.Option(..., "--meeting-no", help="9 位会议号（Feishu 会议里可见）。"),
    since: str = typer.Option(..., "--since", help="起始日期 YYYY-MM-DD。"),
    until: str = typer.Option(..., "--until", help="结束日期 YYYY-MM-DD（含当天）。"),
) -> None:
    """按会议号 + 时间范围列出会议及其 note_id（会议发现，M1-1 前置）。"""
    cfg = _config()
    meeting_no = meeting_no.replace(" ", "")  # 飞书显示带空格（937 075 886），实际无空格
    tz = ZoneInfo(load_settings().timezone)
    try:
        start = int(datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=tz).timestamp())
        end_dt = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)
        end = int(end_dt.timestamp()) - 1
    except ValueError as exc:
        typer.echo("日期格式应为 YYYY-MM-DD")
        raise typer.Exit(code=2) from exc

    try:
        session = FeishuSession(cfg)
        client = FeishuClient(cfg, session.tenant_access_token())
        found = list_meetings_by_no(client, meeting_no, start, end)
    except FeishuError as exc:
        typer.echo(f"✗ 列会议失败：{exc}")
        raise typer.Exit(code=1) from exc

    if not found:
        typer.echo(f"会议号 {meeting_no} 在 {since}~{until} 内没有会议")
        raise typer.Exit(code=0)
    for m in found:
        note = m.note_id or "(无纪要)"
        typer.echo(f"• {m.topic or '(无主题)'}  meeting_id={m.meeting_id}  note_id={note}")
    typer.echo("")
    typer.echo("对有 note_id 的会议跑：wb feishu note-transcript --note-id <note_id>")


@feishu_app.command("note-transcript")
def note_transcript(
    note_id: str = typer.Option(..., "--note-id", help="会议纪要 ID（note_id）。"),
    preview: int = typer.Option(300, "--preview", help="预览逐字稿前 N 个字符。"),
) -> None:
    """M0-10 冒烟：按 note_id 拉取完整逐字稿（notes → 逐字稿文档 → 正文）。"""
    cfg = _config()
    try:
        session = FeishuSession(cfg)
        client = FeishuClient(cfg, session.tenant_access_token())
        result = FeishuNoteSource(client).fetch_transcript(note_id)
    except FeishuError as exc:
        typer.echo(f"✗ 拉取逐字稿失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ 已取回逐字稿（{len(result.text)} 字符）")
    typer.echo(f"  note_id={result.note_id}  doc_token={result.doc_token}")
    if preview > 0:
        typer.echo(f"--- 前 {preview} 字符 ---")
        typer.echo(result.text[:preview])
