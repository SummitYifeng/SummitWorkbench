#!/usr/bin/env python3
"""校验工作库的**库内模板**是否「插入即合法」。

为什么需要它：`_vault/templates/` 在仓库之外，`tests/unit/test_vault_templates.py` 只覆盖仓库自带的
种子模板（`templates/vault/`），**覆盖不到使用者库里的模板**。2026-09-14 实测发现库内 16 个模板
**全部**在 frontmatter 里留了未加引号的 `{{…}}` 占位符 —— 这在 YAML 层是非法映射，于是
「照指南插入模板 → 保存」会产出**过不了 `wb vault check`** 的页面。修好之后用本脚本把这条守住。

判据（等价于使用者的真实动作）：只做 Obsidian 核心模板插件会自动完成的替换
（`{{date}}` / `{{time}}` / `{{title}}`），**其余占位符原样保留**，然后要求该页能通过
`parse_frontmatter` + `validate_note`。也就是说：使用者只改正文、不填任何占位符，也必须合法。

用法：

    python scripts/kb_check_templates.py                 # 默认查 ~/Documents/Work/_vault/templates
    python scripts/kb_check_templates.py --templates <目录>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from summit_workbench.domain.vault import validate_note
from summit_workbench.repositories.vault import parse_frontmatter

# Obsidian 核心「模板」插件会自动替换的占位符；其余占位符在真实使用中会原样留下。
_AUTO_REPLACEMENTS = {
    "{{date}}": "2026-01-01",
    "{{time}}": "12:00",
    "{{title}}": "样例标题",
}

DEFAULT_TEMPLATES = Path("~/Documents/Work/_vault/templates")

# 尚未被 Obsidian 替换的占位符（例如 {{project}}、{{对象名称}}）。
_PLACEHOLDER = re.compile(r"\{\{[^{}]*\}\}")
# 替换模式下的合法占位值：满足项目 ID 字符集，且不是日期/枚举类字段的合法值也不会误报。
_SENTINEL = "sample"


def render_as_obsidian(text: str, *, placeholders: str = "keep") -> str:
    """模拟 Obsidian 插入模板时的自动替换（只替换它认识的那几个占位符）。

    ``placeholders="keep"``（默认）：其余占位符**原样保留**——判据是「人插入后不改绑定字段也能用」，
    适用于**使用者库内、人直接插入使用的模板**。
    ``placeholders="substitute"``：把剩余占位符换成合法占位值再校验——判据是「骨架结构本身合法」，
    适用于**参考骨架**（如仓库种子模板；它们的占位符本来就该由人填写）。
    """
    for key, value in _AUTO_REPLACEMENTS.items():
        text = text.replace(key, value)
    if placeholders == "substitute":
        text = _PLACEHOLDER.sub(_SENTINEL, text)
    return text


def check_template(path: Path, *, placeholders: str = "keep") -> list[str]:
    """返回问题列表；空列表表示通过当前判据。"""
    translated = render_as_obsidian(path.read_text(encoding="utf-8"), placeholders=placeholders)
    meta, body, error = parse_frontmatter(translated)
    if error is not None:
        return [f"frontmatter 解析失败：{error}"]
    return [str(issue) for issue in validate_note(meta, body)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验库内模板是否「插入即合法」")
    parser.add_argument(
        "--placeholders",
        choices=("keep", "substitute"),
        default="keep",
        help="keep=占位符原样保留也必须合法（人直接用的模板，默认）；substitute=先替换占位符再校验（参考骨架）",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=DEFAULT_TEMPLATES,
        help=f"模板目录（默认 {DEFAULT_TEMPLATES}）",
    )
    args = parser.parse_args(argv)

    templates_dir = args.templates.expanduser()
    if not templates_dir.is_dir():
        print(f"✗ 模板目录不存在：{templates_dir}", file=sys.stderr)
        return 2

    files = sorted(templates_dir.glob("*.template.md"))
    if not files:
        print(f"✗ 目录里没有 *.template.md：{templates_dir}", file=sys.stderr)
        return 2

    failures: list[tuple[Path, list[str]]] = []
    for path in files:
        problems = check_template(path, placeholders=args.placeholders)
        if problems:
            failures.append((path, problems))
            print(f"✗ {path.name}")
            for problem in problems:
                print(f"    - {problem}")

    total = len(files)
    if failures:
        print(f"\n✗ {len(failures)}/{total} 个模板「插入不合法」——使用者照它建页会过不了校验。")
        print("  提示：① frontmatter 里的 {{…}} 占位符必须加引号，否则 YAML 视为非法映射；")
        print("        ② 绑定字段（project/projects）里的占位符要人填真实值——若这是参考骨架，")
        print("           请用 --placeholders substitute 复核结构本身是否合法。")
        return 1

    if args.placeholders == "keep":
        print(f"✓ {total} 个模板全部「插入即合法」（只做 Obsidian 自动替换也能通过 schema）")
    else:
        print(f"✓ {total} 个模板在「占位符替换为合法值后」全部通过 schema（参考骨架判据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
