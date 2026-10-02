"""界面文案口径守卫：**原生 macOS 壳**与**首启向导**（2026-09-14 原生壳文案扫描）。

背景：App SPA 之外的这两块不在 `web/src` 审计范围内，本轮扫出并修掉四类问题：
① 内部枚举 / rawValue 直贴给使用者；② 英文技术词打头的错误文案；③ 一条字面量缺陷
（更新提示把 `(version)` 原样打出来，版本号丢失）；④ 向导里 3 处错误文案漏了转义。

判据真源：使用者 2026-09-14 选择题 ④「主显中文名，英文 ID 放次要位置（小字 / hover），
只有『引用来源』保留完整路径」。

变异验证（改回去必须红）：
- 把 `"发现可用更新：\\(version)"` 退回 `"发现可用更新 (version)"` ⇒ 第 1 组红；
- 在 `presentFailure()` 里把中文状态名退回 `state.rawValue` ⇒ 第 2 组红；
- 把任一 `NSLocalizedDescriptionKey` 退回英文打头（如 `"bundle server …"`）⇒ 第 3 组红；
- 把向导的 `compatibilityText(...)` 退回 `escapeHtml(state.compatibility)` ⇒ 第 4 组红；
- 把 `escapeHtml(error.message)` 退回 `error.message` ⇒ 第 5 组红。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NATIVE = REPO / "native" / "SummitWorkbench"
ONBOARDING = REPO / "src" / "summit_workbench" / "webapp" / "onboarding_view.py"

CJK = re.compile(r"[\u4e00-\u9fff]")
# 面向使用者的调用：弹窗正文 / 状态条 / 提示行
USER_FACING_CALLS = ("presentError(", "messageText =", "informativeText =", "showStatus(")
LOCALIZED = re.compile(r'NSLocalizedDescriptionKey:\s*"((?:[^"\\]|\\.)*)"')


def _swift(name: str) -> str:
    return (NATIVE / name).read_text(encoding="utf-8")


def test_update_prompt_interpolates_the_version() -> None:
    """更新提示必须插值版本号（曾把 `(version)` 字面量打给使用者）。

    2026-09-14 收口：文案移到 `UICopy.swift` 的纯函数，由
    `native/tests/UICopyTests.swift` 做**功能**单测——因为这些是短中文字面量，
    Swift 的 small-string 优化会内联进代码，二进制里搜不到（见 `UICopy.swift` 注释）。
    """
    copy = _swift("UICopy.swift")
    # 只查代码行：注释里会**引用**这个错误写法作为说明（例如本文件的 docstring 与 UICopy 的注释）。
    code = "\n".join(
        line for line in copy.splitlines() if not line.strip().startswith(("//", "///"))
    )
    assert "(version)" not in code, "字面量 `(version)` 又回来了"
    assert 'trimmed.isEmpty ? "发现可用更新" : "发现可用更新：\\(trimmed)"' in copy, (
        "更新提示必须插值实际版本号"
    )
    lifecycle = _swift("LifecycleCoordinator.swift")
    assert "UICopy.updateAvailable(version: version)" in lifecycle, "协调器必须调用带版本号的纯函数"
    assert "UICopy.updateChecking" in lifecycle, "其余更新文案也要走纯函数"


def _function_body(text: str, signature: str) -> str:
    """粗切一个 Swift 函数体：从签名到下一个同缩进的 `func`。"""
    start = text.index(signature)
    rest = text[start:]
    match = re.search(r"\n    (?:private |)func ", rest)
    return rest[: match.start()] if match else rest


def test_user_facing_alerts_never_print_raw_state() -> None:
    """弹窗 / 状态条不得直接贴 `rawValue`（`crashLoop`、`degraded`… 是内部标识）。

    `copyDiagnostics()` 是**有意保留**的例外：那是复制给支持人员的诊断文本，
    里面必须带 `state.rawValue` / `frontend build` 这类精确标识。
    """
    lifecycle = _swift("LifecycleCoordinator.swift")
    for line_no, line in enumerate(lifecycle.splitlines(), 1):
        if any(call in line for call in USER_FACING_CALLS):
            assert "rawValue" not in line, (
                f"LifecycleCoordinator.swift:{line_no} 把 rawValue 贴给了使用者"
            )

    # 更狠一层：除诊断文本外，任何**字符串插值**里都不许出现 rawValue
    # （上一次变异验证暴露：只查调用行会漏掉「先算好 detail、再传给 presentError」的写法）。
    diagnostics = _function_body(lifecycle, "private func copyDiagnostics()")
    outside = lifecycle.replace(diagnostics, "")
    offenders = [
        line.strip()
        for line in outside.splitlines()
        if "\\(" in line and "rawValue" in line and not line.strip().startswith("///")
    ]
    assert not offenders, f"弹窗文案里直接插了 rawValue：{offenders}"

    # 中文状态名确实在（否则上面的断言可能只是「这段被删了」）
    assert "UICopy.supervisorState(current)" in lifecycle
    copy = _swift("UICopy.swift")
    for label in (
        "空闲",
        "正在探测服务",
        "正在启动",
        "已就绪",
        "降级运行",
        "正在重启",
        "反复启动失败",
        "端口被占用",
        "正在停止",
        "已停止",
        "未知",
    ):
        assert f'return "{label}"' in copy, f"UICopy 缺少状态中文名：{label}"


def test_localized_error_messages_are_chinese_first() -> None:
    """用户可见的错误文案必须中文打头，英文技术词只能进括号。"""
    checked = 0
    for path in sorted(NATIVE.glob("*.swift")):
        for match in LOCALIZED.finditer(path.read_text(encoding="utf-8")):
            message = match.group(1)
            checked += 1
            assert CJK.search(message), f"{path.name} 的错误文案没有中文：{message}"
            head = message[0]
            assert not head.isascii() or not head.islower(), (
                f"{path.name} 的错误文案以英文技术词打头：{message}"
            )
    assert checked >= 10, f"只扫到 {checked} 条错误文案，守卫可能失效"


def test_onboarding_wizard_maps_internal_enums_to_chinese() -> None:
    """向导确认页不得显示 `read-write` / `cannot-open` 这类后端枚举。"""
    page = ONBOARDING.read_text(encoding="utf-8")
    assert "escapeHtml(state.compatibility)" not in page, "兼容性又直接贴枚举了"
    assert "compatibilityText(state.compatibility)" in page
    # 三个枚举值都要有中文映射（新增取值时这里会红，提示补映射）
    for value in ("read-write", "read-only-upgrade-required", "cannot-open"):
        assert f"'{value}':" in page, f"兼容性映射缺少 {value}"
    # 工作区 UUID 只显示短标识（完整值进 title）
    assert "shortId(state.workspace_id)" in page
    assert "title=\"'+escapeHtml(state.workspace_id)+'\"" in page


def test_onboarding_wizard_escapes_error_messages() -> None:
    """向导里所有错误文案都必须过 `escapeHtml`（同一文件其它地方本来就是这么做的）。"""
    page = ONBOARDING.read_text(encoding="utf-8")
    assert "'<div class=\"error\">'+error.message" not in page, "有错误文案漏了转义"
    assert page.count("escapeHtml(error.message)") == 4
