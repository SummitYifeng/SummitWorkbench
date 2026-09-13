#!/usr/bin/env python3
"""工作知识库（工作库）源材料入库器：把仓库外的原始材料归档为 vault 内的 `source` / 逐字稿笔记。

设计要点（对应 conventions.md §13）：

- **原件不可变**：正文逐字保留；只把 ATX 标题整体降一级，使「一篇一个一级标题」成立，
  并让章节成为 `##` 区块（检索分块与「路径#区块」引用的锚点）。
- **幂等**：以 `(source.ref, content_sha256)` 为键。同一份材料重复入库**不会**产生重复笔记。
- **判重不猜测**：同 `ref` 但内容哈希不同 → **不覆盖、不新建**，报冲突并以退出码 2 结束，
  交给人工决定（这是「出现脏数据必须停下来问」的落点）。
- **只写内容，不写机器状态**：哈希写进笔记 frontmatter（`source.hash`），不额外落状态文件。

用法：

    python scripts/kb_intake.py --vault ~/Documents/Work/_vault --check   # 只报告
    python scripts/kb_intake.py --vault ~/Documents/Work/_vault           # 落盘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

HEADING_RE = re.compile(r"^#{1,6} ")
EXIT_OK = 0
EXIT_DRIFT = 2


@dataclass(frozen=True)
class Material:
    """一份待入库的原始材料及其目标笔记形态。"""

    src: str  # 相对 MATERIALS_ROOT 的路径
    target: str  # vault 相对路径
    note_type: str  # source | meeting-transcript
    date: str
    title: str
    workstream: str
    domain: str
    kind: str  # source.kind：doc | transcript | meeting | feishu | email | manual
    summary: str
    points: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    org: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()  # 仅 meeting-transcript 使用（multi scope）
    transcript_title: str = ""  # 仅 meeting-transcript：正文一级标题
    demote_headings: bool = True


MATERIALS_ROOT = Path("~/Desktop/当前材料")


def load_manifest(path: Path) -> list[Material]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Material(
            src=item["src"],
            target=item["target"],
            note_type=item["note_type"],
            date=item["date"],
            title=item["title"],
            workstream=item["workstream"],
            domain=item["domain"],
            kind=item["kind"],
            summary=item["summary"],
            points=tuple(item.get("points", ())),
            tags=tuple(item.get("tags", ())),
            people=tuple(item.get("people", ())),
            org=tuple(item.get("org", ())),
            aliases=tuple(item.get("aliases", ())),
            projects=tuple(item.get("projects", ())),
            transcript_title=item.get("transcript_title", ""),
            demote_headings=bool(item.get("demote_headings", True)),
        )
        for item in raw
    ]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


FENCE_RE = re.compile(r"^\s*(?:```|~~~)")


def normalise_body(text: str, *, demote: bool) -> str:
    """原文逐字保留；仅按需把 ATX 标题整体降一级（首行一级标题保留为笔记标题）。

    ⚠️ **围栏代码块内不降级**：模板类材料里常有 ```markdown 包住的示例，其 `# 标题`
    是示例内容而不是章节标题。若一并降级，它们会在 source 笔记里变成真实的 `##` 区块，
    从而污染检索分块与「路径#区块」锚点（2026-09-13 实测踩到）。
    """
    lines = text.rstrip("\n").splitlines()
    if not demote:
        return "\n".join(lines)
    out = [lines[0]]
    in_fence = False
    for line in lines[1:]:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append("#" + line if not in_fence and HEADING_RE.match(line) else line)
    return "\n".join(out)


def scan_ingested(vault: Path) -> tuple[dict[tuple[str, str], Path], dict[str, Path]]:
    """扫描 vault 内已入库的 source/逐字稿。

    返回 ``({(ref, hash): 路径}, {hash: 路径})``：前者用于「同一材料重复入库」，
    后者用于**内容相同但文件名不同**（例如两份逐字稿其实是同一份转写导出两次）的去重。
    """
    seen: dict[tuple[str, str], Path] = {}
    by_hash: dict[str, Path] = {}
    for path in sorted(vault.rglob("*.md")):
        parts = path.relative_to(vault).parts
        if any(p in {".git", ".obsidian", "_signals", "templates"} for p in parts):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        front = text.split("\n", 1)[1]
        end = front.find("\n---")
        if end == -1:
            continue
        try:
            meta = yaml.safe_load(front[:end]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(meta, dict) or meta.get("type") not in {"source", "meeting-transcript"}:
            continue
        source = meta.get("source")
        if isinstance(source, dict):
            ref = str(source.get("ref") or "")
            digest = str(source.get("hash") or "")
        else:  # meeting-transcript 用顶层 source: transcript
            ref = str(meta.get("transcript_ref") or "")
            digest = str(meta.get("content_sha256") or "")
        if ref and digest:
            seen[(ref, digest)] = path
        if digest:
            by_hash.setdefault(digest, path)
    return seen, by_hash


def render_frontmatter(material: Material, digest: str) -> str:
    lines = [
        "---",
        f"id: {material.date}-{sha256_text(material.target)[:4]}",
        f"title: {material.title}",
        "area: work",
        f"workstream: {material.workstream}",
        f"type: {material.note_type}",
        f"domain: {material.domain}",
        f"status: {'archived' if material.note_type == 'meeting-transcript' else 'active'}",
        f"created: {material.date}",
        f"updated: {material.date}",
        f"date: {material.date}",
        f"summary: {material.summary}",
        f"tags: {list(material.tags)}",
        f"aliases: {list(material.aliases)}",
        f"people: {list(material.people)}",
        f"org: {list(material.org)}",
        "confidential: false",
    ]
    if material.note_type == "meeting-transcript":
        lines.append(f"projects: {list(material.projects)}")
        lines.append(f"transcript_ref: {material.src}")
        lines.append(f"content_sha256: {digest}")
    else:
        lines.append("source:")
        lines.append(f"  kind: {material.kind}")
        lines.append(f"  ref: {material.src}")
        lines.append(f"  date: {material.date}")
        lines.append(f"  hash: {digest}")
    lines.append("---")
    return "\n".join(lines)


def render_source_note(material: Material, digest: str, body: str) -> str:
    if material.note_type == "meeting-transcript":
        return (
            render_frontmatter(material, digest)
            + f"\n\n# {material.transcript_title or material.title}\n\n{body}\n"
        )
    points = "\n".join(f"- {p}" for p in material.points) or "<!-- 待补充：忠于原文的要点 -->"
    return "\n".join(
        [
            render_frontmatter(material, digest),
            "",
            "## 来源",
            "",
            f"- 原始文件名：`{Path(material.src).name}`",
            f"- 收到位置：`{MATERIALS_ROOT}/{material.src}`"
            "（仓库外，未进 Git；全文已逐字收录于本笔记正文）",
            f"- 内容 sha256：`{digest}`",
            f"- 材料性质：{material.summary}",
            "- 结构归一：文本**逐字保留**；仅将 ATX 标题整体降一级，使「一篇一个一级标题」成立，",
            "  并让各章节成为 `##` 区块（检索分块与「路径#区块」引用的锚点）",
            "- 本文件**不可变**：任何改写、提炼都写进同工作线的 `notes/`，不要就地改本文件",
            "",
            "## 要点",
            "",
            points,
            "",
            body,
            "",
            "---",
            "",
            "## 关联",
            "",
            "<!-- 双链候选见 `review/kb-intake.md`；经人工确认后写回本区 -->",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="工作库源材料入库（幂等 + 判重）")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("scripts/kb_intake_manifest.json"))
    parser.add_argument("--materials-root", type=Path, default=MATERIALS_ROOT)
    parser.add_argument("--check", action="store_true", help="只报告，不写盘")
    args = parser.parse_args()

    vault: Path = args.vault.expanduser().resolve()
    if not vault.is_dir():
        print(f"vault 不存在：{vault}", file=sys.stderr)
        return 1

    materials = load_manifest(args.manifest)
    ingested, by_hash = scan_ingested(vault)
    root = args.materials_root.expanduser()

    written = skipped = 0
    drift: list[str] = []
    for material in materials:
        source_path = root / material.src
        if not source_path.is_file():
            print(f"✗ 缺少原始材料：{source_path}", file=sys.stderr)
            return 1
        raw = source_path.read_text(encoding="utf-8")
        digest = sha256_text(raw)
        if (material.src, digest) in ingested:
            print(f"= 已入库（跳过，幂等）  {material.target}")
            skipped += 1
            continue
        duplicate_of = by_hash.get(digest)
        if duplicate_of is not None:
            print(
                f"= 内容与 {duplicate_of.relative_to(vault)} 完全相同（同 sha256），"
                f"按重复材料跳过：{material.src}"
            )
            skipped += 1
            continue
        same_ref = [p for (ref, _h), p in ingested.items() if ref == material.src]
        if same_ref:
            drift.append(
                f"{material.src}：同 ref 但内容哈希不同；已存在 "
                f"{', '.join(str(p.relative_to(vault)) for p in same_ref)}"
            )
            continue
        target_path = vault / material.target
        if target_path.exists():
            drift.append(f"{material.target}：目标文件已存在但未被识别为同一材料")
            continue
        body = normalise_body(raw, demote=material.demote_headings)
        note = render_source_note(material, digest, body)
        if args.check:
            print(f"+ 将写入  {material.target}  ({len(note)} 字符)")
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(note, encoding="utf-8")
            print(f"+ 已写入  {material.target}")
        # 立刻登记到内存里：**同一批次**内出现重复材料时也要去重，而不是等到下次运行。
        ingested[(material.src, digest)] = target_path
        by_hash.setdefault(digest, target_path)
        written += 1

    print(f"\n新增 {written}，跳过（已存在）{skipped}，冲突 {len(drift)}")
    if drift:
        print("\n⚠️ 需要人工决定（不覆盖、不新建）：", file=sys.stderr)
        for item in drift:
            print(f"  - {item}", file=sys.stderr)
        return EXIT_DRIFT
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
