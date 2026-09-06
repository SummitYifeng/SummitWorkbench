"""TLS 信任链选择（P1-07D）：packaged/frozen 运行时的 CA bundle 解析。

打包后的 PyInstaller server/worker 使用随 Python 分发的 OpenSSL，其编译期
OPENSSLDIR 指向 python.org 框架路径（/Library/Frameworks/...），该路径在
macOS 上通常不存在、也不会随 bundle 分发；macOS 系统 Keychain 又无法被
OpenSSL 的 set_default_verify_paths() 读取。因此 OpenSSL 的「系统默认 CA」
在打包环境不可用，dulwich/urllib3 会对 GitHub 报 TLS 校验失败（P1-07D 的
git_tls_failed）。

本模块统一改用随 bundle 分发的 certifi Mozilla CA bundle（两个打包 spec 都已把
certifi.where() 收集为 <bundle>/certifi/cacert.pem），并可把 SSL_CERT_FILE 指向
它，让 ssl.create_default_context() / load_default_certs() 都能命中可信根。
绝不关闭 TLS 校验（production 保持 HTTPS-only），也绝不把 TLS 失败归为离线/远端
不可达（错误分类在 git_backend）。
"""

from __future__ import annotations

import importlib.util
import os
import ssl
import sys
from pathlib import Path

_SSL_CERT_FILE_ENV = "SSL_CERT_FILE"


def ca_bundle_path() -> Path | None:
    """返回打包运行时可用的 CA bundle 路径（不关闭 TLS 校验）。

    优先级：certifi（常规 site-packages）→ PyInstaller frozen 数据目录
    （sys._MEIPASS/certifi/cacert.pem）→ 系统 OpenSSL 默认路径。
    """
    # 1) certifi：开发/CLI 与常规 site-packages。
    if importlib.util.find_spec("certifi") is not None:
        try:
            import certifi

            candidate = Path(certifi.where())
            if candidate.is_file():
                return candidate
        except Exception:  # noqa: BLE001 - certifi 定位失败不致命，继续回退
            pass
    # 2) PyInstaller onedir/onefile：数据文件被收集为 <bundle>/certifi/cacert.pem。
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidate = Path(frozen_root) / "certifi" / "cacert.pem"
        if candidate.is_file():
            return candidate
    # 3) 系统 OpenSSL 默认路径（开发机或已配置 OPENSSLDIR 的环境）。
    defaults = ssl.get_default_verify_paths()
    for raw in (defaults.cafile, defaults.openssl_cafile):
        if raw:
            candidate = Path(raw)
            if candidate.is_file():
                return candidate
    return None


def configure_default_tls_trust() -> Path | None:
    """把 SSL_CERT_FILE 指向可用 CA bundle（幂等；尊重既有覆盖）。

    在打包 server/worker 入口调用一次，让所有经 ssl.create_default_context() 的
    HTTPS 客户端（urllib3/dulwich、httpx 等）使用同一可信根。仅当环境未显式设置
    SSL_CERT_FILE 且发现可用 bundle 时写入；返回最终生效的 bundle 路径。
    """
    bundle = ca_bundle_path()
    if bundle is not None and not os.environ.get(_SSL_CERT_FILE_ENV):
        os.environ[_SSL_CERT_FILE_ENV] = str(bundle)
    return bundle


def tls_runtime_diagnostic() -> dict[str, object]:
    """Return a safe, path-free diagnostic for a packaged TLS runtime.

    This is intentionally read-only and reports only booleans/enums.  Packaged
    integration tests use it from the frozen server/worker executables so they
    can prove that the bundle CA is found and that Dulwich receives it without
    exposing a user path or any credential.
    """
    bundle = ca_bundle_path()
    frozen_root = getattr(sys, "_MEIPASS", None)
    in_frozen_bundle = False
    if bundle is not None and frozen_root:
        try:
            in_frozen_bundle = bundle.resolve().is_relative_to(Path(frozen_root).resolve())
        except OSError:
            in_frozen_bundle = False

    result: dict[str, object] = {
        "ca_bundle_present": bundle is not None and bundle.is_file(),
        "ca_bundle_source": "pyinstaller-bundle" if in_frozen_bundle else "external-or-none",
        "ssl_cert_file_configured": bool(os.environ.get(_SSL_CERT_FILE_ENV)),
        "ssl_context_status": "not-checked",
        "ssl_context_verify_mode": None,
        "ssl_context_check_hostname": None,
        "dulwich_transport_status": "not-checked",
        "dulwich_ca_bundle_present": False,
        "dulwich_cert_reqs": None,
        "dulwich_proxy_manager": None,
    }
    if bundle is None or not bundle.is_file():
        result["ssl_context_status"] = "ca_bundle_missing"
        result["dulwich_transport_status"] = "ca_bundle_missing"
        return result

    try:
        context = ssl.create_default_context(cafile=str(bundle))
    except (OSError, ssl.SSLError):
        result["ssl_context_status"] = "ca_bundle_load_failed"
    else:
        result["ssl_context_status"] = "ok"
        result["ssl_context_verify_mode"] = context.verify_mode.name
        result["ssl_context_check_hostname"] = context.check_hostname

    try:
        from summit_workbench.repositories.dulwich_git import _https_pool_manager

        manager = _https_pool_manager("https://github.com")
        kwargs = manager.connection_pool_kw
        ca_certs = kwargs.get("ca_certs")
        result["dulwich_transport_status"] = "ok"
        result["dulwich_ca_bundle_present"] = (
            bool(ca_certs) and Path(os.fsdecode(ca_certs)).is_file()
        )
        result["dulwich_cert_reqs"] = kwargs.get("cert_reqs")
        result["dulwich_proxy_manager"] = type(manager).__name__
    except (OSError, RuntimeError, ValueError):
        result["dulwich_transport_status"] = "transport_setup_failed"
    return result


__all__ = ["ca_bundle_path", "configure_default_tls_trust", "tls_runtime_diagnostic"]
