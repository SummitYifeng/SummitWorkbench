"""密钥保护测试（NFR-4）：秘密值不得出现在 repr / str / 日志 / 序列化中。"""

from __future__ import annotations

import logging
import subprocess

import pytest
from pydantic import SecretStr

from summit_workbench.config.secrets import (
    CredentialError,
    CredentialRef,
    redact,
    resolve_credential,
)


def test_credential_ref_holds_no_secret_value() -> None:
    ref = CredentialRef(service="feishu", account="app-secret")
    # 引用本身不含秘密，只有 service/account 标识。
    assert "feishu" in repr(ref)
    assert "app-secret" in repr(ref)


def test_secretstr_not_leaked_in_repr() -> None:
    secret = SecretStr("super-secret-token")
    assert "super-secret-token" not in repr(secret)
    assert "super-secret-token" not in str(secret)
    # 只有显式 get_secret_value() 才拿到明文。
    assert secret.get_secret_value() == "super-secret-token"


def test_redact_masks_secretstr() -> None:
    assert redact(SecretStr("abc123")) == "***"
    assert redact("/tmp/plain/path") == "/tmp/plain/path"


def test_secret_not_leaked_via_logging(caplog) -> None:
    secret = SecretStr("leak-me-not")
    with caplog.at_level(logging.INFO):
        logging.getLogger("test").info("credential=%s", redact(secret))
    assert "leak-me-not" not in caplog.text
    assert "***" in caplog.text


# —— 凭据解析的失败分支（credential 系统的整个失败面都经由 _run_security）——

_REF = CredentialRef(service="summit-workbench-x", account="acct")


def test_resolve_raises_credential_error_on_nonzero(monkeypatch) -> None:
    """security 返回非零 → CredentialError，且信息含操作/引用但绝不含秘密。"""

    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(
            args=["security"], returncode=44, stdout="", stderr="item could not be found\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CredentialError) as exc:
        resolve_credential(_REF)
    msg = str(exc.value)
    assert "解析" in msg
    assert "summit-workbench-x" in msg  # 引用可见，便于定位


def test_resolve_raises_credential_error_when_security_missing(monkeypatch) -> None:
    """非 macOS / 缺 security CLI → FileNotFoundError 归一为 CredentialError（不冒泡）。"""

    def fake_run(*_a, **_k):
        raise FileNotFoundError("security")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CredentialError):
        resolve_credential(_REF)
