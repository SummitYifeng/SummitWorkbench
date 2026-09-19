#!/usr/bin/env python3
"""双链、块级锚点与有明确来源上下文的裸锚点自检（只读）。

校验两件事：

1. 正文里的 `[[目标]]` / `[[目标#区块]]`（含 `[[目标|中文名]]` 形式）能否解析到真实文件、
   锚点是否是真实标题；
2. 反引号里的 `路径#区块` 引用（检索答案与 `## 证据` 区的引用格式）能否解析到真实文件与真实标题。

为什么需要它：`路径#区块` 是我们与 Obsidian 共用的引用契约，而**标题层级一变锚点就会静默失效**
（2026-09-13 踩过 H2 降级的坑，2026-09-14 又遇到 H1 不构成块边界）。入库后必须机械校验。

用法：

    .venv/bin/python scripts/kb_verify_links.py        # 默认校验 settings 解析出的 vault
    .venv/bin/python scripts/kb_verify_links.py <vault 路径>
    .venv/bin/python scripts/kb_verify_links.py <vault 路径> --quiet

覆盖范围（读结论前先看）：

- **覆盖**：`[[目标]]` / `[[目标#区块]]`（含 `|别名`）、`` `路径#区块` ``，以及**有唯一来源上下文**
  的裸锚点 `` `#区块` ``；
- **不覆盖**：`###` 及更深的锚点（契约只把 `#` / `##` 当块边界，见 conventions §13 遗留 12）；
  以及**没有或无法唯一确定来源页**的裸锚点（§13 遗留 13 登记的形态：`inbox.md`、
  `index/sop.md`、`review/meetings.md`、`decisions/*`、部分 `sources/*`、
  `conventions.md` 自身举例）。
- ⚠️ **2026-09-19 覆盖回归**：`source_context` 曾"只看首块"，第五阶段把 H1 前的前言并进第一个
  `##` 后首块只剩 H1 ⇒ 两页来源推不出来 ⇒ 裸锚点计数 **56 → 0**（门禁不再校验，却仍报
  "全部可解析"）。现在改为**扫全篇标记行 + 开头区块收敛**，计数恢复 56。

退出码：0 = 全部可解析；1 = 存在死链或失效锚点；2 = 路径不存在。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from summit_workbench.domain.markdown_blocks import chunk_markdown  # noqa: E402

# 机器目录与模板不参与双链（与 conventions.md §0 一致）。
SKIP_DIRS = frozenset(
    {".git", ".obsidian", "_signals", ".summit-workbench", "templates", "node_modules"}
)

WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+?))?(?:\|[^\]]*)?\]\]")
PATH_REF = re.compile(r"`([^`\n]+?)#([^`\n]+?)`")
FENCED_BLOCK = re.compile(r"^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$", re.S | re.M)
# 行内代码里的 `[[…]]` 是**文档在举例**，不是真链接（Obsidian 也不会把它渲染成链接）。
INLINE_CODE = re.compile(r"`[^`\n]*`")
BARE_REF = re.compile(r"`#([^`\n]+?)`")
SOURCE_PATH = re.compile(r"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.md)")
# 来源标记行：只认这些词所在的行。拉丁词用**词界**，否则路径 `…/sources/x.md` 里的
# "sources" 会被当成 "source" 标记，把"正文里提到的路径"误判成来源（假歧义）。
SOURCE_MARKER = re.compile(r"来源|出处|真源|原件|副本|\bsource\b|\bcopy\b", re.I)


def markdown_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in vault.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.relative_to(vault).parts)
    )


def headings(source_id: str, text: str) -> set[str]:
    """Return only the addressable H1/H2 headings, using shared chunk rules."""
    return {chunk.heading for chunk in chunk_markdown(source_id, text) if chunk.heading}


def _source_candidates(
    text: str, by_rel: dict[str, Path], basenames: set[str], self_path: Path | None
) -> list[Path]:
    """扫描 ``text`` 里「来源标记行」上出现的、**能解析且不是本页自身**的路径。

    - 只认 :data:`SOURCE_MARKER` **标记行**：不扫全部正文，否则正文里提到的路径会被误判成来源；
    - 只收**能在库内解析**的路径：`source` 页的「原件」常是本机绝对路径（如
      `/Users/…/Desktop/…`），那些不是库内来源上下文；
    - 排除**本页自身**：`source` 页的 `## 来源` 会列「vault 内副本」＝本页，自指不是来源上下文。
    """
    found: list[Path] = []
    for line in text.splitlines():
        if not SOURCE_MARKER.search(line):
            continue
        for raw in SOURCE_PATH.findall(line):
            resolved = resolve(raw, by_rel, basenames)
            if resolved is not None and resolved != self_path:
                found.append(resolved)
    return list(dict.fromkeys(found))


def source_context(
    body: str,
    by_rel: dict[str, Path],
    basenames: set[str],
    self_path: Path | None = None,
) -> tuple[Path | None, bool]:
    """推断本页裸锚点所属的**来源页**；返回 ``(来源, 是否歧义)``。

    为什么要扫全篇（2026-09-19 覆盖回归）：此前只看 ``chunks[0]``。第五阶段把 H1 之前的
    前言并进了第一个 ``##`` 区块（即 ``chunks[1]``），``chunks[0]`` 于是只剩 H1，两页的
    来源指针被移出扫描范围——「裸锚点」计数从 56 **静默**掉到 0：门禁不再校验它们，却仍
    显示"全部可解析"。

    判据（保持「唯一才算得出，多义视为无法判定」的语义）：

    1. 只认 :data:`SOURCE_MARKER` **标记行**（不扫全部正文）；
    2. 候选只收能解析、且不是本页自身的路径；
    3. **全篇**恰好一个候选 → 用它（来源只在一处被提到时也能找到；
       也覆盖"标记行在第二个块里"的第五阶段形态）；
    4. 全篇多个候选时，收敛到**开头区块**（首块 + 第一个 ``#``/``##`` 区块，正是第五阶段
       前言并段的落点）里声明的那个；开头也恰好一个 → 用它；
    5. 否则视为"无法判定"：开头仍多个 → 歧义（沿用改前语义，报问题）；一个都没有 → 不计数。
    """
    content = body
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            content = body[end + len("\n---") :].lstrip("\n")
    chunks = chunk_markdown("", content)
    if not chunks:
        return None, False
    whole = _source_candidates(content, by_rel, basenames, self_path)
    if len(whole) == 1:
        return whole[0], False
    opening = _source_candidates(
        "\n".join(chunk.text for chunk in chunks[:2]), by_rel, basenames, self_path
    )
    if len(opening) == 1:
        return opening[0], False
    return None, len(opening) > 1


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
    heading_cache = {
        path: headings(path.relative_to(vault).with_suffix("").as_posix(), body)
        for path, body in bodies.items()
    }

    problems: list[str] = []
    link_count = 0
    ref_count = 0
    bare_count = 0

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

        bare_refs = [
            match
            for match in BARE_REF.finditer(prose)
            if not match.group(1).lstrip().startswith("#")
        ]
        if bare_refs:
            source, ambiguous = source_context(body, by_rel, basenames, path)
            if ambiguous:
                problems.append(f"{rel}: 裸锚点来源上下文有歧义，无法安全解析")
            elif source is not None:
                bare_count += len(bare_refs)
                for match in bare_refs:
                    block = match.group(1).strip()
                    if block not in heading_cache[source]:
                        problems.append(f"{rel}: 裸锚点失效 `#{block}`（来源无此标题）")

    if not args.quiet:
        print(f"vault：{vault}")
        print(
            f"扫描：{len(files)} 篇 Markdown｜双链 {link_count} 条｜"
            f"`路径#区块` 引用 {ref_count} 条｜裸锚点 {bare_count} 条"
        )
    if problems:
        print(f"✗ 发现 {len(problems)} 个问题：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("✓ 全部双链与块级锚点均可解析")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
