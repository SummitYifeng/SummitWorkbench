"""收件箱提升路由（契约 §10「收件箱条目的提升通路」）。

三条路由，职责严格分开：

- ``GET /api/inbox``：**只读**待处理条目（含稳定标识、`#项目` 解析、capture 机器标记、
  本地启发式的默认提升目标）。**绝不调用模型**——列表渲染不能静默花钱。
- ``POST /api/inbox/suggest``：**显式按钮**才调一次 `capture` 能力的模型，只给建议、
  不写任何东西（与 `/api/capture` 的区别：capture 会真的记进收件箱）。
- ``POST /api/inbox/promote``：把一条条目提升为正式内容，**同一个提交**里把它移出收件箱，
  且 ``changed_paths`` 列全（目标页 + inbox；第七阶段的真实事故就是漏列 → 脏工作树）。

三种目标**全部复用既有落盘实现**，本模块不新造第二套：
``project`` → `repositories/writeback.py`（`## 下一步` / `## 跟进事项`）；
``feishu-task`` → `workflows/review_apply.create_task_through_outbox`（outbox 账本 + 幂等，
库内不留可检索正文，只在 `review/archive/` 留痕）；
``thought`` → `repositories/thread_notes.write_thought_note`（与 `/api/journal/thought` 同一个）。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from summit_workbench.domain.review import CandidateKind
from summit_workbench.domain.time import business_date
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.inbox import (
    InboxEntry,
    find_entry,
    parse_inbox_entries,
    remove_inbox_entry,
    suggest_promotion,
)
from summit_workbench.repositories.project_registry import load_project_registry
from summit_workbench.repositories.review_audit import ExecutionRecord, archive_executions
from summit_workbench.repositories.thread_notes import write_thought_note
from summit_workbench.repositories.writeback import (
    append_project_followup,
    append_project_main,
)
from summit_workbench.webapp.api import InboxPromotePayload, InboxSuggestPayload
from summit_workbench.webapp.dependencies import RouteDependencies
from summit_workbench.webapp.feishu_pool import _FeishuClientPool
from summit_workbench.webapp.mutation_response import _commit_note, _mutation_fields
from summit_workbench.webapp.mutation_runtime import MutationRuntime
from summit_workbench.workflows.capture import classify_capture, extract_project_tags
from summit_workbench.workflows.local_mutation import LocalMutationOutcome
from summit_workbench.workflows.review_apply import create_task_through_outbox

_INBOX_FILENAME = "inbox.md"


def _with_text_project(entry: InboxEntry, projects: list[str]) -> InboxEntry:
    """补上「正文里的 `#项目`」这个路由信号（契约 §10）。

    `inbox.md` 的抬头**明确邀请**使用者手写 `- [ ] 想法内容 #项目名`；这种条目没有
    `wb-capture-project` 机器标记，而本地启发式的第 2 条规则看的正是 `entry.project`
    ⇒ 不补的话，手工条目会被默认判成「一篇工作思考」，与规则本身自相矛盾
    （2026-09-19 第九阶段收尾时实测，见 AGENTS.md 已知待办 8）。

    标记优先：它是写入口的判定结果，可能已经过别名归一；正文标签只在标记缺失时兜底。
    """
    if entry.project or not projects:
        return entry
    return replace(entry, project=projects[0])


def register_inbox_routes(
    dependencies: RouteDependencies,
    *,
    runtime: MutationRuntime,
    feishu_clients: _FeishuClientPool,
) -> None:
    """注册收件箱读 / AI 建议 / 提升三条路由。"""
    app: FastAPI = dependencies.app
    ctx = dependencies.context

    def _read_entries() -> tuple[list[InboxEntry], str | None]:
        """读并解析收件箱；返回 ``(条目, 错误说明)``（错误转为可见文案，不抛给读端点）。"""
        path = ctx.vault_dir / _INBOX_FILENAME
        if not path.is_file():
            return [], None
        try:
            return parse_inbox_entries(path.read_text(encoding="utf-8")), None
        except ValueError as exc:
            return [], str(exc)

    def _entry_payload(entry: InboxEntry) -> dict[str, object]:
        """一条待处理条目的读侧 payload（含本地启发式的默认目标，不调模型）。"""
        registry = load_project_registry(ctx.vault_dir)
        projects = extract_project_tags(entry.text, registry)
        suggested, reason = suggest_promotion(_with_text_project(entry, projects))
        return {
            "id": entry.id,
            "text": entry.text,
            "kind": entry.kind,
            "due": entry.due,
            "project": entry.project,
            "projects": projects,
            "candidate_id": entry.candidate_id,
            "suggested_target": suggested,
            "suggested_reason": reason,
        }

    def _remove_from_inbox(inbox: Path, entry_id: str) -> None:
        """把条目移出收件箱（不留占位行）。**在 mutation 内**重读，行区间以最新文件为准。

        在 mutation 里重读有两个作用：并发提升时不会按过期的行号删错行；条目若已消失
        就抛错（而不是"看起来很成功地什么都没删"）。
        """
        text = inbox.read_text(encoding="utf-8")
        fresh = find_entry(parse_inbox_entries(text), entry_id)
        if fresh is None:
            raise ValueError("条目已不在收件箱（可能刚被提升或手工删除）")
        atomic_write_text(inbox, remove_inbox_entry(text, fresh))

    def _commit(action: str, mutate: Any) -> tuple[Any | None, dict[str, object] | None]:
        """跑一次本地事务；失败转成可见文案（``ValueError`` 一律不 500）。"""
        try:
            return runtime.run(action, mutate), None
        except ValueError as exc:
            return None, {"ok": False, "message": f"保存失败：{exc}"}

    @app.get("/api/inbox", response_model=None)
    def api_inbox() -> dict[str, object]:
        """待处理条目列表（**纯读**：不调模型、不写盘）。"""
        entries, error = _read_entries()
        if error is not None:
            return {"ok": False, "message": error, "items": [], "pending": 0}
        return {
            "ok": True,
            "items": [_entry_payload(entry) for entry in entries],
            "pending": len(entries),
        }

    @app.post("/api/inbox/suggest", response_model=None)
    def api_inbox_suggest(payload: InboxSuggestPayload) -> dict[str, object]:
        """**显式**让 AI 判断这条适合提升成什么（一次 `capture` 能力调用；只给建议、不写盘）。

        与列表渲染彻底解耦：只有使用者点了「让 AI 判断」才会走到这里。模型不可用/输出非法时
        回落到本地启发式，并明确标注"这是本地判断、不是 AI"。
        """
        entries, error = _read_entries()
        if error is not None:
            return {"ok": False, "message": error}
        entry = find_entry(entries, payload.id)
        if entry is None:
            return {"ok": False, "message": "该条目已不在收件箱（可能已被提升或手工删除）"}
        local_target, local_reason = suggest_promotion(entry)

        from summit_workbench.config.secrets import CredentialError, resolve_credential
        from summit_workbench.prompts import load_prompt
        from summit_workbench.providers.llm import LLMError
        from summit_workbench.webapp.model_config import _load_model_config_for_context

        try:
            cfg = _load_model_config_for_context(ctx, "capture")
            api_key = resolve_credential(cfg.api_key_ref)
            prompt = load_prompt("capture-classifier")
            classified = classify_capture(
                cfg,
                api_key,
                prompt,
                entry.text,
                today=business_date(datetime.now(UTC)),
            )
        except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
            return {
                "ok": True,
                "model_used": False,
                "target": local_target,
                "reason": f"{local_reason}（AI 不可用，显示的是本地判断：{type(exc).__name__}）",
                "kind": entry.kind,
                "due": entry.due,
            }
        # AI 只提供「有没有期限 / 是不是承诺」这类事实信号；目标仍走同一条本地规则映射，
        # 于是"AI 建议"与"默认建议"永远在同一个决策面上，可比较、可解释。
        projected = InboxEntry(
            id=entry.id,
            text=entry.text,
            kind=classified.kind.value,
            due=classified.due_date or entry.due,
            project=entry.project,
            candidate_id=entry.candidate_id,
        )
        target, reason = suggest_promotion(projected)
        return {
            "ok": True,
            "model_used": True,
            "target": target,
            "reason": f"AI 建议：{reason}（建议仅供参考，最终由你确认）",
            "kind": classified.kind.value,
            "due": classified.due_date or entry.due,
        }

    @app.post("/api/inbox/promote", response_model=None)
    def api_inbox_promote(payload: InboxPromotePayload) -> dict[str, object]:
        """把一条条目提升为正式内容，并在**同一个提交**里把它移出收件箱（契约 §10）。"""
        inbox = ctx.vault_dir / _INBOX_FILENAME
        if not inbox.is_file():
            return {"ok": False, "message": "收件箱不存在或已为空"}
        try:
            entries = parse_inbox_entries(inbox.read_text(encoding="utf-8"))
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        entry = find_entry(entries, payload.id)
        if entry is None:
            return {"ok": False, "message": "该条目已不在收件箱（可能已被提升或手工删除）"}

        if payload.target == "project":
            return _promote_to_project(payload, entry, inbox)
        if payload.target == "thought":
            return _promote_to_thought(payload, entry, inbox)
        if payload.target == "feishu-task":
            return _promote_to_feishu_task(payload, entry, inbox)
        return {"ok": False, "message": f"未知提升目标：{payload.target}"}

    # ---- 三种提升：各自「先写目标、后移出收件箱」，两步在同一个 mutation 里 ----
    # 顺序有讲究：目标页写入是**按 candidate_id 幂等**的（writeback 的 wb-candidate 标记），
    # 万一后半步失败、重试时不会在目标页里留下第二份；反过来（先删条目）则会丢内容。

    def _promote_to_project(
        payload: InboxPromotePayload, entry: InboxEntry, inbox: Path
    ) -> dict[str, object]:
        """→ 项目页的 `## 下一步`（我的下一步）或 `## 跟进事项`（他人的行动项）。"""
        registry = load_project_registry(ctx.vault_dir)
        effective = _with_text_project(entry, extract_project_tags(entry.text, registry))
        raw_project = payload.project.strip() or (effective.project or "")
        if not raw_project:
            return {"ok": False, "message": "请选择要写入的项目（这条没有 #项目 标签）"}
        project = registry.resolve(raw_project)
        if project is None:
            return {"ok": False, "message": f"项目未建档：{raw_project}（先在「项目」页建档）"}
        page = ctx.vault_dir / "projects" / f"{project}.md"
        if not page.is_file():
            return {"ok": False, "message": f"项目页不存在：projects/{project}.md"}

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            if payload.block == "followup":
                target, _written = append_project_followup(
                    ctx.vault_dir, project, entry.text, entry.id
                )
            else:
                target, _written = append_project_main(
                    ctx.vault_dir,
                    project,
                    entry.text,
                    entry.id,
                    CandidateKind.ACTION_ITEM,
                )
            _remove_from_inbox(inbox, entry.id)
            return LocalMutationOutcome(target, (inbox, target))

        result, failure = _commit("inbox/promote", mutate)
        if failure is not None:
            return failure
        assert result is not None
        block_label = "跟进事项" if payload.block == "followup" else "下一步"
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "target": "project",
            "message": f"已提升为 {project} 的「{block_label}」并移出收件箱{git_note}",
            "path": str(result.business_return),
            "project": project,
            **_mutation_fields(result),
        }

    def _promote_to_thought(
        payload: InboxPromotePayload, entry: InboxEntry, inbox: Path
    ) -> dict[str, object]:
        """→ 一篇工作思考（`thinking/`，三段式；落盘复用 `write_thought_note`）。"""
        problem = payload.problem.strip() or entry.text
        thinking = payload.thinking.strip()
        conclusion = payload.conclusion.strip()
        empty = [
            name
            for name, value in (
                ("## 问题缘起", problem),
                ("## 思考展开", thinking),
                ("## 当前结论", conclusion),
            )
            if not value
        ]
        if empty:
            return {"ok": False, "message": "缺少必填段落：" + "、".join(empty)}
        registry = load_project_registry(ctx.vault_dir)
        projects = extract_project_tags(entry.text, registry)
        day = ctx.today()

        def mutate(_operation_id: str) -> LocalMutationOutcome[Any]:
            note = write_thought_note(
                ctx.vault_dir,
                day=day,
                problem=problem,
                thinking=thinking,
                conclusion=conclusion,
                projects=projects,
                summary=payload.summary,
            )
            _remove_from_inbox(inbox, entry.id)
            return LocalMutationOutcome(note, (inbox, note.path))

        result, failure = _commit("inbox/promote", mutate)
        if failure is not None:
            return failure
        assert result is not None
        note = result.business_return
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "target": "thought",
            "message": f"已提升为一篇工作思考 → {note.path.name} 并移出收件箱{git_note}",
            "path": str(note.path),
            "title": note.title,
            "summary": note.summary,
            **_mutation_fields(result),
        }

    def _promote_to_feishu_task(
        payload: InboxPromotePayload, entry: InboxEntry, inbox: Path
    ) -> dict[str, object]:
        """→ 飞书待办：走既有 outbox 路径；**库里不留可检索正文**，只在 review/archive/ 留痕。

        外部副作用（网络）必须在 `MutationRuntime.run` **之前**完成——这是
        `workflows/local_mutation.py` 的纪律：事务里只做本地写盘。
        """
        due = payload.due_date.strip() or (entry.due or "")
        if not due:
            return {"ok": False, "message": "飞书待办需要截止日期（这条没带截止，请填一个）"}
        # 飞书任务要求全天 start 与 due 同时给（AGENTS.md「飞书任务时效」）：缺开始日期时
        # 默认与截止同一天，形成一个"当天到期"的任务。
        start = payload.start_date.strip() or due
        registry = load_project_registry(ctx.vault_dir)
        target_project = _with_text_project(
            entry, extract_project_tags(entry.text, registry)
        ).project
        from summit_workbench.webapp.feishu_pool import _build_task_creator

        try:
            remote_id, operation_id = create_task_through_outbox(
                vault_dir=ctx.vault_dir,
                candidate_id=entry.id,
                description=entry.text,
                due_date=due,
                start_at=start,
                target_project=target_project,
                task_creator=_build_task_creator(ctx, feishu_clients),
            )
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

        def mutate(_operation_id: str) -> LocalMutationOutcome[Path]:
            archive = archive_executions(
                ctx.vault_dir,
                [
                    ExecutionRecord(
                        timestamp=datetime.now(UTC).isoformat(),
                        candidate_id=entry.id,
                        decision="approved",
                        ai_original=entry.text,
                        final_description=entry.text,
                        target_project=target_project,
                        route="feishu-task",
                        due_date=due,
                        destination="feishu-task",
                        result="succeeded",
                        external_id=remote_id,
                        operation_id=operation_id,
                        start_at=start,
                    )
                ],
            )
            _remove_from_inbox(inbox, entry.id)
            return LocalMutationOutcome(archive, (inbox, archive))

        result, failure = _commit("inbox/promote", mutate)
        if failure is not None:
            return failure
        assert result is not None
        git_note = _commit_note(result.commit_result)
        return {
            "ok": True,
            "target": "feishu-task",
            "message": f"已建飞书待办（截止 {due}）并移出收件箱{git_note}",
            "path": str(result.business_return),
            "external_id": remote_id,
            "operation_id": operation_id,
            **_mutation_fields(result),
        }


__all__ = ["register_inbox_routes"]
