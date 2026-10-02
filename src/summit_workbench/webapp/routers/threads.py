"""线程路由（LEGACY-APP-SPLIT-PLAN Step 11 / J）。

承载原 ``legacy_app`` 中 J 集群的 4 条线程路由：状态区块写回、活动一致性报告、
工作日志追加、产物保存。活动迁移 seam 与「本次触碰路径」的组装已抽到
:mod:`summit_workbench.webapp.services.work_log`（与 ``/api/journal/log`` 共用）。

``register_project_read_routes``（projects 域）原本插在 ``/api/threads/state`` 与其余
线程路由之间，因此这里也用两个注册函数、在原位置分别调用，使 ``app.routes`` 顺序与
拆分前逐项一致。事务守卫 ``runtime`` 由 ``create_app`` 注入。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from summit_workbench.domain.threaddoc import ArtifactKind
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.webapp.api import (
    ArtifactSavePayload,
    LogAppendPayload,
    ProjectStatePayload,
)
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.webapp.services.work_log import (
    thread_activity_migration,
    work_log_outcome,
)
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.thread_activity_migration import (
    ThreadActivityConsistencyReport,
    ThreadActivityMigrationMode,
)


def register_thread_routes(dependencies: RouteDependencies, *, runtime: MutationRuntime) -> None:
    """注册线程状态路由（原 ``legacy_app`` 528–561，在 projects 只读 seam 之前）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.post("/api/threads/state")
    def api_set_project_state(payload: ProjectStatePayload) -> dict[str, object]:
        """把主档案「当前状态」区块替换为一段文本（产物摘要 → 状态草案，显式确认后写回）。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "状态内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(payload.project.strip())
        if project is None:
            return {"ok": False, "message": f"项目未建档：{payload.project.strip()}"}

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            from summit_workbench.repositories.note_status import update_note_status
            from summit_workbench.repositories.vault import load_note as _load_note
            from summit_workbench.repositories.writeback import set_project_status

            path, _written = set_project_status(ctx.vault_dir, project, text)
            from summit_workbench.repositories.approval import approve_markdown

            approve_markdown(path, operation_id=_operation_id)
            note = _load_note(path)
            status = note.meta.get("status")
            if isinstance(status, str):
                update_note_status(ctx.vault_dir, path, status, extra={"updated": ctx.today()})
            return LocalMutationOutcome(path, (path,))

        try:
            result = runtime.run("threads/state", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"更新失败：{exc}"}
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已更新 {project} 当前状态{git_note}",
            "project": project,
            **_mutation_fields(result),
        }


def register_thread_document_routes(
    dependencies: RouteDependencies, *, runtime: MutationRuntime
) -> None:
    """注册线程日志/产物/活动一致性路由（原 ``legacy_app`` 569–726，在 projects seam 之后）。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    @app.get("/api/threads/activity-consistency")
    def api_thread_activity_consistency() -> dict[str, object]:
        """Return the deterministic old/new report for the P2-01B event slice."""
        migration = thread_activity_migration(ctx)
        if migration is None:
            report = ThreadActivityConsistencyReport(
                mode=ThreadActivityMigrationMode.LEGACY,
                status="disabled",
            )
        else:
            report = migration.inspect()
        return {"ok": report.ok, "thread_activity_consistency": report.as_dict()}

    @app.post("/api/threads/logs")
    def api_append_log(payload: LogAppendPayload) -> dict[str, object]:
        """追加推进日志（可关联多线程）；只保存原文，不隐式调用模型。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "日志内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        resolved: list[str] = []
        for name in payload.projects:
            cid = registry.resolve(name) or name
            if cid and cid in registry.canonical and cid not in resolved:
                resolved.append(cid)
        if not resolved:
            return {"ok": False, "message": "没有可关联的项目/线程（先在「项目」页建档）"}

        summary = ""

        activity_migration = thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = append_work_log(
                ctx.vault_dir,
                projects=resolved,
                text=text,
                summary=summary,
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            return work_log_outcome(
                ctx.vault_dir,
                path=path,
                projects=resolved,
                migration=activity_migration,
            )

        try:
            result = runtime.run("threads/logs", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        return {
            "ok": True,
            "message": f"已追加推进日志 → {len(resolved)} 个线程",
            "path": str(path),
            "summary": summary,
            **_mutation_fields(result),
        }

    @app.post("/api/threads/artifacts")
    def api_save_artifact(payload: ArtifactSavePayload) -> dict[str, object]:
        """把 AI 产物（阶段总结/PRD/背景包等）存入线程档案并生成索引。"""
        text = payload.text.strip()
        if not text:
            return {"ok": False, "message": "产物内容为空"}
        registry = load_project_registry(ctx.vault_dir)
        project = registry.resolve(payload.project.strip())
        if project is None:
            return {
                "ok": False,
                "message": f"项目未建档：{payload.project.strip()}（先在「项目」页建档再存产物）",
            }
        title_hint = (payload.title or "").strip()
        title = title_hint
        summary = ""
        kind = ArtifactKind.OTHER
        activity_migration = thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = save_thread_artifact(
                ctx.vault_dir,
                project=project,
                text=text,
                title=title,
                summary=summary,
                kind=kind,
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            return work_log_outcome(
                ctx.vault_dir,
                path=path,
                projects=[project],
                migration=activity_migration,
            )

        try:
            result = runtime.run("threads/artifacts", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        return {
            "ok": True,
            "message": f"已存入 {project} 档案（保留全文）",
            "path": str(path),
            "title": title,
            "summary": summary,
            **_mutation_fields(result),
        }


__all__ = ["register_thread_document_routes", "register_thread_routes"]
