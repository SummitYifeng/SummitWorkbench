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
# offline_access 必需——只有授予它，换取 token 时才会返回 refresh_token。
DEFAULT_SCOPES: tuple[str, ...] = (
    "calendar:calendar:readonly",  # 日历只读
    "task:task",  # 任务读写
    "docx:document:readonly",  # 纪要正文文档只读
    "offline_access",  # 换取 refresh_token 必需
)

# 会议相关 scope（视频会议 / 会议纪要）在当前控制台的精确标识需实测确认——
# 之前猜测的 vc:meeting:readonly / minutes:minutes:readonly 在租户里不存在（授权报 20027）。
# 会议纪要读取本就推迟到 M0-10；届时在控制台确认可用标识后，再加入默认或用 [feishu].scopes 覆盖。
MEETING_SCOPES_PENDING_M0_10: tuple[str, ...] = ()

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
