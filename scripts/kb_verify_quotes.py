#!/usr/bin/env python3
"""校验知识库里的**逐字引用**是否真的能在其声明的来源里找到。

为什么需要它：原子笔记最容易出的问题是「看起来合理、但原文里没有」的编造。
本脚本把这件事变成**可机械判定**的检查：笔记 `## 来源` / `## 证据` 区里以 `>` 开头的引用行，
必须能在其 `source.ref` 指向的来源笔记正文里逐字找到（忽略空白与 Markdown 强调符号）。

同时校验会议笔记 `## 证据索引` 里写出的 `<说话人> <mm:ss>` 时间点是否真的出现在所链逐字稿里，
避免「引用了不存在的发言位置」。

退出码：0 = 全部通过；1 = 存在无法核对的引用；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SKIP_DIRS = {".git", ".obsidian", "_signals", "templates"}
QUOTE_RE = re.compile(r"^\s*(?:>\s*)+(.+?)\s*$")
STAMP_RE = re.compile(r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9 ]{0,20}?)\s+(\d{1,2}:\d{2})")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


@dataclass(frozen=True)
class Finding:
    note: str
    line: int
    quote: str
    reason: str

    def __str__(self) -> str:
        return f"{self.note}:{self.line}  [{self.reason}]  {self.quote[:70]}"


def normalise(text: str) -> str:
    """去掉 Markdown 强调符号与全部空白，便于逐字比对。"""
    text = text.replace("**", "").replace("`", "").replace("*", "")
    return re.sub(r"\s+", "", text)


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    rest = text.split("\n", 1)[1]
    end = rest.find("\n---")
    if end == -1:
        return {}, text
    raw = rest[:end]
    body = rest[end + len("\n---") :]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, body
    return (meta if isinstance(meta, dict) else {}), body


def iter_notes(vault: Path) -> list[Path]:
    out = []
    for path in sorted(vault.rglob("*.md")):
        if any(p in SKIP_DIRS for p in path.relative_to(vault).parts):
            continue
        out.append(path)
    return out


def section_quotes(body: str) -> list[tuple[int, str]]:
    """取出 `## 来源` / `## 证据` 区里的引用行（行号, 文本）。"""
    lines = body.splitlines()
    out: list[tuple[int, str]] = []
    active = False
    for index, line in enumerate(lines, 1):
        if line.startswith("## "):
            active = line[3:].strip() in {"来源", "证据"}
            continue
        if not active:
            continue
        match = QUOTE_RE.match(line)
        if match:
            quote = match.group(1).strip()
            # 纯装饰性的引用（分隔线、空）跳过
            if quote and not quote.startswith("---") and quote not in {"```"}:
                out.append((index, quote))
    return out


def is_citation_only(quote: str) -> bool:
    """形如「（原文 § 二、…）」或「（来自 XXX）」的出处说明不是逐字引用。"""
    return quote.startswith("（") or quote.startswith("(")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验知识库逐字引用")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument(
        "--materials-root",
        type=Path,
        default=None,
        help="原始材料根目录。给了它就额外校验 source/逐字稿是否**逐字保留**了原件。",
    )
    args = parser.parse_args()
    vault: Path = args.vault.expanduser().resolve()
    if not vault.is_dir():
        print(f"vault 不存在：{vault}", file=sys.stderr)
        return 2

    bodies: dict[str, str] = {}
    texts: dict[str, str] = {}
    metas: dict[str, dict[str, object]] = {}
    for path in iter_notes(vault):
        rel = path.relative_to(vault).as_posix()
        text = path.read_text(encoding="utf-8")
        meta, body = split_frontmatter(text)
        texts[rel] = text
        bodies[rel] = body
        metas[rel] = meta
    by_slug = {Path(rel).stem: rel for rel in texts}

    findings: list[Finding] = []
    checked = 0
    for rel, body in bodies.items():
        meta = metas[rel]
        source = meta.get("source")
        ref = str(source.get("ref") or "") if isinstance(source, dict) else ""
        target_rel = ref if ref in bodies else by_slug.get(Path(ref).stem, "")
        if target_rel and target_rel != rel:
            haystack = normalise(bodies[target_rel])
            for line, quote in section_quotes(body):
                if is_citation_only(quote) or quote.startswith(("[", "#")):
                    continue
                checked += 1
                if normalise(quote) not in haystack:
                    findings.append(Finding(rel, line, quote, "来源中找不到该逐字引用"))

        # 会议笔记：证据索引里写出的 <说话人> <mm:ss> 必须真的在逐字稿里
        if meta.get("type") == "meeting-note":
            evidence = body.split("## 证据索引", 1)[-1]
            links: list[tuple[int, str]] = []
            for number, text_line in enumerate(evidence.splitlines(), 1):
                found = WIKILINK_RE.search(text_line)
                if found:
                    links.append((number, found.group(1)))
            for line, link in links:
                transcript_rel = by_slug.get(link.strip())
                if transcript_rel is None:
                    findings.append(Finding(rel, line, link, "证据索引指向的笔记不存在"))
                    continue
                # 只把**逐字稿**当作时间戳的比对对象：证据索引里也会链到项目主页等，
                # 拿那些笔记去查说话人时间点只会产生假失败。
                if metas[transcript_rel].get("type") != "meeting-transcript":
                    continue
                haystack = normalise(texts[transcript_rel])
                for stamp in STAMP_RE.finditer(evidence):
                    checked += 1
                    speaker, clock = stamp.group(1).strip(), stamp.group(2)
                    if normalise(speaker) + clock not in haystack:
                        findings.append(
                            Finding(
                                rel,
                                line,
                                f"{speaker} {clock}",
                                f"逐字稿 {transcript_rel} 中无此时间点",
                            )
                        )

    if args.materials_root is not None:
        checked, findings = _check_verbatim(
            bodies, metas, args.materials_root.expanduser(), checked, findings
        )

    print(f"检查了 {checked} 条逐字引用 / 时间点 / 原件比对，问题 {len(findings)} 条")
    for finding in findings:
        print(f"  ✗ {finding}")
    return 1 if findings else 0


def _strip_headings(text: str) -> list[str]:
    """去掉 ATX 标题标记并丢弃空行——用于「只允许标题层级不同」的逐字比对。"""
    out = []
    for line in text.strip().splitlines():
        value = re.sub(r"^#+\s*", "", line).rstrip()
        if value:
            out.append(value)
    return out


_SEPARATOR_RE = re.compile(r"-{3,}")
_ASSOCIATION_HEADING = "关联"


def _is_allowed_scaffold_tail(tail: list[str]) -> bool:
    """原件之后**允许**残留的内容：只有约定为页尾区块的 `## 关联`。

    ``conventions`` §4.3 规定 `source` 页在逐字原文之后写一个 `## 关联` 区块，区块内部
    可以自由写双链——它本来就在原件之外。所以「原件已经结束」的判据不是「笔记到此为止」，
    而是「原件之后除了这个页尾区块以外没有别的东西」。

    只看跳过分隔线（`---`）之后**第一个**真正的行：它必须是 `关联`
    （``_strip_headings`` 已把 `## 关联` 变成裸 `关联`）。
    """
    for line in tail:
        if _SEPARATOR_RE.fullmatch(line.strip()):
            continue
        return line.strip() == _ASSOCIATION_HEADING
    return True


def _contains_original(have: list[str], want: list[str]) -> bool:
    """``want``（原件）是否为 ``have``（笔记正文）中一段**连续且逐字**的片段，
    并且它之后只允许约定的页尾脚手架（见 :func:`_is_allowed_scaffold_tail`）。

    这是「原件不可变」的机械证明：归档时任何顺手改写、裁掉段落、往中间插一句话，
    或者**在原件后面另加内容**，都会在这里暴露。逐位置扫描而不是只认第一处命中——
    笔记自己的标题偶尔会与原件首行同名，那种位置不满足「其后是页尾区块」，应当跳过。
    """
    if not want:
        return True
    for index in range(len(have) - len(want) + 1):
        if have[index : index + len(want)] != want:
            continue
        if _is_allowed_scaffold_tail(have[index + len(want) :]):
            return True
    return False


def _check_verbatim(
    bodies: dict[str, str],
    metas: dict[str, dict[str, object]],
    materials_root: Path,
    checked: int,
    findings: list[Finding],
) -> tuple[int, list[Finding]]:
    """source / 逐字稿笔记必须**逐字包含**其原始材料（只允许 ATX 标题层级不同）。

    这是「原件不可变」的机械证明：归档时任何顺手改写、裁掉段落、往中间插一句话，或者
    在原件后面另加内容，都会在这里暴露。做法是在笔记正文里找原件的**连续行序列**，因此
    不依赖笔记自身的分节结构；原件之后只放行约定为页尾区块的 `## 关联`（conventions §4.3）。
    """
    for rel, body in bodies.items():
        meta = metas[rel]
        if meta.get("type") not in {"source", "meeting-transcript"}:
            continue
        source = meta.get("source")
        ref = str(source.get("ref") or "") if isinstance(source, dict) else ""
        ref = ref or str(meta.get("transcript_ref") or "")
        if not ref:
            continue
        original = materials_root / ref
        if not original.is_file():
            findings.append(Finding(rel, 1, ref, "原件不存在，无法核对逐字保留"))
            continue
        checked += 1
        # 原件必须逐字、连续地出现在笔记正文里，且其后只允许约定的页尾 `## 关联` 区块：
        # 既证明原文逐字在库，也证明没有在原件后面另加内容。
        if not _contains_original(
            _strip_headings(body),
            _strip_headings(original.read_text(encoding="utf-8")),
        ):
            findings.append(Finding(rel, 1, ref, "正文未逐字包含原件（被改写、截断或另加了内容）"))
    return checked, findings


if __name__ == "__main__":
    raise SystemExit(main())
