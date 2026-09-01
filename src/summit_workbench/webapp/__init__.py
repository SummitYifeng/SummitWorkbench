"""本地 Web 面板（可选组件）：会议审批可点选。

设计：服务端渲染 HTML、无外部资源、只绑定回环地址；所有变更经 repositories 改写 meetings.md，
Web 层不含任何领域逻辑。需安装 ``web`` extra（``uv sync --extra web``）。
"""

from summit_workbench.webapp.app import create_app

__all__ = ["create_app"]
