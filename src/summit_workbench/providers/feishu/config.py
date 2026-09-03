"""飞书应用配置与凭据引用。

非敏感项（app_id、redirect_uri、scopes、主机）来自本机配置文件的 ``[feishu]`` 表；
敏感项（app_secret、refresh_token）只以 Keychain 引用形式出现，绝不入配置文件或 git。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from summit_workbench.config.secrets import CredentialRef
from summit_workbench.config.settings import default_config_file
from summit_workbench.providers.feishu.errors import FeishuConfigError

# 主机（授权走 accounts 域，其余 OpenAPI 走 open 域）。
AUTHORIZE_HOST = "https://accounts.feishu.cn"
OPENAPI_HOST = "https://open.feishu.cn"

# 授权 / 令牌端点（已对官方文档核实，2026-08）。
AUTHORIZE_PATH = "/open-apis/authen/v1/authorize"
TOKEN_PATH = "/open-apis/authen/v2/oauth/token"  # 授权码换取与刷新共用

# 按 PRD NFR-4 的最小权限申请的 scope。vc/minutes 的精确标识需与开放平台
# 「应用权限」列表核对后再定；此处给出合理默认，允许在 [feishu].scopes 覆盖。
# 这些是 **user_access_token 授权** 请求的 scope（用户态可授予项）。
# 会议纪要/逐字稿/会议列表的读取走 tenant_access_token（应用态），其权限
# （vc:note:read / docs:document.content:read / vc:meeting.*）在开放平台按应用授予，
# 不进入这里——避免把仅 tenant 可授予的 scope 混入用户授权导致 20027。
# offline_access 必需——只有授予它，换取 token 时才会返回 refresh_token。
DEFAULT_SCOPES: tuple[str, ...] = (
    # 日历读写（2026-09-03 真机核实：审批「新建会议」/行内编辑日历事件可写回；
    # scope 变更后需**重新授权一次**，旧 token 不带新 scope）。
    "calendar:calendar",
    "task:task:read",  # 任务读（M2-1 list_tasks；真机核实：粗粒度 task:task 不足，需细粒度）
    "task:task:write",  # 任务写（create/update/complete；2026-09-03 真机核实 update/complete 可用）
    "docx:document:readonly",  # 文档只读（用户态）
    "offline_access",  # 换取 refresh_token 必需
)

# Keychain 凭据引用的默认 service 名（account 统一用 app_id）。
APP_SECRET_SERVICE = "summit-workbench-feishu-app-secret"
REFRESH_TOKEN_SERVICE = "summit-workbench-feishu-refresh-token"


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    redirect_uri: str
    scopes: tuple[str, ...] = DEFAULT_SCOPES
    authorize_host: str = AUTHORIZE_HOST
    openapi_host: str = OPENAPI_HOST

    @property
    def app_secret_ref(self) -> CredentialRef:
        return CredentialRef(service=APP_SECRET_SERVICE, account=self.app_id)

    @property
    def refresh_token_ref(self) -> CredentialRef:
        return CredentialRef(service=REFRESH_TOKEN_SERVICE, account=self.app_id)

    @property
    def scope_param(self) -> str:
        """authorize / token 端点使用的空格分隔 scope 串。"""
        return " ".join(self.scopes)


def load_feishu_config(config_file: Path | None = None) -> FeishuConfig:
    """从本机配置文件的 ``[feishu]`` 表加载配置。

    必填 ``app_id`` 与 ``redirect_uri``；缺失即抛 :class:`FeishuConfigError`
    （明确失败，不用占位值蒙混）。凭据不在此处，运行时按引用从 Keychain 读取。
    """
    path = config_file or default_config_file()
    if not path.is_file():
        raise FeishuConfigError(
            f"配置文件不存在：{path}（需在 [feishu] 表填 app_id / redirect_uri）"
        )

    with path.open("rb") as fh:
        data = tomllib.load(fh)
    section = data.get("feishu")
    if not isinstance(section, dict):
        raise FeishuConfigError(f"配置文件缺少 [feishu] 表：{path}")

    app_id = section.get("app_id")
    redirect_uri = section.get("redirect_uri")
    missing = [k for k, v in {"app_id": app_id, "redirect_uri": redirect_uri}.items() if not v]
    if missing:
        raise FeishuConfigError(f"[feishu] 缺少必填项：{', '.join(missing)}")

    scopes = section.get("scopes")
    scope_tuple = tuple(scopes) if isinstance(scopes, list) and scopes else DEFAULT_SCOPES

    return FeishuConfig(
        app_id=str(app_id),
        redirect_uri=str(redirect_uri),
        scopes=scope_tuple,
    )
