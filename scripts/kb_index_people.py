#!/usr/bin/env python3
"""Regenerate ``<vault>/index/people.md`` from note frontmatter.

Why this file exists: ``index/people.md`` says in its own 维护规则 that it is
aggregated rather than hand-maintained, but the script that produced it was
written in ``/tmp`` and never committed — so the page was not reproducible.
This is that script, checked in.

Rules (kept identical to the hand-run version so regeneration is a no-op):

- sources are every ``*.md`` under the vault **except** ``templates/`` and the
  machine directories (``.git`` / ``.obsidian`` / ``_signals`` /
  ``.summit-workbench``);
- a note contributes to a name when the name appears in its frontmatter
  ``people`` (人物 section) or ``org`` (组织 section) list;
- notes are listed in vault-relative path order, first four shown as
  ``[[stem|stem]]``; a fifth and beyond collapse into ``（共 N 篇）``;
- names are ordered by note count descending, ties broken by name ascending.

Usage::

    scripts/kb_index_people.py                 # rewrite index/people.md
    scripts/kb_index_people.py --check         # exit 1 if the page is stale
    scripts/kb_index_people.py --date 2026-09-13
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from datetime import date
from pathlib import Path

import yaml

SKIP_DIRS = frozenset({".git", ".obsidian", "_signals", ".summit-workbench", "templates"})
PREVIEW = 4
TITLE = "人物与组织索引"

# 固定区块标题：`## 人物` / `## 组织` / `## 维护规则` 是约定的一部分（conventions.md），
# 改名会让 Obsidian 里的 `[[index/people#组织]]` 引用与索引检索一起断掉。
SECTION_PEOPLE = "人物"
SECTION_ORG = "组织"
SECTION_RULES = "维护规则"

RULES: tuple[str, ...] = (
    "- 笔记 frontmatter 的 `people` / `org` 用**自然语言原名**，全库保持一致。",
    "- 新增相关笔记时，本页由聚合脚本重生成，不需要手工维护条目。",
)

FOOTER_NOTE = (
    "> 由各笔记 frontmatter 的 `people` / `org` 字段聚合而成（可脚本再生成）。本页只做导航。"
)


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _frontmatter(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    rest = text.split("\n", 1)[1] if "\n" in text else ""
    end = rest.find("\n---")
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(rest[:end]) or {}
    except yaml.YAMLError:
        return None
    return meta if isinstance(meta, dict) else None


def collect(vault_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (人物 → notes, 组织 → notes), both in path order, keys in display order."""
    people: dict[str, list[str]] = {}
    orgs: dict[str, list[str]] = {}
    for path in sorted(vault_dir.rglob("*.md")):
        rel = path.relative_to(vault_dir)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        meta = _frontmatter(path)
        if meta is None:
            continue
        stem = rel.with_suffix("").name
        for name in _as_list(meta.get("people")):
            people.setdefault(name, []).append(stem)
        for name in _as_list(meta.get("org")):
            orgs.setdefault(name, []).append(stem)
    return people, orgs


def _ranked(index: dict[str, list[str]]) -> list[str]:
    """Count descending, then name ascending.

    The name tie-break is what the original hand-run script produced — verified by
    regenerating the shipped page byte-for-byte. It keeps the long tail of
    single-note names readable instead of filesystem-dependent.
    """
    return sorted(index, key=lambda name: (-len(index[name]), name))


def _line(name: str, notes: list[str]) -> str:
    shown = "、".join(f"[[{stem}|{stem}]]" for stem in notes[:PREVIEW])
    suffix = f"（共 {len(notes)} 篇）" if len(notes) > PREVIEW else ""
    return f"- **{name}**：{shown}{suffix}"


def render(
    people: dict[str, list[str]],
    orgs: dict[str, list[str]],
    *,
    created: str,
    updated: str,
) -> str:
    lines = [
        "---",
        f"date: {created}",
        "type: index",
        "status: active",
        "project: global",
        f"updated: {updated}",
        f"title: {TITLE}",
        "aliases: [People, 人物索引]",
        "---",
        "",
        f"# {TITLE}",
        "",
        FOOTER_NOTE,
        "",
        f"## {SECTION_PEOPLE}",
        "",
    ]
    lines += [_line(name, people[name]) for name in _ranked(people)]
    # 既有文件里 `## 组织` 紧跟最后一条人物条目（无空行），保持一致以免产生无意义 diff。
    lines += [f"## {SECTION_ORG}", ""]
    lines += [_line(name, orgs[name]) for name in _ranked(orgs)]
    lines += [f"## {SECTION_RULES}", "", *RULES, ""]
    return "\n".join(lines)


def _existing_frontmatter(path: Path) -> dict[str, object]:
    return _frontmatter(path) or {}


def _body(text: str) -> str:
    """Everything after the closing frontmatter fence (used by --check)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + len("\n---") :].lstrip("\n")


def _frontmatter_raw(text: str) -> str | None:
    """既有页面的 frontmatter 原文（含围栏）；没有则 None。

    为什么需要它：`render()` 会自带一份最小 frontmatter（只有 date/type/status/project/
    updated/title/aliases）。直接写盘会把页面已有的 `id` / `area` / `workstream` /
    `summary` 等**新规范要求的字段整段抹掉**（2026-09-14 发现）。写入时必须保留既有
    frontmatter，只替换正文——与 `kb_index_decisions.py` 同一约定。
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[: end + len("\n---")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 frontmatter 重生成 index/people.md")
    default_vault = os.environ.get("WORK_ROOT", str(Path.home() / "Documents" / "Work"))
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(default_vault),
        help="Work 父目录或 _vault 本身（默认 $WORK_ROOT 或 ~/Documents/Work）",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="输出文件（默认 <vault>/_vault/index/people.md）"
    )
    parser.add_argument("--date", default=None, help="frontmatter 的 updated（默认今天）")
    parser.add_argument("--check", action="store_true", help="只校验，不写；过期则退出码 1")
    args = parser.parse_args(argv)

    vault_root = args.vault.expanduser().resolve()
    # 允许两种指法：给「库根」（~/Documents/Work，_vault 是它的子目录）或直接给笔记目录。
    vault_dir = vault_root / "_vault" if (vault_root / "_vault").is_dir() else vault_root
    target = (args.output or (vault_dir / "index" / "people.md")).expanduser()
    if not (vault_dir / "conventions.md").is_file():
        print(f"✗ 这不像是工作知识库根目录（缺 conventions.md）：{vault_dir}", file=sys.stderr)
        return 2

    updated = args.date or date.today().isoformat()
    created = str(_existing_frontmatter(target).get("date") or updated)
    people, orgs = collect(vault_dir)
    rendered = render(people, orgs, created=created, updated=updated)

    if args.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if _body(current) == _body(rendered):
            print(
                f"✓ index/people.md 与 frontmatter 一致（{len(people)} 位人物，{len(orgs)} 个组织）"
            )
            return 0
        diff = difflib.unified_diff(
            _body(current).splitlines(),
            _body(rendered).splitlines(),
            fromfile=str(target),
            tofile="重新聚合的结果",
            lineterm="",
        )
        print("✗ index/people.md 已过期，请重跑本脚本：", file=sys.stderr)
        for line in list(diff)[:40]:
            print(line, file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    front = _frontmatter_raw(existing)
    text = f"{front}\n\n{_body(rendered)}" if front else rendered
    target.write_text(text, encoding="utf-8")
    print(f"✓ 已写入 {target}（{len(people)} 位人物，{len(orgs)} 个组织）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
