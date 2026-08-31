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


def _run_security(
    args: list[str], *, action: str, ref: CredentialRef
) -> subprocess.CompletedProcess[str]:
    """运行 ``security`` 子命令，失败时抛出不含秘密值的 :class:`CredentialError`。"""
    try:
        completed = subprocess.run(["security", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:  # 非 macOS 或缺少 security CLI
        raise CredentialError(f"无法调用 security CLI {action} {ref}") from exc

    if completed.returncode != 0:
        # 只回传 stderr 的首行摘要，Keychain 不会把密码写进 stderr。
        detail = (completed.stderr or "").strip().splitlines()
        hint = detail[0] if detail else f"returncode={completed.returncode}"
        raise CredentialError(f"未能{action} {ref}: {hint}")
    return completed


def resolve_credential(ref: CredentialRef) -> SecretStr:
    """从 Keychain 读取 ``ref`` 对应的秘密值（``security find-generic-password -w``）。

    任何失败都抛出 :class:`CredentialError`，异常信息里不含秘密值。
    """
    completed = _run_security(
        ["find-generic-password", "-s", ref.service, "-a", ref.account, "-w"],
        action="解析",
        ref=ref,
    )
    return SecretStr(completed.stdout.rstrip("\n"))


def store_credential(ref: CredentialRef, value: SecretStr) -> None:
    """把 ``value`` 写入 Keychain 中 ``ref`` 对应的 generic password（存在则更新）。

    供运行时保存 API 返回的凭据使用——典型场景是飞书 refresh_token 每次刷新都会轮换，
    必须回写新值（见 providers/feishu）。秘密值只经 ``-w`` 传给 security，不进日志、不进异常。
    """
    _run_security(
        [
            "add-generic-password",
            "-a",
            ref.account,
            "-s",
            ref.service,
            "-w",
            value.get_secret_value(),
            "-U",  # 已存在则更新
        ],
        action="写入",
        ref=ref,
    )


def redact(value: object) -> str:
    """把可能含敏感内容的对象渲染成安全字符串（用于日志 / 诊断输出）。"""
    if isinstance(value, SecretStr):
        return "***"
    return str(value)
