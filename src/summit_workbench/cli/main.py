"""``wb`` 命令树（M0-1：仅 help / version / diagnose）。"""

from __future__ import annotations

import json

import typer

from summit_workbench import __version__
from summit_workbench.cli import diagnostics
from summit_workbench.cli.ask import ask_command
from summit_workbench.cli.brief import brief_command
from summit_workbench.cli.doctor import doctor_command
from summit_workbench.cli.feishu import feishu_app
from summit_workbench.cli.kb import kb_app
from summit_workbench.cli.meeting import meeting_app
from summit_workbench.cli.model import model_app
from summit_workbench.cli.project import project_app
from summit_workbench.cli.review import review_app
from summit_workbench.cli.status import status_command
from summit_workbench.cli.sync import sync_app
from summit_workbench.cli.vault import vault_app
from summit_workbench.cli.web import web_command
from summit_workbench.cli.weekly import weekly_command
from summit_workbench.cli.worker import worker_command
from summit_workbench.config.settings import load_settings

app = typer.Typer(
    name="wb",
    help="SummitWorkbench CLI（status/brief/ask/vault/feishu/meeting/model/sync 等）。",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(vault_app)
app.add_typer(kb_app)
app.add_typer(feishu_app)
app.add_typer(meeting_app)
app.add_typer(model_app)
app.add_typer(project_app)
app.add_typer(review_app)
app.add_typer(sync_app)
app.command("status")(status_command)
app.command("doctor")(doctor_command)
app.command("ask")(ask_command)
app.command("brief")(brief_command)
app.command("weekly")(weekly_command)
app.command("worker")(worker_command)
app.command("web")(web_command)


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


@app.command()
def diagnose(
    as_json: bool = typer.Option(
        False, "--json", help="以 JSON 输出（便于脚本 / 后续 wb status 复用）。"
    ),
) -> None:
    """检查底座环境：运行时、路径与必需系统工具。绝不打印任何秘密值。

    退出码：底座就绪返回 0，否则返回 1（便于安装脚本与 CI 判定）。
    """
    report = diagnostics.collect(load_settings())

    if as_json:
        typer.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(report)

    raise typer.Exit(code=0 if report.ok else 1)


def _print_human(report: diagnostics.Diagnostics) -> None:
    def check(ok: bool) -> str:
        return "✓" if ok else "✗"

    root_state = "存在" if report.work_root_exists else "待创建"
    vault_state = "存在" if report.vault_dir_exists else "待创建"
    cfg_state = "已找到" if report.config_file_found else "未创建（使用内置默认值）"
    typer.echo(f"{check(report.python_ok)} Python {report.python_version} (需 ≥ 3.12)")
    typer.echo(f"  平台      {report.platform}")
    typer.echo(f"  工作根目录 {report.work_root} ({root_state})")
    typer.echo(f"  vault     {report.vault_dir} ({vault_state})")
    typer.echo(f"  配置文件   {report.config_file} ({cfg_state})")
    for name, ok in report.tools.items():
        typer.echo(f"{check(ok)} 工具 {name}")
    typer.echo("")
    typer.echo(f"底座状态：{'就绪' if report.ok else '存在缺失项，见上方 ✗'}")


def main() -> None:
    """``wb`` 控制台脚本入口。"""
    app()


if __name__ == "__main__":
    main()
