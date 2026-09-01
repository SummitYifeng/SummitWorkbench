"""macOS 桌面通知（M2-6）：经 ``osascript`` 发系统通知。

设计原则：
- 只在 macOS 且存在 ``osascript`` 时真正发送；否则安全空转并返回 False（不报错、不中断简报）。
- 通知失败不掩盖主流程（NFR-6 的可见性由调用方决定是否记录）。
- 文本经引号转义，避免破坏 AppleScript 字符串。
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def send_notification(title: str, message: str, *, subtitle: str | None = None) -> bool:
    """发一条 macOS 通知；成功返回 True，环境不支持或失败返回 False。"""
    if sys.platform != "darwin":
        return False
    osascript = shutil.which("osascript")
    if not osascript:
        return False
    parts = [f'display notification "{_escape(message)}"', f'with title "{_escape(title)}"']
    if subtitle:
        parts.append(f'subtitle "{_escape(subtitle)}"')
    script = " ".join(parts)
    try:
        completed = subprocess.run(
            [osascript, "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0
