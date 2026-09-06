"""PyInstaller worker 入口：只执行一次自动化任务，不启动 Web server。"""

from __future__ import annotations

import typer

from summit_workbench.cli.worker import worker_command


def main() -> None:
    typer.run(worker_command)


if __name__ == "__main__":
    main()
