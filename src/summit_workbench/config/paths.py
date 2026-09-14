"""路径解析：单一权威入口。

硬约束（NFR-3）：禁止硬编码 ``/Users/<name>/``，一律基于 ``$HOME`` 或
``WORK_ROOT`` 环境变量派生。所有派生路径集中在此，方便未来 Mac Air 接入。

P0-06 起提供 :class:`WorkspacePaths` 作为**唯一解析对象**，明确 ``work_root``、
``vault_dir`` 与 ``lock_root``；web、brief、Feishu refresh、sync 及所有写者都从
它取得锁根，杜绝「自定义 vault 导致锁分裂」。profile 级本机状态（config、Keychain、
device/心跳）由 P0-07 的 profile/device 域管理，本模块只负责路径解析。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def home_dir() -> Path:
    """当前用户 home 目录，绝不硬编码用户名。"""
    return Path.home()


class UserPathError(ValueError):
    """使用者输入的路径无法解析。

    面向使用者：``str(exc)`` 的文案可以直接显示在界面上，所以每条都要说**怎么办**。
    由 ``request_boundary`` 统一转成 400 JSON，不要再让它变成 500。
    """


def _home_candidates(explicit: Path | None) -> list[Path]:
    """可以当作「当前用户 home」的候选，按可信度排序。

    存在的意义：``Path.expanduser()`` 只认**进程环境**（``$HOME``），打包后的服务进程
    不一定有它；而这里可以把调用方**已经知道**的 home 放在最前面。
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    try:
        candidates.append(Path.home())
    except RuntimeError:
        pass
    env_home = os.environ.get("HOME")
    if env_home:
        candidates.append(Path(env_home))
    try:
        import pwd  # noqa: PLC0415  （冻结包/精简环境里可能没有）

        candidates.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    except (ImportError, KeyError):
        pass
    return [item for item in candidates if str(item).strip() not in {"", "~"}]


def resolve_user_path(raw: str, *, home: Path | None = None) -> Path:
    """把**使用者输入**的路径解析成 :class:`Path`，支持 ``~`` 与 ``~/…``。

    :param home: 调用方已知的 home（优先于进程环境）。测试与隔离安装用它。
    :raises UserPathError: 路径为空，或 ``~`` / ``~用户`` 解析不了。

    为什么不用 ``Path(raw).expanduser()``：2026-09-14 在 Air 上首启实测，
    ``Path("~/Documents/Work/_vault").expanduser()`` 在服务进程里抛
    ``RuntimeError: Could not determine home directory.``——那是个**未捕获异常**，
    于是向导只拿到一个非 JSON 响应，界面上显示成一句 WebKit 的
    「The string did not match the expected pattern.」，真实原因完全不可见。
    两种触发都能在这里被挡住并给出可执行文案：

    1. ``~用户`` 里的用户在**这台机器上不存在**（实测：``~gandalf/x`` 抛的就是那条
       RuntimeError，而 ``Path.home()`` 一切正常——这正是 Air 那次的情形）；
    2. 进程既没有 ``$HOME``，也查不到当前 uid 的 passwd 记录。

    ⚠️ ``~用户`` 解析不了时**绝不**退回「就当它是当前用户」——那会把库建到错误的位置。
    """
    text = (raw or "").strip()
    if not text:
        raise UserPathError("路径不能为空：请填写一个文件夹路径")

    if text == "~" or text.startswith("~/"):
        base = next(iter(_home_candidates(home)), None)
        if base is None:
            raise UserPathError(
                "解析不了「~」：这个服务进程读不到当前用户的家目录。"
                "请改用绝对路径（例如 /Users/你的用户名/Documents/Work/_vault）"
            )
        return base if text == "~" else base / text[2:]

    if text.startswith("~"):
        # `~用户名` 只能靠 passwd 库解析；用户不存在时 `expanduser()` 会**抛 RuntimeError**
        # （不是返回原串），所以这里必须先接住，再自己判断解析成功没有。
        try:
            expanded = Path(text).expanduser()
        except RuntimeError:
            expanded = Path(text)
        if str(expanded).startswith("~"):
            name = text[1:].split("/", 1)[0]
            raise UserPathError(
                f"解析不了「~{name}」：这台机器上没有这个用户。"
                "如果你指的是当前用户的家目录，请写成 ~/… 或直接用绝对路径"
                "（例如 /Users/你的用户名/Documents/Work/_vault）"
            )
        return expanded

    return Path(text)


def resolve_work_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """解析工作项目根目录 ``~/Documents/Work``（L9）。

    优先级：显式参数 > 环境变量 ``WORK_ROOT`` > 默认 ``$HOME/Documents/Work``。
    返回 ``expanduser`` 展开后的路径，但不要求其已存在（M0-1 不创建目录）。
    """
    candidate = explicit or os.environ.get("WORK_ROOT")
    if candidate:
        return Path(candidate).expanduser()
    return home_dir() / "Documents" / "Work"


@dataclass(frozen=True)
class WorkspacePaths:
    """单一权威路径解析结果：work_root / vault_dir / lock_root。

    - ``work_root``：工作项目根（env/显式；默认 ``$HOME/Documents/Work``）。
    - ``vault_dir``：vault 目录（默认 ``<work_root>/_vault``）。
    - ``lock_root``：工作区锁根 = vault 的容器目录；``.wb.lock`` 落在这里。
      默认形态（vault = ``<work_root>/_vault``）下它就是 ``work_root``；vault 被
      显式指到 work_root 下其它位置时锁根跟随 vault 容器。所有写者（web、brief、
      Feishu refresh、sync、CLI、仓库层）都以它为锁根，同一 workspace 共用同一把
      ``.wb.lock``，不因自定义 vault 路径分裂（P0-06）。

    vault 内部子目录（daily/projects/meetings/...）在各自 workflow 首次使用时按需派生，
    不在此预置未被使用的路径。
    """

    work_root: Path
    vault_dir: Path
    lock_root: Path

    @property
    def lock_file(self) -> Path:
        """本工作区的锁文件路径（``<lock_root>/.wb.lock``，不创建文件）。"""
        return self.lock_root / ".wb.lock"


# 兼容别名：早期调用方以 WorkPaths 引用旧 dataclass（含 settings 类型注解）。
WorkPaths = WorkspacePaths


def resolve_work_paths(
    work_root: str | os.PathLike[str] | None = None,
    vault_dir: str | os.PathLike[str] | None = None,
) -> WorkspacePaths:
    """派生 :class:`WorkspacePaths`（唯一的路径解析入口）。

    ``vault_dir`` 默认是 ``<work_root>/_vault``（PRD 3.1.5），可被显式覆盖；
    ``lock_root`` 恒为 vault 容器目录（默认形态下即 work_root），供所有锁调用取根。
    """
    root = resolve_work_root(work_root)
    vault = Path(vault_dir).expanduser() if vault_dir else root / "_vault"
    return WorkspacePaths(work_root=root, vault_dir=vault, lock_root=vault.parent)
