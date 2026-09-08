"""飞书会话：把配置、Keychain 凭据与 token 刷新绑在一起。

职责：读 app_secret 与 refresh_token（Keychain）→ 刷新出 access_token →
把轮换出的新 refresh_token 回写 Keychain。凭据只在内存中短暂存在，不落日志。

P0-06：token 轮换的工作区锁根不再默默取默认 ``resolve_work_root()``，而是接受调用方
从 :class:`~summit_workbench.config.paths.WorkspacePaths` 传入的 lock root——web、
brief 等带 vault/workspace 上下文的调用方传入实际锁根，保证与同一 workspace 的写者
锁在同一 ``.wb.lock``；机器级 CLI 命令（login/smoke/doctor 等）不传时保持兼容回退。
"""

from __future__ import annotations

import time
from pathlib import Path

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
    def __init__(self, cfg: FeishuConfig, *, lock_root: Path | None = None) -> None:
        """构造飞书会话。

        :param lock_root: 工作区锁根（``WorkspacePaths.lock_root``）；为 ``None`` 时
            回退 :func:`resolve_work_root`（机器级命令的兼容默认）。
        """
        self.cfg = cfg
        self._lock_root = lock_root
        self._cached_access_token: SecretStr | None = None
        self._access_token_expires_at = 0.0

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
        with workspace_lock(self._lock_root):
            store_credential(self.cfg.refresh_token_ref, tokens.refresh_token)
        self._cached_access_token = None
        self._access_token_expires_at = 0.0
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
        token（LHF #1）。这里用工作区锁把整段 read-modify-write 圈成临界区；锁根
        取构造时传入的 lock root（P0-06），不再默认落到 env work root。
        """
        now = time.monotonic()
        if self._cached_access_token is not None and now < self._access_token_expires_at:
            return self._cached_access_token
        with workspace_lock(self._lock_root):
            now = time.monotonic()
            if self._cached_access_token is not None and now < self._access_token_expires_at:
                return self._cached_access_token
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
            self._cached_access_token = tokens.access_token
            # Refresh before expiry; a short floor also avoids keeping a token
            # that is already near expiry while a request is in flight.
            self._access_token_expires_at = now + max(1.0, float(tokens.expires_in) - 30.0)
            return tokens.access_token

    def invalidate_access_token(self) -> None:
        """Drop the in-process access-token cache after reauthorization or 401."""
        self._cached_access_token = None
        self._access_token_expires_at = 0.0
