"""PyInstaller worker 入口：只执行一次自动化任务，不启动 Web server。"""

from __future__ import annotations

import json
import os

import typer

from summit_workbench.cli.worker import worker_command
from summit_workbench.config.tls_trust import configure_default_tls_trust, tls_runtime_diagnostic


def main() -> None:
    # 与打包 server 一致：先让 ssl.create_default_context() 命中 certifi CA。
    configure_default_tls_trust()
    if os.environ.get("WB_TLS_DIAGNOSTIC") == "1":
        print(json.dumps(tls_runtime_diagnostic(), ensure_ascii=False, sort_keys=True))
        return
    typer.run(worker_command)


if __name__ == "__main__":
    main()
