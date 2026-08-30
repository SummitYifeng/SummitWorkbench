"""SummitWorkbench：外置执行管理层 + 第二大脑。

当前处于 M0-1 工程骨架阶段，只提供可安装、可测试的底座，不含任何飞书 /
模型 / 会议 / 简报业务能力。
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("summit-workbench")
except PackageNotFoundError:  # 未安装（例如直接从源码树运行）时的兜底。
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
