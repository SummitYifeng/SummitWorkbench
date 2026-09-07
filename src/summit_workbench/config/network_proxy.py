"""本机 HTTP(S) 代理发现（P1-07D）。

打包 App 经 Finder/LaunchServices 启动时，环境里通常没有 ``https_proxy`` /
``http_proxy`` / ``all_proxy``，但用户可能已在 macOS「系统设置 → 网络 → 代理」配置了
本地代理（如 Clash/V2Ray 的 ``127.0.0.1:7890``）。dulwich/urllib3 只读 env 与 git
config 的 ``http.proxy``，因此生产 HTTPS 传输需要显式回退到 macOS 系统代理，否则在
部分网络下直接连接 github.com 会被阻断（``git_remote_unavailable``）。

本模块只返回代理地址（不含凭据），绝不把代理 URL 写进日志或 remote。
"""

from __future__ import annotations

import os
import subprocess

_ENV_KEYS = ("https_proxy", "http_proxy", "all_proxy")
_PROXY_FIELDS = {
    "HTTPEnable",
    "HTTPSEnable",
    "HTTPProxy",
    "HTTPSProxy",
    "HTTPPort",
    "HTTPSPort",
}


def system_http_proxy() -> str | None:
    """返回可用 HTTP(S) 代理 URL（``http://host:port``）或 ``None``。

    优先级：env（``https_proxy`` > ``http_proxy`` > ``all_proxy``）→ macOS 系统代理
    （HTTPS > HTTP）。macOS 系统代理经只读 ``scutil --proxy`` 解析，与 App 已有的
    ``security`` CLI 依赖一致；任何解析失败都返回 ``None``，绝不让 TLS/网络失败误判。
    """
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    try:
        completed = subprocess.run(
            ["scutil", "--proxy"], capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key in _PROXY_FIELDS:
            fields[key] = value.strip()
    if fields.get("HTTPSEnable") == "1" and fields.get("HTTPSProxy") and fields.get("HTTPSPort"):
        return f"http://{fields['HTTPSProxy']}:{fields['HTTPSPort']}"
    if fields.get("HTTPEnable") == "1" and fields.get("HTTPProxy") and fields.get("HTTPPort"):
        return f"http://{fields['HTTPProxy']}:{fields['HTTPPort']}"
    return None


def proxy_detected() -> bool:
    """是否检测到本机代理（env 或 macOS 系统代理）。"""
    return system_http_proxy() is not None


__all__ = ["proxy_detected", "system_http_proxy"]
