"""后置自动推送的显式开关（``WB_NO_AUTO_PUSH``）。

**为什么需要它**（2026-09-19 真实事故）：SWB 的每一条 Web/CLI 写入路径在 commit 之后都会经
``sync_coordinator.push_after_commit`` 把结果推到 vault 远端。日常使用这是对的，但**验证类
动作**不该顺带推送——跨端闸门当时已经加了 ``--no-push``，却仍然被"运行中的 App 自动推送"
把验证件与本地未推提交一起发布到了 ``origin/main``：``--no-push`` 只挡住了闸门自己收尾那一个
提交，挡不住端点自己的推送。

**语义**

- **默认关闭**：env 未设 / 空 / ``0`` / ``false`` … → 行为完全不变（commit 后照常 push）。
- 设 ``WB_NO_AUTO_PUSH=1``（也接受 ``true`` / ``yes`` / ``on``，大小写与首尾空白不敏感）→
  **commit 照常发生，只是不再自动 push**。
- 跳过动作**必须可见**：写一行服务日志（事件 ``auto_push_skipped``）并把
  :func:`auto_push_skip_note` 放进调用方的返回值里。
- ⚠️ **绝不把"跳过推送"记成同步成功（``ready``）**：跳过发生在 push 之前，同步状态机根本
  不参与——调用方拿到的是一句明确的"已跳过自动推送"，而不是一个看起来正常的同步状态。
  这正是最容易骗到下一个人的地方（"没有推送"被读成"同步没问题"）。

**边界**：本开关只影响"写入之后的自动推送"。使用者显式发起的同步（``/api/sync/run``、
``wb sync``）不受影响——那是使用者的动作，不是自动行为。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

AUTO_PUSH_DISABLE_ENV = "WB_NO_AUTO_PUSH"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def auto_push_disabled(environ: Mapping[str, str] | None = None) -> bool:
    """是否显式关闭"写入后的自动推送"。默认 False（保持既有行为）。

    每次调用都读一次环境，便于测试与"运行中改 env 重启"的部署；不缓存。
    """
    source: Mapping[str, str] = os.environ if environ is None else environ
    return source.get(AUTO_PUSH_DISABLE_ENV, "").strip().lower() in _TRUTHY


def auto_push_skip_note() -> str:
    """跳过自动推送的可见说明（放进响应 ``message`` / ``auto_push.note``）。"""
    return f"（已跳过自动推送：{AUTO_PUSH_DISABLE_ENV} 已启用）"


def log_auto_push_skipped(*, home: Path | None = None, where: str = "") -> None:
    """写一行服务日志留痕（best-effort，失败绝不影响写入路径）。

    ``where`` 只说"哪条写入路径"（如 ``commit_suffix`` / ``mutation``），不写路径或正文。
    """
    from summit_workbench.observability.server_log import log_server_event

    log_server_event(
        "auto_push_skipped",
        level="warning",
        fields={"env": AUTO_PUSH_DISABLE_ENV, "where": where},
        home=home,
    )


__all__ = [
    "AUTO_PUSH_DISABLE_ENV",
    "auto_push_disabled",
    "auto_push_skip_note",
    "log_auto_push_skipped",
]
