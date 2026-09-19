"""日常写入路由：工作日志（`logs/`）与工作思考（`thinking/`）。

这两条是**使用者自己写**的入口（契约 §1.1 / §3 / §4.10 / §9.1，2026-09-19 起）：

- **工作日志**：关联项目**可选**（0 个 → `project: global`，1 个 → `project: <id>`，
  多个 → `projects: [...]`）；正文是使用者的原始记录 ⇒ `status: active`。落点与
  frontmatter 由 :func:`repositories.thread_notes.append_work_log` 统一负责（不另写一套）。
- **工作思考**：`long-form-thought`，三个固定区块（`## 问题缘起` / `## 思考展开` /
  `## 当前结论`）都必填，且是**会被检索**的类型 ⇒ 落盘前跑 **schema + 检索就绪** 两层校验，
  不合格拒绝落盘。落点 `thinking/<YYYYMMDD>-<slug>.md`；目录**按需创建**（不放 `.gitkeep`：
  空目录例外只给"程序写入目标"与"项目骨架"，契约 §1）。

两条都经 ``MutationRuntime.run`` 走统一事务边界（自动 commit；设 ``WB_NO_AUTO_PUSH=1``
则不自动推送）。**本模块不调用模型**：日志不再依赖 AI 摘要，思考是纯人工产物。
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

import yaml
from fastapi import FastAPI

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.retrieval_contract import validate_retrieval_readiness
from summit_workbench.domain.vault import WORKSTREAM_VOCAB, validate_note
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.thread_notes import append_work_log
from summit_workbench.repositories.vault import parse_frontmatter
from summit_workbench.webapp.api import JournalLogPayload, JournalThoughtPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.workflows.local_mutation import LocalMutationOutcome

_THINKING_DIRNAME = "thinking"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SUMMARY_LIMIT = 80
_TITLE_LIMIT = 60
# 契约 §2.1 的「本库叠加必填」——`long-form-thought` 不是机器写入页，必须全写。
_OVERLAY_REQUIRED = ("id", "title", "area", "workstream", "created", "updated", "summary")


def _resolve_projects(vault_dir: Path, names: list[str]) -> tuple[list[str], list[str]]:
    """项目名/别名 → 规范 ID；返回 ``(已解析, 解析不到的原名)``。"""
    registry = load_project_registry(vault_dir)
    resolved: list[str] = []
    unknown: list[str] = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        canonical = registry.resolve(name)
        if canonical is None:
            unknown.append(name)
        elif canonical not in resolved:
            resolved.append(canonical)
    return resolved, unknown


def _slugify(text: str, *, fallback: str) -> str:
    """标题 → 文件名 slug（小写英文 kebab-case）；纯中文标题回退到 id 短码。"""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:60].strip("-") or fallback


def _first_line(text: str, *, limit: int) -> str:
    collapsed = " ".join(text.strip().split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + "…"


def _derive_summary(conclusion: str, *, limit: int = _SUMMARY_LIMIT) -> str:
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


def _validate_thought_text(text: str) -> None:
    """落盘**前**跑 schema + 检索就绪两层校验（不合格就拒绝，不写半成品）。"""
    meta, body, error = parse_frontmatter(text)
    if error is not None:
        raise ValueError(f"frontmatter 无法解析：{error}")
    missing = [name for name in _OVERLAY_REQUIRED if not meta.get(name)]
    if missing:
        raise ValueError("缺本库叠加必填字段：" + ", ".join(missing))
    problems = [str(issue) for issue in validate_note(meta, body)]
    problems += [f"检索就绪：{issue}" for issue in validate_retrieval_readiness(meta, body)]
    if problems:
        raise ValueError("思考页不符合契约：" + "；".join(problems))


def _render_thought_note(
    *,
    title: str,
    workstream: str,
    projects: list[str],
    summary: str,
    day: str,
    problem: str,
    thinking: str,
    conclusion: str,
) -> str:
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
    if projects:
        meta["projects"] = projects
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


def register_journal_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册 `POST /api/journal/log` 与 `POST /api/journal/thought`。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/api/journal/log", response_model=None)
    def api_journal_log(payload: JournalLogPayload) -> dict[str, object]:
        """写一条日常工作日志（可关联 0..n 个项目；不绑项目 → `project: global`）。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "日志正文不能为空"}
        projects, unknown = _resolve_projects(ctx.vault_dir, payload.projects)
        if unknown:
            return {
                "ok": False,
                "message": "项目未建档：" + "、".join(unknown) + "（先在「项目」页建档）",
            }

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = append_work_log(ctx.vault_dir, projects=projects, text=text)
            return LocalMutationOutcome(path, (path,))

        try:
            result = runtime.run("journal/log", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        where = "、".join(projects) if projects else "不绑项目（project: global）"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已写入工作日志 → {where}{git_note}",
            "path": str(path),
            "projects": projects,
            **_mutation_fields(result),
        }

    @app.post("/api/journal/thought", response_model=None)
    def api_journal_thought(payload: JournalThoughtPayload) -> dict[str, object]:
        """写一篇工作思考（三段都必填；过 schema + 检索就绪才落盘）。"""
        sections = {
            "问题缘起": payload.problem.strip(),
            "思考展开": payload.thinking.strip(),
            "当前结论": payload.conclusion.strip(),
        }
        empty = [name for name, value in sections.items() if not value]
        if empty:
            return {
                "ok": False,
                "message": "缺少必填段落：" + "、".join(f"## {name}" for name in empty),
            }
        workstream = (payload.workstream or "cross").strip()
        if workstream not in WORKSTREAM_VOCAB:
            return {
                "ok": False,
                "message": f"workstream {workstream!r} 不在词表 {sorted(WORKSTREAM_VOCAB)}",
            }
        projects, unknown = _resolve_projects(ctx.vault_dir, payload.projects)
        if unknown:
            return {
                "ok": False,
                "message": "项目未建档：" + "、".join(unknown) + "（先在「项目」页建档）",
            }
        day = ctx.today()
        title = (payload.title or "").strip() or _first_line(
            payload.summary or sections["问题缘起"], limit=_TITLE_LIMIT
        )
        summary = (payload.summary or "").strip() or _derive_summary(sections["当前结论"])
        fallback = secrets.token_hex(2)
        slug = _slugify(title, fallback=fallback)
        prefix = day.replace("-", "")

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            # 目录按需创建（不放 .gitkeep）；先校验、后落盘，绝不写半成品。
            thinking_dir = ctx.vault_dir / _THINKING_DIRNAME
            path = thinking_dir / f"{prefix}-{slug}.md"
            suffix = 2
            while path.exists():
                path = thinking_dir / f"{prefix}-{slug}-{suffix}.md"
                suffix += 1
            text = _render_thought_note(
                title=title,
                workstream=workstream,
                projects=projects,
                summary=summary,
                day=day,
                problem=sections["问题缘起"],
                thinking=sections["思考展开"],
                conclusion=sections["当前结论"],
            )
            _validate_thought_text(text)
            with workspace_lock(ctx.vault_dir.parent):
                atomic_write_text(path, text, ensure_parents=True)
            return LocalMutationOutcome(path, (path,))

        try:
            result = runtime.run("journal/thought", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已写入工作思考 → {path.name}{git_note}",
            "path": str(path),
            "title": title,
            "summary": summary,
            "workstream": workstream,
            "projects": projects,
            **_mutation_fields(result),
        }


__all__ = ["register_journal_routes"]
