"""凭据引用与解析。

原则（NFR-4）：配置里只出现「凭据引用」（keychain 的 service + account），
绝不出现秘密值本身。真正的秘密值在运行时按需从 macOS Keychain 读取，并以
:class:`pydantic.SecretStr` 承载，确保它不会出现在 ``repr``、日志或模型上下文中。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from pydantic import SecretStr


class CredentialError(RuntimeError):
    """凭据无法解析时抛出（缺失、Keychain 不可用等）。异常信息不含秘密值。"""


@dataclass(frozen=True)
class CredentialRef:
    """指向 macOS Keychain 中一条 generic password 的引用。

    只保存 ``service`` 与 ``account`` 这类非敏感标识；不保存也不缓存秘密值。
    """

    service: str
    account: str

    def __str__(self) -> str:  # noqa: D105 - 明确不泄露内容
        return f"CredentialRef(service={self.service!r}, account={self.account!r})"


def resolve_credential(ref: CredentialRef) -> SecretStr:
    """从 Keychain 读取 ``ref`` 对应的秘密值。

    使用 ``security find-generic-password -w`` 只取密码正文。任何失败都抛出
    :class:`CredentialError`，且异常信息里不包含秘密值。
    """
    try:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                ref.service,
                "-a",
                ref.account,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # 非 macOS 或缺少 security CLI
        raise CredentialError(f"无法调用 security CLI 解析 {ref}") from exc

    if completed.returncode != 0:
        # 只回传 stderr 的首行摘要，Keychain 不会把密码写进 stderr。
        detail = (completed.stderr or "").strip().splitlines()
        hint = detail[0] if detail else f"returncode={completed.returncode}"
        raise CredentialError(f"未能解析 {ref}: {hint}")

    return SecretStr(completed.stdout.rstrip("\n"))


def redact(value: object) -> str:
    """把可能含敏感内容的对象渲染成安全字符串（用于日志 / 诊断输出）。"""
    if isinstance(value, SecretStr):
        return "***"
    return str(value)
