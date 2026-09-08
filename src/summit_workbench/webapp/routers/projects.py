"""项目相关 Web 路由。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from summit_workbench.repositories.project_registry import (
    archive_project,
    create_project_note,
    ensure_project_active,
    load_project_registry,
)
from summit_workbench.repositories.project_scan import is_internal_dirname
from summit_workbench.repositories.project_view import build_project_view
from summit_workbench.webapp.api import ProjectCreatePayload, ProjectPayload, ProjectRenamePayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, LocalMutationResult

ROUTE_PREFIXES = ("/api/projects",)

ProjectMutationRunner = Callable[
    [str, Callable[[str], LocalMutationOutcome[Path]]],
    LocalMutationResult[Path],
]


def _project_target(dependencies: RouteDependencies, name: str) -> tuple[bool, str]:
    """校验加入或归档工作台的目标：Work 文件夹或已建档的知识线程。"""
    context = dependencies.context
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return False, f"非法项目名：{name}"
    if is_internal_dirname(name):
        return False, f"{name} 是系统内部目录，不能作为项目操作"
    folder = context.work_root / name
    if folder.is_dir():
        return True, ""
    registry = load_project_registry(context.vault_dir)
    if name in registry.canonical:
        return True, ""
    return False, f"work_root 下没有该项目文件夹，vault 中也没有 {name} 的档案"


def register_project_read_routes(dependencies: RouteDependencies) -> None:
    """注册项目只读路由。"""
    app = dependencies.app
    context = dependencies.context

    @app.get("/api/projects/view")
    def api_project_view(name: str) -> dict[str, object]:
        """线视图：某项目/线程的档案区块 + 时间线（logs/artifacts/meetings 聚合）。"""
        registry = load_project_registry(context.vault_dir)
        project = registry.resolve(name)
        if project is None:
            return {"ok": False, "message": f"项目未建档：{name}"}
        try:
            view = build_project_view(context.vault_dir, project)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **view}


def register_project_write_routes(
    dependencies: RouteDependencies,
    *,
    run_mutation: ProjectMutationRunner,
) -> None:
    """注册项目写路由，并通过调用方注入的 runner 复用本地事务边界。"""
    app = dependencies.app
    context = dependencies.context

    @app.post("/api/projects/rename")
    def api_project_rename(payload: ProjectRenamePayload) -> dict[str, object]:
        """设置项目或线程的显示名。"""
        name = payload.name.strip()
        title = payload.title.strip()
        if not title:
            return {"ok": False, "message": "显示名不能为空"}
        registry = load_project_registry(context.vault_dir)
        project = registry.resolve(name)
        if project is None:
            return {"ok": False, "message": f"项目未建档：{name}"}
        path = context.vault_dir / "projects" / f"{project}.md"

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            from summit_workbench.repositories.note_status import update_note_status
            from summit_workbench.repositories.vault import load_note as _load_note

            note = _load_note(path)
            status = note.meta.get("status")
            if not isinstance(status, str):
                raise ValueError(f"项目档案无效：{project}")
            update_note_status(
                context.vault_dir, path, status, extra={"title": title, "updated": context.today()}
            )
            return LocalMutationOutcome(path, (path,))

        try:
            result = run_mutation("projects/rename", mutate)
        except ValueError as exc:
            return {"ok": False, "message": f"改名失败：{exc}"}
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"{project} 显示名已设为「{title}」{git_note}",
            **_mutation_fields(result),
        }

    @app.post("/api/projects/activate")
    def api_project_activate(payload: ProjectPayload) -> dict[str, object]:
        """把项目加入工作台（幂等）：无档案则建档；archived 则恢复为 active。"""
        name = payload.name.strip()
        ok, message = _project_target(dependencies, name)
        if not ok:
            return {"ok": False, "message": message}
        try:
            result = run_mutation(
                "projects/activate",
                lambda _operation_id: LocalMutationOutcome(
                    (path := ensure_project_active(context.vault_dir, name)), (path,)
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"加入工作台失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已加入工作台：{name}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }

    @app.post("/api/projects/archive")
    def api_project_archive(payload: ProjectPayload) -> dict[str, object]:
        """把项目归档（幂等）：置 status: archived，不在首页显示；可随时恢复。"""
        name = payload.name.strip()
        ok, message = _project_target(dependencies, name)
        if not ok:
            return {"ok": False, "message": message}
        try:
            result = run_mutation(
                "projects/archive",
                lambda _operation_id: LocalMutationOutcome(
                    (path := archive_project(context.vault_dir, name)), (path,)
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"归档失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已归档：{name}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }

    @app.post("/api/projects/create")
    def api_project_create(payload: ProjectCreatePayload) -> dict[str, object]:
        """新建知识线程项目：在 vault 建档。"""
        project_id = payload.project_id.strip()
        if not project_id:
            return {"ok": False, "message": "请输入项目 ID"}
        if is_internal_dirname(project_id):
            return {"ok": False, "message": "项目 ID 不能以下划线开头（保留给系统内部目录）"}
        if (context.work_root / project_id).is_dir():
            return {
                "ok": False,
                "message": f"Work 下已有同名文件夹 {project_id}，请用「加入工作台」建档",
            }
        aliases = [alias.strip() for alias in payload.aliases if alias.strip()]
        try:
            result = run_mutation(
                "projects/create",
                lambda _operation_id: LocalMutationOutcome(
                    (
                        path := create_project_note(
                            context.vault_dir, project_id, aliases=aliases or None
                        )
                    ),
                    (path,),
                ),
            )
        except (ValueError, FileExistsError) as exc:
            return {"ok": False, "message": f"新建失败：{exc}"}
        path = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "message": f"已建档知识线程：{project_id}{git_note}",
            "path": str(path),
            **_mutation_fields(result),
        }


__all__ = [
    "ProjectMutationRunner",
    "ROUTE_PREFIXES",
    "register_project_read_routes",
    "register_project_write_routes",
]
