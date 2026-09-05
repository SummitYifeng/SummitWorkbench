"""wb web：启动本地工作台（可选组件，需 web extra）。

--open 把「打开面板」变成一条命令：若服务未在跑则后台拉起，再打开浏览器——
通知/脚本/Spotlight 都能直达 127.0.0.1:8787。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.webapp.build_info import mode_from_environment
from summit_workbench.webapp.security import validate_bind_host


def _server_alive(host: str, port: int) -> bool:
    """探测面板是否已在运行（GET /api/state，短超时）。"""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/state", timeout=1.5) as resp:
            return bool(getattr(resp, "status", None) == 200)
    except Exception:  # noqa: BLE001 - 探测失败即视为未运行
        return False


def _spawn_detached(host: str, port: int) -> bool:
    """后台拉起 wb web（不占用当前终端），成功返回 True。"""
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "summit_workbench.cli.main",
                "web",
                "--host",
                host,
                "--port",
                str(port),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def _open_browser(host: str, port: int) -> bool:
    if sys.platform != "darwin":
        return False
    opener = shutil.which("open")
    if not opener:
        return False
    return (
        subprocess.run(
            [opener, f"http://{host}:{port}/"],
            check=False,
            capture_output=True,
            timeout=10,
        ).returncode
        == 0
    )


def web_command(
    host: str = typer.Option("127.0.0.1", "--host", help="绑定地址（默认仅本机回环）。"),
    port: int = typer.Option(8787, "--port", help="监听端口。"),
    open_browser: bool = typer.Option(
        False, "--open", help="若服务未运行则后台拉起，并打开浏览器直达面板。"
    ),
) -> None:
    """在 localhost 启动 Web 工作台；--open 可随时「点开直达」。"""
    try:
        validate_bind_host(host, mode_from_environment(os.environ.get("WB_PANEL_MODE")))
    except ValueError as exc:
        typer.echo(f"✗ 启动拒绝：{exc}")
        raise typer.Exit(code=2) from exc
    if open_browser:
        if _server_alive(host, port):
            typer.echo(f"面板已在运行：http://{host}:{port}/")
        elif _spawn_detached(host, port):
            typer.echo(f"已在后台启动面板：http://{host}:{port}/")
        else:
            typer.echo("后台启动失败，请直接运行：wb web")
        _open_browser(host, port)
        return

    try:
        import uvicorn

        from summit_workbench.webapp.app import WebContext, create_app
    except ModuleNotFoundError as exc:
        typer.echo(f"✗ 未安装 Web 组件。请先运行：uv sync --extra web（缺少 {exc.name}）")
        raise typer.Exit(code=2) from exc

    settings = load_settings()
    paths = settings.work_paths()
    ctx = WebContext(
        vault_dir=paths.vault_dir, work_root=paths.work_root, timezone=settings.timezone
    )
    typer.echo(f"工作台：http://{host}:{port}/  （Ctrl+C 停止）")
    typer.echo(f"vault：{paths.vault_dir}")
    uvicorn.run(
        create_app(ctx, bind_host=host, port=port), host=host, port=port, log_level="warning"
    )
