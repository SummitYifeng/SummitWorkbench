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

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from summit_workbench.domain.vault import WORKSTREAM_VOCAB
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.thought_notes import ThoughtNote, write_thought_note
from summit_workbench.repositories.thread_notes import (
    JOURNAL_FIELD_LABELS,
    append_work_log,
    render_journal_body,
)
from summit_workbench.webapp.api import JournalLogPayload, JournalThoughtPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.operation_receipts import run_with_receipt
from summit_workbench.webapp.services.work_log import (
    thread_activity_migration,
    work_log_outcome,
)
from summit_workbench.workflows.local_mutation import LocalMutationOutcome


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


def register_journal_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册 `POST /api/journal/log` 与 `POST /api/journal/thought`。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/api/journal/log", response_model=None)
    def api_journal_log(
        request: Request, payload: JournalLogPayload
    ) -> dict[str, object] | JSONResponse:
        return run_with_receipt(
            ctx,
            request,
            payload.model_dump(mode="json"),
            lambda: _journal_log(payload),
        )

    def _journal_log(payload: JournalLogPayload) -> dict[str, object]:
        """写一条「日常手记」（五区块形态；可关联 0..n 个项目；不绑项目 → `project: global`）。"""
        sections = {
            "did": payload.did,
            "remaining": payload.remaining,
            "reflection": payload.reflection,
            "blockers": payload.blockers,
        }
        if not any(value.strip() for value in sections.values()):
            labels = " / ".join(JOURNAL_FIELD_LABELS.values())
            return {"ok": False, "message": f"至少填一段：{labels}"}
        projects, unknown = _resolve_projects(ctx.vault_dir, payload.projects)
        if unknown:
            return {
                "ok": False,
                "message": "项目未建档：" + "、".join(unknown) + "（先在「项目」页建档）",
            }
        try:
            body = render_journal_body(sections=sections, projects=projects)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

        # 活动迁移 seam 与「本次触碰路径」的组装与 `/api/threads/logs` 共用同一个实现
        # （`services/work_log.py`）：`append_work_log` 除日志页外还会刷新每个关联项目页的
        # `activity_at`，漏列项目页会让它们留在未提交状态（S-1(a)，2026-09-19 真实事故）。
        activity_migration = thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = append_work_log(
                ctx.vault_dir,
                projects=projects,
                text=body,
                form="daily",
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            return work_log_outcome(
                ctx.vault_dir,
                path=path,
                projects=projects,
                migration=activity_migration,
            )

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
    def api_journal_thought(
        request: Request, payload: JournalThoughtPayload
    ) -> dict[str, object] | JSONResponse:
        return run_with_receipt(
            ctx,
            request,
            payload.model_dump(mode="json"),
            lambda: _journal_thought(payload),
        )

    def _journal_thought(payload: JournalThoughtPayload) -> dict[str, object]:
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

        def mutate(_operation_id: str) -> LocalMutationOutcome[ThoughtNote]:
            # 落盘全部交给 `repositories/thread_notes.write_thought_note`（唯一实现）：
            # 目录按需创建、缺标题/摘要时派生、先校验后落盘、同名取序号不覆盖。
            note = write_thought_note(
                ctx.vault_dir,
                day=day,
                problem=sections["问题缘起"],
                thinking=sections["思考展开"],
                conclusion=sections["当前结论"],
                projects=projects,
                workstream=workstream,
                title=payload.title or "",
                summary=payload.summary or "",
            )
            return LocalMutationOutcome(note, (note.path,))

        try:
            result = runtime.run("journal/thought", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        note = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已写入工作思考 → {note.path.name}{git_note}",
            "path": str(note.path),
            "title": note.title,
            "summary": note.summary,
            "workstream": workstream,
            "projects": projects,
            **_mutation_fields(result),
        }


__all__ = ["register_journal_routes"]
