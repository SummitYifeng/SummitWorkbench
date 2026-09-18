#!/usr/bin/env python3
"""检查 ``<vault>/decisions/*.md`` 是否混入了**知识库自身机制**的描述。

为什么有这个脚本：决策页回答的是"业务上定了什么"，不是"这份材料该放哪一页"。
2026-09-18 清理时发现，早期由 Agent 代写的决策把归属判定 / 素材落点 / 双链 / 闭掉未决条目
这类**库机制话术**写进了正文，读者要翻两层才知道业务结论是什么。该规范写进了
``conventions.md`` §7，本脚本是它的机器守卫——**只在维护 vault 时运行**，不依赖业务内容。

用法::

    scripts/kb_check_decision_hygiene.py                      # 默认 ~/Documents/Work/_vault
    scripts/kb_check_decision_hygiene.py --vault <path>
    scripts/kb_check_decision_hygiene.py --vault <path> --list-hits

退出码：0 = 干净；1 = 有命中（需人工判断是"库机制描述"还是业务用词）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 只收**明确指向本库机制**的词。刻意不含「索引」「字段」等业务里也常见的词——
# 守卫宁可少报，也不要制造假阳性让人忽略它。
LIBRARY_MECHANICS = (
    "归属判定",
    "素材落点",
    "本库块边界",
    "检索层拿不到",
    "不入库",
    "入库管线",
    "闭掉未决条目",
    "不设两份",
    "不在两边各写一份",
    "本决定的落点",
    "该记在哪条线",
    "按 conventions",
    "见 conventions §",
)
# 命中这些行视为**合法引用**（出处指针、frontmatter、关联区块的导航），不算违规。
ALLOWED_CONTEXT = re.compile(r"^\s*(#|-\s*\[\[|source:|aliases:|tags:|id:|title:)")


def scan(vault: Path, *, list_hits: bool) -> int:
    decisions = sorted((vault / "decisions").glob("*.md"))
    if not decisions:
        print(f"✗ 没有找到决策页：{vault / 'decisions'}", file=sys.stderr)
        return 1
    problems: list[tuple[Path, int, str, str]] = []
    for path in decisions:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if ALLOWED_CONTEXT.match(line):
                continue
            for token in LIBRARY_MECHANICS:
                if token in line:
                    problems.append((path, number, token, line.strip()))
                    break
    if not problems:
        print(f"✓ {len(decisions)} 篇决策页：未发现库机制描述")
        return 0
    print(f"✗ {len(problems)} 处疑似库机制描述（{len({p for p, *_ in problems})} 篇决策页）：")
    for path, number, token, line in problems:
        if list_hits:
            print(f"  {path.name}:{number} [{token}] {line[:120]}")
        else:
            print(f"  {path.name}:{number} [{token}]")
    print(
        "\n判断口径见 conventions.md §7：决策页只记业务结论。若确认是业务用词，请调窄上面的词表。"
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="决策页卫生检查（库机制描述）")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path.home() / "Documents" / "Work" / "_vault",
        help="vault 路径（默认 ~/Documents/Work/_vault）",
    )
    parser.add_argument("--list-hits", action="store_true", help="打印命中行原文")
    args = parser.parse_args()
    return scan(args.vault, list_hits=args.list_hits)


if __name__ == "__main__":
    raise SystemExit(main())
