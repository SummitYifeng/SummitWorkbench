"""工作思考（``long-form-thought``）的唯一落盘实现。

``/api/journal/thought`` 与收件箱提升的 ``thought`` 目标都从这里写入，确保 schema、
检索就绪校验、文件命名和正文形态不会分叉。
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.approval import approval_record
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter

_THOUGHT_SLUG_RE = re.compile(r"[^a-z0-9]+")
_THINKING_DIRNAME = "thinking"
# 工作思考的标题/摘要缺省值（缺省从正文派生）。
_THOUGHT_TITLE_LIMIT = 60
_THOUGHT_SUMMARY_LIMIT = 80
# 契约 §2.1 的「本库叠加必填」——`long-form-thought` 不是机器写入页，必须全写。
_THOUGHT_OVERLAY_REQUIRED = ("id", "title", "area", "workstream", "created", "updated", "summary")


def _first_line(text: str, *, limit: int) -> str:
    collapsed = " ".join(text.strip().split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + "…"


def _slugify(text: str, *, fallback: str) -> str:
    """标题 → 思考页文件名 slug（小写英文 kebab-case）；纯中文标题回退到 id 短码。"""
    slug = _THOUGHT_SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:60].strip("-") or fallback


def derive_thought_summary(conclusion: str, *, limit: int = _THOUGHT_SUMMARY_LIMIT) -> str:
    """缺省摘要：取「当前结论」首句，限 ~80 字（契约要求 `summary` 必填）。"""
    text = " ".join(conclusion.strip().split())
    cut = len(text)
    for sep in ("。", "！", "？", "；", ".", "!", "?", ";"):
        index = text.find(sep)
        if index != -1:
            cut = min(cut, index + 1)
    summary = text[:cut].strip()
    if len(summary) > limit:
        summary = summary[:limit].rstrip() + "…"
    return summary or _first_line(conclusion, limit=limit)


def render_thought_note(
    *,
    title: str,
    workstream: str,
    projects: Sequence[str],
    summary: str,
    day: str,
    problem: str,
    thinking: str,
    conclusion: str,
) -> str:
    """渲染一篇工作思考的完整文本（frontmatter + 三段正文）。纯函数，便于单测。"""
    meta: dict[str, object] = {
        "id": f"{day}-{secrets.token_hex(2)}",
        "title": title,
        "area": "work",
        "workstream": workstream,
        "type": "long-form-thought",
        "status": "active",
        "created": day,
        "updated": day,
        "date": day,
        "summary": summary,
    }
    projects_list = list(dict.fromkeys(projects))
    if projects_list:
        meta["projects"] = projects_list
    else:
        # 契约 §1.1：跨项目思考不绑定任何项目；`project: global` 与 `projects` 不得并存。
        meta["project"] = "global"
    frontmatter = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    body = (
        f"# {title}\n\n"
        f"## 问题缘起\n\n{problem.strip()}\n\n"
        f"## 思考展开\n\n{thinking.strip()}\n\n"
        f"## 当前结论\n\n{conclusion.strip()}\n"
    )
    return f"---\n{frontmatter}\n---\n\n{body}"


def _validate_thought_text(text: str) -> None:
    """落盘**前**跑 schema + 检索就绪两层校验（不合格就拒绝，不写半成品）。"""
    from summit_workbench.domain.retrieval_contract import validate_retrieval_readiness
    from summit_workbench.domain.vault import validate_note

    meta, body, error = parse_frontmatter(text)
    if error is not None:
        raise ValueError(f"frontmatter 无法解析：{error}")
    missing = [name for name in _THOUGHT_OVERLAY_REQUIRED if not meta.get(name)]
    if missing:
        raise ValueError("缺本库叠加必填字段：" + ", ".join(missing))
    problems = [str(issue) for issue in validate_note(meta, body)]
    problems += [f"检索就绪：{issue}" for issue in validate_retrieval_readiness(meta, body)]
    if problems:
        raise ValueError("思考页不符合契约：" + "；".join(problems))


@dataclass(frozen=True)
class ThoughtNote:
    """一篇刚落盘的工作思考：路径 + 最终采用的标题/摘要（缺省值已派生）。"""

    path: Path
    title: str
    summary: str


def write_thought_note(
    vault_dir: Path,
    *,
    day: str,
    problem: str,
    thinking: str,
    conclusion: str,
    projects: Sequence[str] = (),
    workstream: str = "cross",
    title: str = "",
    summary: str = "",
    operation_id: str | None = None,
) -> ThoughtNote:
    """落一篇工作思考 `thinking/<YYYYMMDD>-<slug>.md`；返回路径与最终标题/摘要。

    调用方只管**内容**：缺标题取摘要/问题缘起首句，缺摘要取「当前结论」首句。
    目录按需创建（不放 `.gitkeep`）；**先校验、后落盘**，不合格绝不写半成品；
    同名时取 `-2`、`-3` 序号，绝不覆盖既有文件。
    """
    problem = problem.strip()
    thinking = thinking.strip()
    conclusion = conclusion.strip()
    resolved_title = title.strip() or _first_line(
        summary.strip() or problem, limit=_THOUGHT_TITLE_LIMIT
    )
    resolved_summary = summary.strip() or derive_thought_summary(conclusion)
    slug = _slugify(resolved_title, fallback=secrets.token_hex(2))
    prefix = day.replace("-", "")
    with workspace_lock(vault_dir.parent):
        thinking_dir = vault_dir / _THINKING_DIRNAME
        path = thinking_dir / f"{prefix}-{slug}.md"
        suffix = 2
        while path.exists():
            path = thinking_dir / f"{prefix}-{slug}-{suffix}.md"
            suffix += 1
        text = render_thought_note(
            title=resolved_title,
            workstream=workstream,
            projects=list(projects),
            summary=resolved_summary,
            day=day,
            problem=problem,
            thinking=thinking,
            conclusion=conclusion,
        )
        meta, body, error = parse_frontmatter(text)
        if error is not None:
            raise ValueError(f"frontmatter 无法解析：{error}")
        meta["approval"] = approval_record(meta, body, operation_id=operation_id or str(uuid4()))
        frontmatter = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        text = f"---\n{frontmatter}\n---\n{body}"
        _validate_thought_text(text)
        atomic_write_text(path, text, ensure_parents=True)
    return ThoughtNote(path=path, title=resolved_title, summary=resolved_summary)


__all__ = [
    "ThoughtNote",
    "derive_thought_summary",
    "render_thought_note",
    "write_thought_note",
]
