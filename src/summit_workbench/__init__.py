"""SummitWorkbench：外置执行管理层 + 第二大脑。

本地 Python CLI（``wb``）。M0 地基已完成：配置/凭据、工作 vault schema、飞书身份与
会议纪要拉取、云端模型结构化、work-sync。M1 起构建会议进入第二大脑的端到端链路。
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("summit-workbench")
except PackageNotFoundError:  # 未安装（例如直接从源码树运行）时的兜底。
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
