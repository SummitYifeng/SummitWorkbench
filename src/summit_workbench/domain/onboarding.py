"""onboarding 领域模型（P0-08：新建 / 升级 / 连接工作区服务）。

纯模型与枚举，无 IO；预检报告 / 完成结果用于 CLI 与 Web API 共用的结构化输出
（错误一律以 OnboardingError 携带可解释的阻断理由列表，绝不静默猜测）。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, computed_field

from summit_workbench.domain.workspace import Compatibility


class OnboardingFlow(StrEnum):
    """三条 onboarding 流程（P0-08）。"""

    CREATE_NEW = "create-new"  # 新建：选 Work Root → staging → _vault + marker + profile
    UPGRADE_EXISTING = "upgrade-existing"  # 升级旧 vault：备份 → 写 marker/profile，不动内容
    CONNECT_LOCAL = "connect-local"  # 连接已 clone/拷贝的带 marker vault → 建档
    CONNECT_REMOTE = "connect-remote"  # 私有 HTTPS remote clone 的目标目录（尚未存在）


class PreflightReport(BaseModel):
    """只读预检报告：路径/权限/空态/git/marker/兼容/网盘/模板卫生/空间 + 阻断理由。"""

    flow: OnboardingFlow
    target: str
    exists: bool = False
    is_dir: bool = False
    writable: bool = False
    empty: bool = False
    vault_target_exists: bool = False  # create-new：work_root/_vault 是否已存在
    has_git_dir: bool = False  # 仅探测 .git 目录存在，不运行任何 git 命令（P0-09 前）
    has_marker: bool = False
    marker_workspace_id: str | None = None
    compatibility: Compatibility | None = None  # connect/upgrade 读到的 marker 兼容结论
    cloud_storage: bool = False
    template_issues: list[str] = []  # create-new：模板个人化内容命中项
    space_free_bytes: int = 0
    space_ok: bool = True
    rejections: list[str] = []  # 阻断理由（任一非空 → ok=False）

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        return not self.rejections


class OnboardingResult(BaseModel):
    """一次 onboarding 成功的结构化结果。"""

    flow: OnboardingFlow
    workspace_id: str
    work_root: str
    vault_dir: str
    device_id: str
    display_name: str
    created_at: str
    backup_dir: str | None = None  # upgrade-existing：timestamped 备份目录
