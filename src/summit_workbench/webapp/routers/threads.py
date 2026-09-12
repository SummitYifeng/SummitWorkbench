"""线程路由（LEGACY-APP-SPLIT-PLAN Step 11 / J）。

承载原 ``legacy_app`` 中 J 集群的 4 条线程路由：状态区块写回、活动一致性报告、
工作日志追加、产物保存。``_thread_activity_migration`` 随迁。

``register_project_read_routes``（projects 域）原本插在 ``/api/threads/state`` 与其余
线程路由之间，因此这里也用两个注册函数、在原位置分别调用，使 ``app.routes`` 顺序与
拆分前逐项一致。事务守卫 ``runtime`` 由 ``create_app`` 注入。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from summit_workbench.domain.threaddoc import ArtifactIndex, ArtifactKind, LogDigest
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.webapp.api import (
    ArtifactSavePayload,
    LogAppendPayload,
    ProjectStatePayload,
)
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.model_config import _load_model_config_for_context
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.thread_activity_migration import (
    ThreadActivityConsistencyReport,
    ThreadActivityMigration,
    ThreadActivityMigrationMode,
)


def _thread_activity_migration(ctx: WebContext) -> ThreadActivityMigration | None:
    """Create the P2-01B seam only for a frozen production workspace context."""
    if ctx.active_workspace is None or not ctx.workspace_id or not ctx.active_workspace.device_id:
        return None
    return ThreadActivityMigration.from_environment(
        ctx.vault_dir,
        workspace_id=ctx.workspace_id,
        device_id=ctx.active_workspace.device_id,
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
        migration = _thread_activity_migration(ctx)
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
        """追加推进日志（可关联多线程）；AI 消化是加分项，任何失败只存原文。"""
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

        digest: LogDigest | None = None
        enriched = False
        try:
            from summit_workbench.config.secrets import CredentialError, resolve_credential
            from summit_workbench.prompts import load_prompt
            from summit_workbench.providers.llm import LLMError
            from summit_workbench.workflows.threadnotes import digest_log

            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("log-digest")
            digest = digest_log(cfg, api_key, prompt, text, project_hints=resolved)
            enriched = True
        except (LLMError, CredentialError, FileNotFoundError, ValueError):
            digest = None

        summary = digest.summary if digest else ""
        involved = digest.involved if digest else []
        tags = digest.tags if digest else []

        archives = [ctx.vault_dir / "projects" / f"{p}.md" for p in resolved]
        activity_migration = _thread_activity_migration(ctx)

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            path = append_work_log(
                ctx.vault_dir,
                projects=resolved,
                text=text,
                summary=summary,
                involved=involved,
                tags=tags,
                next_step=digest.next_step if digest else None,
                decision=digest.decision if digest else None,
                causation_operation_id=_operation_id,
                activity_migration=activity_migration,
            )
            report = activity_migration.last_report.as_dict() if activity_migration else None
            changed_paths = (
                path,
                *archives,
                *(activity_migration.last_write_paths if activity_migration else ()),
            )
            return LocalMutationOutcome(changed_paths[0], changed_paths[1:], report)

        try:
            result = runtime.run("threads/logs", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        tail = f" · 摘要：{summary}" if summary else "（模型不可用，仅存原文）"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已追加推进日志 → {len(resolved)} 个线程 · {tail}{git_note}",
            "path": str(path),
            "summary": summary,
            "enriched": enriched,
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
        index: ArtifactIndex | None = None
        enriched = False
        try:
            from summit_workbench.config.secrets import CredentialError, resolve_credential
            from summit_workbench.prompts import load_prompt
            from summit_workbench.providers.llm import LLMError
            from summit_workbench.workflows.threadnotes import index_artifact

            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("artifact-index")
            index = index_artifact(cfg, api_key, prompt, text, title_hint=title_hint)
            enriched = True
        except (LLMError, CredentialError, FileNotFoundError, ValueError):
            index = None

        title = (index.title if index and index.title else title_hint) or ""
        summary = index.summary if index else ""
        kind = index.kind if index else ArtifactKind.OTHER
        activity_migration = _thread_activity_migration(ctx)

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
            report = activity_migration.last_report.as_dict() if activity_migration else None
            changed_paths = (
                path,
                ctx.vault_dir / "projects" / f"{project}.md",
                *(activity_migration.last_write_paths if activity_migration else ()),
            )
            return LocalMutationOutcome(changed_paths[0], changed_paths[1:], report)

        try:
            result = runtime.run("threads/artifacts", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        path = result.business_return
        tail = f" · 摘要：{summary}" if summary else "（模型不可用，仅存原文）"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已存入 {project} 档案 · {tail}{git_note}",
            "path": str(path),
            "title": title,
            "summary": summary,
            "enriched": enriched,
            **_mutation_fields(result),
        }


__all__ = ["register_thread_document_routes", "register_thread_routes"]
