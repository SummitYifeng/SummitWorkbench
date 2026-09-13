#!/usr/bin/env python3
"""双链与块级锚点自检（只读，可对任意 vault 路径运行）。

校验两件事：

1. 正文里的 `[[目标]]` / `[[目标#区块]]`（含 `[[目标|中文名]]` 形式）能否解析到真实文件、锚点是否是真实标题；
2. 反引号里的 `路径#区块` 引用（检索答案与 `## 证据` 区的引用格式）能否解析到真实文件与真实标题。

为什么需要它：`路径#区块` 是我们与 Obsidian 共用的引用契约，而**标题层级一变锚点就会静默失效**
（2026-09-13 踩过 H2 降级的坑，2026-09-14 又遇到 H1 不构成块边界）。入库后必须机械校验。

用法：

    .venv/bin/python scripts/kb_verify_links.py                    # 默认校验 settings 解析出的 vault
    .venv/bin/python scripts/kb_verify_links.py <vault 路径>
    .venv/bin/python scripts/kb_verify_links.py <vault 路径> --quiet

退出码：0 = 全部可解析；1 = 存在死链或失效锚点；2 = 路径不存在。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 机器目录与模板不参与双链（与 conventions.md §0 一致）。
SKIP_DIRS = frozenset({".git", ".obsidian", "_signals", ".summit-workbench", "templates", "node_modules"})

WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+?))?(?:\|[^\]]*)?\]\]")
PATH_REF = re.compile(r"`([^`\n]+?)#([^`\n]+?)`")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCED_BLOCK = re.compile(r"^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$", re.S | re.M)
# 行内代码里的 `[[…]]` 是**文档在举例**，不是真链接（Obsidian 也不会把它渲染成链接）。
INLINE_CODE = re.compile(r"`[^`\n]*`")


def markdown_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in vault.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.relative_to(vault).parts)
    )


def headings(text: str) -> set[str]:
    found: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(stripped)
        if match:
            found.add(match.group(2).strip())
    return found


def build_maps(files: list[Path], vault: Path) -> tuple[dict[str, Path], set[str], dict[Path, str]]:
    """返回 (无扩展名相对路径 → 文件, 所有 basename, 文件 → 正文)。"""
    by_rel: dict[str, Path] = {}
    basenames: set[str] = set()
    bodies: dict[Path, str] = {}
    for path in files:
        rel = path.relative_to(vault).with_suffix("").as_posix()
        by_rel[rel] = path
        basenames.add(path.stem)
        try:
            bodies[path] = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - 读取失败原样报告
            bodies[path] = ""
            print(f"! 读取失败 {path}：{exc}", file=sys.stderr)
    return by_rel, basenames, bodies


def resolve(target: str, by_rel: dict[str, Path], basenames: set[str]) -> Path | None:
    cleaned = target.strip().rstrip("\\").strip()
    if cleaned.endswith(".md"):
        cleaned = cleaned[: -len(".md")]
    if cleaned in by_rel:
        return by_rel[cleaned]
    stem = Path(cleaned).name
    if stem in basenames:
        # 同名多文件：交给调用方按 basename 命中处理（Obsidian 也这么做）
        for rel, path in by_rel.items():
            if Path(rel).name == stem:
                return path
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 vault 双链与块级锚点")
    parser.add_argument("vault", nargs="?", help="vault 目录；默认取 settings 解析结果")
    parser.add_argument("--quiet", action="store_true", help="只打印结论")
    args = parser.parse_args(argv)

    if args.vault:
        vault = Path(args.vault).expanduser()
    else:
        from summit_workbench.config.settings import load_settings

        vault = load_settings().work_paths().vault_dir
    if not vault.is_dir():
        print(f"✗ vault 不存在：{vault}")
        return 2

    files = markdown_files(vault)
    by_rel, basenames, bodies = build_maps(files, vault)
    heading_cache = {path: headings(body) for path, body in bodies.items()}

    problems: list[str] = []
    link_count = 0
    ref_count = 0

    for path in files:
        rel = path.relative_to(vault).as_posix()
        body = bodies[path]
        # 围栏代码块整体不算正文；行内代码只在找双链时剔除（`路径#区块` 引用本身
        # 就以行内代码形式书写，剔除会让它扫不到）。
        prose = FENCED_BLOCK.sub("", body)
        link_scan = INLINE_CODE.sub("", prose)

        for match in WIKILINK.finditer(link_scan):
            target, anchor = match.group(1), match.group(2)
            link_count += 1
            resolved = resolve(target, by_rel, basenames)
            if resolved is None:
                problems.append(f"{rel}: 死链 [[{target}]]")
                continue
            if anchor:
                wanted = anchor.strip()
                if wanted not in heading_cache[resolved]:
                    problems.append(f"{rel}: 锚点失效 [[{target}#{wanted}]]（目标无此标题）")

        for match in PATH_REF.finditer(prose):
            ref_path, block = match.group(1).strip(), match.group(2).strip()
            if "/" not in ref_path or "://" in ref_path:
                continue
            resolved = resolve(ref_path, by_rel, basenames)
            if resolved is None:
                continue  # 非库内引用（例如本机绝对路径），跳过
            ref_count += 1
            if block not in heading_cache[resolved]:
                problems.append(f"{rel}: `路径#区块` 锚点失效 `{ref_path}#{block}`")

    if not args.quiet:
        print(f"vault：{vault}")
        print(f"扫描：{len(files)} 篇 Markdown｜双链 {link_count} 条｜`路径#区块` 引用 {ref_count} 条")
    if problems:
        print(f"✗ 发现 {len(problems)} 个问题：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("✓ 全部双链与块级锚点均可解析")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
