"""线视图聚合（P2）：把一个线程/仓库项目的档案区块 + 时间线组装成可渲染视图。

数据全部来自 vault 内 Markdown，零模型调用：

- 档案区块：``_vault/projects/<id>.md`` 的固定/可选二级标题下的实质内容行
  （跳过 HTML 注释占位），供前端分区展示；
- 时间线：``logs/``（work-log）、``artifacts/``（thread-doc）、``meetings/notes/``
  （meeting-note）中 frontmatter 命中该项目的笔记，按日期倒序聚合；
- 计数：主档案「跟进事项」未闭环数（``- [ ] ``）与线程 inbox 待处理数。
"""

from __future__ import annotations

import re
from pathlib import Path

from summit_workbench.repositories.vault import load_note

# 主档案中要展示的区块（按此顺序），其余二级标题忽略。
_BLOCK_ORDER = ("当前状态", "下一步", "阻塞", "跟进事项", "决策记录")
_FOLLOWUP_OPEN_RE = re.compile(r"^- \[ \] ")
_INBOX_LINE_RE = re.compile(r"^- \[ \] ")

_ARTIFACT_KIND_LABELS = {
    "summary": "阶段总结",
    "prd": "PRD",
    "background-pack": "背景包",
    "timeline": "时间线",
    "other": "文档",
}


def _section_lines(body: str) -> dict[str, list[str]]:
    """把正文按 ``## 标题`` 切成区块 → 实质内容行（去注释占位，保留原行）。"""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            current = stripped[3:].strip()
            out.setdefault(current, [])
            continue
        if current is None:
            continue
        if not stripped or stripped.startswith("<!--"):
            continue
        out[current].append(stripped)
    return out


def _note_title(note: object, path: Path) -> str:
    """笔记标题：frontmatter title → 正文首个 # 标题 → 文件名。"""
    meta = getattr(note, "meta", {})
    raw = meta.get("title")
    if isinstance(raw, str) and raw:
        return raw
    body = getattr(note, "body", "")
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _meeting_summary(body: str) -> str:
    """会议笔记取「一分钟摘要」区块首段作为时间线条目摘要。"""
    in_summary = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_summary = stripped == "## 一分钟摘要"
            continue
        if in_summary and stripped and not stripped.startswith("<!--"):
            return stripped[:90]
    return ""


def _note_meta(note: object) -> dict[str, object]:
    return getattr(note, "meta", {}) or {}


def _matches(meta: dict[str, object], project: str) -> bool:
    if meta.get("project") == project:
        return True
    projects = meta.get("projects")
    return isinstance(projects, list) and project in projects


def _collect_timeline(vault_dir: Path, project: str) -> list[dict[str, str]]:
    """聚合日志/产物/会议笔记（frontmatter 命中该项目），按日期倒序。"""
    items: list[dict[str, str]] = []
    dirs = {
        "logs": "work-log",
        "artifacts": "thread-doc",
        "meetings/notes": "meeting-note",
    }
    for sub, note_type in dirs.items():
        directory = vault_dir / sub
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            note = load_note(path)
            if note.parse_error is not None:
                continue
            meta = _note_meta(note)
            if str(meta.get("type") or "") != note_type or not _matches(meta, project):
                continue
            date = str(meta.get("date") or path.stem[:10])
            title = ""
            snippet = ""
            if note_type == "work-log":
                title = _note_title(note, path)
                raw = meta.get("summary")
                snippet = str(raw) if isinstance(raw, str) and raw else _first_raw_line(note.body)
                label = "日志"
            elif note_type == "thread-doc":
                title = _note_title(note, path)
                raw = meta.get("summary")
                snippet = str(raw) if isinstance(raw, str) and raw else ""
                label = _ARTIFACT_KIND_LABELS.get(str(meta.get("kind") or ""), "文档")
            else:
                title = _note_title(note, path)
                snippet = _meeting_summary(note.body)
                label = "会议"
            items.append(
                {
                    "date": date,
                    "kind": note_type,
                    "label": label,
                    "title": title,
                    "snippet": snippet,
                }
            )
    items.sort(key=lambda it: (it["date"], it["title"]), reverse=True)
    return items


def _first_raw_line(body: str) -> str:
    """日志原文（## 原文 区）第一段，作为无摘要时的兜底片段。"""
    in_raw = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_raw = stripped == "## 原文"
            continue
        if in_raw and stripped:
            return stripped[:90]
    return ""


def project_archive_state(vault_dir: Path, project: str) -> tuple[str | None, list[str]]:
    """从主档案取「阻塞」首条与「跟进事项」未闭环条目（供简报提醒用）。

    返回 ``(blocked, followup_open)``；档案缺失/无内容时返回 ``(None, [])``，绝不抛错
    （采集层逐源隔离，不因单个项目档案问题拖垮整份简报）。
    """
    path = vault_dir / "projects" / f"{project}.md"
    if not path.is_file():
        return None, []
    note = load_note(path)
    if note.parse_error is not None or note.meta.get("type") != "project-main":
        return None, []
    sections = _section_lines(note.body)
    blocked: str | None = None
    for line in sections.get("阻塞", []):
        text = line[2:].strip() if line.startswith("- ") else line
        if text and text != "无":
            blocked = text
            break
    followup_open: list[str] = []
    for line in sections.get("跟进事项", []):
        if _FOLLOWUP_OPEN_RE.match(line):
            followup_open.append(line[6:].strip())
    return blocked, followup_open


def build_project_view(vault_dir: Path, project: str) -> dict[str, object]:
    """组装线视图数据；项目未建档（档案缺失/无效）时抛 ValueError。"""
    path = vault_dir / "projects" / f"{project}.md"
    if not path.is_file():
        raise ValueError(f"项目未建档：{project}")
    note = load_note(path)
    if note.parse_error is not None or note.meta.get("type") != "project-main":
        raise ValueError(f"项目档案无效：{project}")

    sections = _section_lines(note.body)
    blocks: dict[str, list[str]] = {}
    for heading in _BLOCK_ORDER:
        if heading in sections:
            blocks[heading] = sections[heading]
    followup_pending = sum(
        1 for line in blocks.get("跟进事项", []) if _FOLLOWUP_OPEN_RE.match(line)
    )

    inbox_path = vault_dir / "inboxes" / f"{project}.md"
    inbox_pending = 0
    if inbox_path.is_file():
        inbox_pending = sum(
            1
            for line in inbox_path.read_text(encoding="utf-8").splitlines()
            if _INBOX_LINE_RE.match(line.strip())
        )

    status = note.meta.get("status")
    updated = note.meta.get("updated")
    title_raw = note.meta.get("title")
    title = title_raw if isinstance(title_raw, str) and title_raw else ""
    timeline = _collect_timeline(vault_dir, project)
    return {
        "name": project,
        "title": title,
        "status": status if isinstance(status, str) else "active",
        "updated": updated if isinstance(updated, str) else "",
        "blocks": blocks,
        "followup_pending": followup_pending,
        "inbox_pending": inbox_pending,
        "timeline": timeline,
    }
