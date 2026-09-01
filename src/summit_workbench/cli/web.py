"""``wb web``：启动本地审批面板（可选组件，需 ``web`` extra）。"""

from __future__ import annotations

import typer

from summit_workbench.config.settings import load_settings


def web_command(
    host: str = typer.Option("127.0.0.1", "--host", help="绑定地址（默认仅本机回环）。"),
    port: int = typer.Option(8787, "--port", help="监听端口。"),
) -> None:
    """在 localhost 启动会议审批面板（点选批准/拒绝/修改 + 预演/应用）。"""
    try:
        import uvicorn

        from summit_workbench.webapp.app import WebContext, create_app
    except ModuleNotFoundError as exc:
        typer.echo(
            "✗ 未安装 Web 组件。请先运行：uv sync --extra web"
            f"（缺少 {exc.name}）"
        )
        raise typer.Exit(code=2) from exc

    settings = load_settings()
    paths = settings.work_paths()
    ctx = WebContext(
        vault_dir=paths.vault_dir, work_root=paths.work_root, timezone=settings.timezone
    )
    typer.echo(f"审批面板：http://{host}:{port}/review  （Ctrl+C 停止）")
    typer.echo(f"vault：{paths.vault_dir}")
    uvicorn.run(create_app(ctx), host=host, port=port, log_level="warning")
