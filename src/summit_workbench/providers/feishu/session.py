"""飞书会话：把配置、Keychain 凭据与 token 刷新绑在一起。

职责：读 app_secret 与 refresh_token（Keychain）→ 刷新出 access_token →
把轮换出的新 refresh_token 回写 Keychain。凭据只在内存中短暂存在，不落日志。
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from summit_workbench.config.locking import workspace_lock
from summit_workbench.config.secrets import (
    CredentialError,
    resolve_credential,
    store_credential,
)
from summit_workbench.providers.feishu import auth
from summit_workbench.providers.feishu.config import FeishuConfig
from summit_workbench.providers.feishu.errors import FeishuAuthError, FeishuConfigError


class FeishuSession:
    def __init__(self, cfg: FeishuConfig) -> None:
        self.cfg = cfg

    def _app_secret(self) -> SecretStr:
        try:
            return resolve_credential(self.cfg.app_secret_ref)
        except CredentialError as exc:
            raise FeishuConfigError(
                f"未在 Keychain 找到 app_secret（{self.cfg.app_secret_ref}）；"
                "请先用 security add-generic-password 存入"
            ) from exc

    def complete_authorization(
        self, code: str, *, client: httpx.Client | None = None
    ) -> auth.TokenSet:
        """用授权码换取令牌，并把 refresh_token 存入 Keychain。

        若返回不含 refresh_token，说明未授予 offline_access，显式报错而不静默继续。
        """
        tokens = auth.exchange_code(self.cfg, self._app_secret(), code, client=client)
        if tokens.refresh_token is None:
            raise FeishuAuthError(
                "换取成功但未返回 refresh_token：请确认授权 scope 含 offline_access"
            )
        # 与 access_token() 的轮换共用工作区锁：授权写回与并发刷新互斥，避免覆盖竞态。
        with workspace_lock():
            store_credential(self.cfg.refresh_token_ref, tokens.refresh_token)
        return tokens

    def tenant_access_token(self, *, client: httpx.Client | None = None) -> SecretStr:
        """获取应用身份 tenant_access_token（只需 app_secret，无需用户授权）。

        用于读取 tenant 侧授权的会议纪要/文档资源，避开用户态未授予的 scope。
        """
        return auth.get_tenant_access_token(self.cfg, self._app_secret(), client=client)

    def access_token(self, *, client: httpx.Client | None = None) -> SecretStr:
        """刷新并返回可用的 access_token；同时把轮换出的新 refresh_token 回写 Keychain。

        飞书 refresh_token 单次轮换：``读 RT → 刷新 → 写回新 RT`` 必须作为一个整体
        对并发进程互斥，否则两个触发源会互相作废对方的 token，把 Keychain 存成死
        token（LHF #1）。这里用工作区锁把整段 read-modify-write 圈成临界区。
        """
        with workspace_lock():
            try:
                current_rt = resolve_credential(self.cfg.refresh_token_ref)
            except CredentialError as exc:
                raise FeishuAuthError(
                    f"未在 Keychain 找到 refresh_token（{self.cfg.refresh_token_ref}）；"
                    "请先运行 wb feishu login 完成一次授权",
                    needs_reauthorize=True,
                ) from exc

            tokens = auth.refresh_token(self.cfg, self._app_secret(), current_rt, client=client)
            if tokens.refresh_token is not None:
                store_credential(self.cfg.refresh_token_ref, tokens.refresh_token)
            return tokens.access_token
