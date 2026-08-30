"""密钥保护测试（NFR-4）：秘密值不得出现在 repr / str / 日志 / 序列化中。"""

from __future__ import annotations

import logging

from pydantic import SecretStr

from summit_workbench.config.secrets import CredentialRef, redact


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
