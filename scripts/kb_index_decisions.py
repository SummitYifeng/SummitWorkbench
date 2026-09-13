#!/usr/bin/env python3
"""Regenerate ``<vault>/_vault/index/decisions.md`` from ``decisions/*.md`` frontmatter.

为什么有这个脚本：``index/decisions.md`` 在自己的维护规则里写了「新增决策时同步更新本页」，
但那是句空话——手抄台账迟早漂移。决策是**唯一**能支撑「决策支持」类提问的资产，
台账必须可机械重生成。

与 ``kb_index_people.py``（旧轮遗留）的关键差别：**本脚本不改动既有 frontmatter**，
只替换 `## 生效中` / `## 待复核` / `## 已被替代` 三个区块的内容。
原因：``kb_index_people.py`` 自己造 frontmatter，会把新规范要求的
``id`` / ``area`` / ``workstream`` / ``summary`` 等字段抹掉（见 PLAN 的 Phase 5 遗留项）。

规则：

- 数据源＝``decisions/*.md`` 中 ``type: decision`` 的笔记；
- 分组：``superseded``（含 frontmatter ``status: superseded``）→ 已被替代；
  ``under-review`` 或 ``review_on`` 已到期 → 待复核；其余 → 生效中；
- 排序：生效中/已被替代按 ``decided_on`` 倒序，待复核按 ``review_on`` 正序，同日按文件名词典序；
- 条目格式：``- YYYY-MM-DD [[<stem>|<title 去掉「决定：」前缀>]]：<summary>``；
- 空分组写 ``_（暂无。）_``，不留空区。

用法::

    scripts/kb_index_decisions.py                 # 重生成 index/decisions.md
    scripts/kb_index_decisions.py --check         # 与磁盘不一致则退出码 1
    scripts/kb_index_decisions.py --today 2026-09-14   # 固定「今天」以便可重复校验
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

SKIP_STATUS = frozenset({"draft"})
SECTIONS = ("## 生效中", "## 待复核", "## 已被替代")
SECTION_RULES = "## 维护规则"
EMPTY = "_（暂无。）_"
TITLE_PREFIXES = ("决定：", "决定:", "决定｜")


def _split_frontmatter(text: str) -> tuple[str, dict[str, object], str] | None:
    """返回 (frontmatter 原文含围栏, meta, 正文)。解析失败返回 None。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    raw = text[: end + len("\n---")]
    body = text[end + len("\n---") :].lstrip("\n")
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None
    return (raw, meta, body) if isinstance(meta, dict) else None


def _text(value: object) -> str:
    """把 frontmatter 值转成可比较的字符串。

    ⚠️ 必须处理 ``datetime.date``：YAML 会把 ``decided_on: 2026-09-12`` 解析成 ``date``
    对象而不是 ``str``。第一版只认 ``str``，于是**所有决策都显示成「（日期未记）」**
    （2026-09-14 实测踩到，已补回归测试）。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _link_text(title: str, stem: str) -> str:
    cleaned = title.strip()
    for prefix in TITLE_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            break
    return cleaned or stem


def collect(decisions_dir: Path, *, today: str) -> dict[str, list[str]]:
    """按分组收集条目行；键是区块标题。"""
    groups: dict[str, list[tuple[str, str]]] = {section: [] for section in SECTIONS}
    if not decisions_dir.is_dir():
        return {section: [] for section in SECTIONS}
    for path in sorted(decisions_dir.glob("*.md")):
        parsed = _split_frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        _, meta, _ = parsed
        if _text(meta.get("type")) != "decision":
            continue
        if _text(meta.get("status")) in SKIP_STATUS:
            continue
        decided_on = _text(meta.get("decided_on")) or _text(meta.get("date"))
        review_on = _text(meta.get("review_on"))
        decision_status = _text(meta.get("decision_status"))
        superseded = decision_status == "superseded" or _text(meta.get("status")) == "superseded"

        line = (
            f"- {decided_on or '（日期未记）'} "
            f"[[{path.stem}|{_link_text(_text(meta.get('title')), path.stem)}]]"
            f"：{_text(meta.get('summary'))}"
        )
        if superseded:
            groups["## 已被替代"].append((decided_on, path.stem, line))
        elif decision_status == "under-review" or (review_on and review_on <= today):
            groups["## 待复核"].append((review_on or decided_on, path.stem, line))
        else:
            groups["## 生效中"].append((decided_on, path.stem, line))

    out: dict[str, list[str]] = {}
    for section, items in groups.items():
        if section == "## 生效中" or section == "## 已被替代":
            items.sort(key=lambda item: (item[0], item[1]), reverse=True)
        else:
            items.sort(key=lambda item: (item[0], item[1]))
        out[section] = [line for _, _, line in items]
    return out


def _split_sections(body: str) -> tuple[str, str]:
    """把正文拆成 (前导文本, `## 维护规则` 起的尾部原文)。"""
    idx = body.find(SECTION_RULES)
    if idx == -1:
        return body, f"{SECTION_RULES}\n"
    return body[:idx], body[idx:]


def render(existing_body: str, groups: dict[str, list[str]]) -> str:
    """保留既有正文的前导与维护规则，只替换三个分组区块。"""
    preamble, rules = _split_sections(existing_body)
    head = preamble.split("\n## ", 1)[0].rstrip("\n")
    lines = [head, ""]
    for section in SECTIONS:
        lines.append(section)
        lines.append("")
        entries = groups.get(section) or []
        lines.extend(entries or [EMPTY])
        lines.append("")
    return "\n".join(lines) + "\n" + rules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 decisions/*.md 重生成 index/decisions.md")
    default_vault = os.environ.get("WORK_ROOT", str(Path.home() / "Documents" / "Work"))
    parser.add_argument("--vault", type=Path, default=Path(default_vault))
    parser.add_argument(
        "--today", default=None, help="判定 review_on 到期用的「今天」（默认系统日期）"
    )
    parser.add_argument("--check", action="store_true", help="只校验，不写；过期则退出码 1")
    args = parser.parse_args(argv)

    vault = args.vault.expanduser() / "_vault"
    target = vault / "index" / "decisions.md"
    if not target.is_file():
        print(f"✗ 找不到 {target}", file=sys.stderr)
        return 2

    today = args.today or date.today().isoformat()
    parsed = _split_frontmatter(target.read_text(encoding="utf-8"))
    if parsed is None:
        print(f"✗ {target} 缺少可解析的 frontmatter", file=sys.stderr)
        return 2
    frontmatter, _, body = parsed

    groups = collect(vault / "decisions", today=today)
    expected = render(body, groups)
    actual = body if body.endswith("\n") else body + "\n"
    if actual == expected:
        print(f"✓ index/decisions.md 是最新的（{sum(len(v) for v in groups.values())} 篇决策）")
        return 0
    if args.check:
        print("✗ index/decisions.md 已过期：请运行 scripts/kb_index_decisions.py", file=sys.stderr)
        return 1

    target.write_text(frontmatter + "\n\n" + expected, encoding="utf-8")
    print(f"✓ 已重生成 index/decisions.md（{sum(len(v) for v in groups.values())} 篇决策）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
