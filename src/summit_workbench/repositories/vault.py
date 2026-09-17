"""vault Markdown 读取与 frontmatter 解析。

只做「读文件、切分 frontmatter、交给 domain 校验」，规则本身在
:mod:`summit_workbench.domain.vault`。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from summit_workbench.domain.retrieval_contract import validate_retrieval_readiness
from summit_workbench.domain.vault import ValidationIssue, validate_note
from summit_workbench.repositories.ignore import is_internal_dirname

_FM_DELIM = "---"


@dataclass(frozen=True)
class ParsedNote:
    path: Path
    meta: dict[str, object]
    body: str
    parse_error: str | None = None


def parse_frontmatter(text: str) -> tuple[dict[str, object], str, str | None]:
    """从 Markdown 文本切出 YAML frontmatter 与正文。

    返回 ``(meta, body, error)``。无 frontmatter 或 YAML 非法时 ``meta`` 为空、
    ``error`` 说明原因；不抛异常，便于批量校验汇总。
    """
    if not text.startswith(_FM_DELIM):
        return {}, text, "缺少 frontmatter（文件未以 --- 开头）"

    parts = text.split("\n", 1)
    remainder = parts[1] if len(parts) > 1 else ""
    end = remainder.find("\n" + _FM_DELIM)
    if end == -1:
        return {}, text, "frontmatter 未闭合（缺少结束的 ---）"

    raw_fm = remainder[:end]
    body = remainder[end + len("\n" + _FM_DELIM) :].lstrip("\n")
    try:
        loaded = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError as exc:
        return {}, body, f"frontmatter YAML 解析失败：{exc}"
    if not isinstance(loaded, dict):
        return {}, body, "frontmatter 顶层必须是键值映射"
    return loaded, body, None


def iter_markdown_files(root: Path) -> Iterator[Path]:
    """遍历 ``root`` 下的 Markdown 文件，跳过 :func:`is_internal_dirname` 认定的目录。

    只判**目录**部分（``parts[:-1]``）：判据是「目录名」，文件名不以它判定。
    """
    for path in sorted(root.rglob("*.md")):
        if any(is_internal_dirname(part) for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def meta_date_iso(value: object) -> str | None:
    """把 frontmatter 日期值规整为 ``YYYY-MM-DD`` 字符串（或 None）。

    YAML 会把未加引号的 ``updated: 2026-09-03`` 解析成 ``date`` 对象；只有加引号
    （``'2026-09-03'``）才保留为 str。读取侧统一经本函数规整，避免「同值不同型」
    导致字段被误判为空。
    """
    if isinstance(value, datetime):  # datetime 是 date 子类，须先判
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            return None
    return None


def load_note(path: Path) -> ParsedNote:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 非 UTF-8 文件（例如被误放进 vault 的二进制）不是可读笔记：走 parse_error 通道，
        # 让每个已有的调用方一致地跳过或报错，而不是让整个扫描/请求抛 500。
        return ParsedNote(path=path, meta={}, body="", parse_error="文件不是 UTF-8 文本")
    meta, body, error = parse_frontmatter(text)
    return ParsedNote(path=path, meta=meta, body=body, parse_error=error)


def check_vault(root: Path, *, work_vault: bool = False) -> dict[Path, list[ValidationIssue]]:
    """校验 ``root`` 下全部 Markdown，返回 {文件: 问题列表}（仅含有问题的文件）。

    ``work_vault=True`` 启用工作库专属的 ``area: work`` / ``workstream`` 规则；默认关闭，
    以免通用 vault 校验影响个人库。

    两层校验：vault schema（``validate_note``）+ 工作库检索就绪契约
    （``validate_retrieval_readiness``，见 ``docs/contracts/WORK-KB-RETRIEVAL-CONTRACT.md``）。
    后者保证写进库的内容能被 SummitKnowledge 稳定切块引用；只写不检索的类型不做检索校验。
    """
    results: dict[Path, list[ValidationIssue]] = {}
    for path in iter_markdown_files(root):
        note = load_note(path)
        if note.parse_error is not None:
            results[path] = [ValidationIssue(note.parse_error)]
            continue
        issues = list(
            validate_note(
                note.meta,
                note.body,
                work_vault=work_vault,
                relative_path=path.relative_to(root),
            )
        )
        issues += [
            ValidationIssue(f"检索就绪：{issue.message}", field=issue.field)
            for issue in validate_retrieval_readiness(note.meta, note.body)
        ]
        if issues:
            results[path] = issues
    return results
