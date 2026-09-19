"""线程知识笔记的落盘：推进日志（work-log）与 AI 产物（thread-doc）。

两条写入都遵守 vault schema（统一 frontmatter + 固定区块），落盘后即时 self-check，
保证任何写进 vault 的内容都能通过 ``wb vault check``：

- 推进日志 ``_vault/logs/YYYY-MM-DD-<seq>.md``：``type: work-log``，可关联 **0..n** 个
  项目（绑定 0 个写 ``project: global``、1 个写 ``project: <id>``、多个写 ``projects: [...]``）；
  正文是使用者的原始记录 ⇒ ``status: active``（2026-09-19 起；纯机器生成、无人工正文才用
  ``generated``，契约 §3/§4.10/§9.1）。模型摘要只是附加，不可用时原文照存。
- AI 产物 ``_vault/artifacts/<project>-<seq>.md``：``type: thread-doc``，单项目
  （``project: <id>``），frontmatter 带 ``title / summary / kind`` 供检索命中。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.threaddoc import ArtifactKind, LogTag
from summit_workbench.domain.time import business_date
from summit_workbench.domain.vault import iter_headings
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import load_note
from summit_workbench.workflows.knowledge_normalization import (
    format_normalization_error,
    normalize_generated_body,
)

if TYPE_CHECKING:
    from summit_workbench.workflows.thread_activity_migration import ThreadActivityMigration

_SLUG_RE = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff_-]+")
_LOGS_DIRNAME = "logs"
_ARTIFACTS_DIRNAME = "artifacts"

# ── 「日常手记」形态（契约 §4.10）────────────────────────────────────────────
# App「写工作日志」按使用者的话术采集四段，落盘换成标准区块名；
# `## 关联` 恒在（无关联项目时写 `- （无）`）。
# 落盘顺序 = 契约 §4.10 / 库内模板 `templates/work-log.template.md` 的五区块顺序。
JOURNAL_FIELD_HEADINGS: tuple[tuple[str, str], ...] = (
    ("did", "## 今天 / 本周做了什么"),
    ("reflection", "## 进展与变化"),
    ("blockers", "## 卡点与需要谁"),
    ("remaining", "## 下一步"),
)
JOURNAL_RELATED_HEADING = "## 关联"
# 单个 `##` 块（含标题行）上限：超过会被 SK 切成**共享同一锚点**的子块，`路径#区块` 不再唯一
# （契约 §9.1「结论块瘦身」/ §4.10）。
JOURNAL_MAX_BLOCK_CHARS = 1500
# 表单标签（使用者的原话）——报错与文档都用它，避免两处漂移。
JOURNAL_FIELD_LABELS: dict[str, str] = {
    "did": "今天做了什么",
    "remaining": "还剩什么没做",
    "reflection": "今天的一点感悟",
    "blockers": "卡点与需要谁",
}


def render_journal_body(*, sections: Mapping[str, str], projects: Sequence[str] = ()) -> str:
    """把 App 表单四段渲染成「日常手记」五区块正文（纯函数，便于单测）。

    - 某一段为空 ⇒ **不生成该区块**（不写"（无）"占位，有几段写几段）；
    - `## 关联` **恒在**：无关联项目时写 `- （无）`，保持五区块齐全；
    - 任一段超过 :data:`JOURNAL_MAX_BLOCK_CHARS` ⇒ 抛 :class:`ValueError`
      （超长块会被切成共享同一锚点的子块，引用不再唯一）。
    """
    parts: list[str] = []
    for field, heading in JOURNAL_FIELD_HEADINGS:
        value = (sections.get(field) or "").strip()
        if not value:
            continue
        if len(heading) + 2 + len(value) > JOURNAL_MAX_BLOCK_CHARS:
            label = JOURNAL_FIELD_LABELS[field]
            raise ValueError(
                f"「{label}」超过 {JOURNAL_MAX_BLOCK_CHARS} 字符（{len(value)} 字）："
                "超长区块会被切成共享同一锚点的子块、引用不再唯一；"
                "请精简，或改用「写工作思考」/分析笔记"
            )
        parts.append(f"{heading}\n\n{value}")
    links = "\n".join(f"- [[projects/{project}]]" for project in dict.fromkeys(projects))
    parts.append(f"{JOURNAL_RELATED_HEADING}\n\n{links or '- （无）'}")
    return "\n\n".join(parts) + "\n"


def _day(now: datetime | None) -> str:
    return business_date(now or datetime.now(UTC))


def _next_seq(directory: Path, prefix: str) -> int:
    """目录里同名前缀文件的下一个序号（1 起，缺目录时从 1 开始）。"""
    if not directory.is_dir():
        return 1
    count = sum(1 for p in directory.glob(f"{prefix}-*.md") if p.is_file())
    return count + 1


def _write_note(path: Path, meta: dict[str, object], body: str) -> Path:
    """frontmatter 用 YAML 安全序列化（允许中文），原子写盘。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    atomic_write_text(path, f"---\n{fm}\n---\n\n{body}")
    return path


def _check(path: Path) -> None:
    """写盘后自检：schema + 检索就绪双重校验失败即抛错（不落坏笔记）。

    检索就绪校验（``validate_retrieval_readiness``）保证自动产物可被 SummitKnowledge
    稳定切块引用；两条校验都在**落盘之后立即**执行，失败即抛错并把问题写清。
    """
    from summit_workbench.domain.retrieval_contract import validate_retrieval_readiness
    from summit_workbench.domain.vault import validate_note

    note = load_note(path)
    if note.parse_error is not None:
        raise ValueError(f"笔记 frontmatter 无法解析：{path}：{note.parse_error}")
    problems = [str(issue) for issue in validate_note(note.meta, note.body)]
    problems += [
        f"检索就绪：{issue}" for issue in validate_retrieval_readiness(note.meta, note.body)
    ]
    if problems:
        raise ValueError(f"笔记不符合 vault schema：{path}：" + "; ".join(problems))


def _clean_text(text: str) -> str:
    """去掉首尾空白但保留正文换行（不要像单行捕捉那样折叠）。"""
    return text.strip()


def _touch_projects_activity(vault_dir: Path, projects: Iterable[str], day: str) -> None:
    """日志/产物入库后，刷新关联项目档案 frontmatter 的 ``activity_at``（活动痕迹）。

    语义拆分（P1）：``updated`` = 实质更新，只在建档/激活/归档/改名与用户显式确认的状态
    写回时刷新；机器高频自刷新的日志/产物入库**不再动 updated**（否则 AI 收尾会让停滞点名
    失明），只写 ``activity_at`` 供首页「最近活跃」展示（档案正文不动，保留原子写）。
    """
    from summit_workbench.repositories.note_status import update_note_status
    from summit_workbench.repositories.vault import load_note as _load

    for project in projects:
        path = vault_dir / "projects" / f"{project}.md"
        if not path.is_file():
            continue
        note = _load(path)
        if note.parse_error is not None:
            continue
        status = note.meta.get("status")
        if isinstance(status, str):
            update_note_status(vault_dir, path, status, extra={"activity_at": day})


def _has_top_level_h2(text: str) -> bool:
    """正文里是否已有可引用的 ``##`` 区块（围栏代码里的不算）。"""
    return any(level == 2 and heading for level, heading in iter_headings(text))


def append_work_log(
    vault_dir: Path,
    *,
    projects: Sequence[str] = (),
    text: str,
    summary: str = "",
    involved: Iterable[str] = (),
    tags: Iterable[LogTag] = (),
    next_step: str | None = None,
    decision: str | None = None,
    now: datetime | None = None,
    causation_operation_id: str | None = None,
    activity_migration: ThreadActivityMigration | None = None,
) -> Path:
    """落一条推进日志（可关联 0..n 个线程）。``text`` 必填；``summary`` 空 = 模型未消化，原文照存。

    空项目 = 日常日志（不属于任何项目）：写 ``project: global``，且**不**刷新任何项目档案的
    ``activity_at``（2026-09-19，契约 §1.1/§3）。正文若已自带 ``##`` 区块（例如照库内模板写的
    五区块手写日志）则原样保留；否则包一层 ``## 原文``（机器写入形态）——契约 §4.10 的两套区块
    并存，这里按"调用方给了什么就用什么"选形态。
    """
    body_text = _clean_text(text)
    if not body_text:
        raise ValueError("日志正文不能为空")
    occurred_at = now or datetime.now(UTC)
    day = _day(occurred_at)
    projects_list = list(dict.fromkeys(projects))
    heading = f"推进日志 {day}（{projects_list[0]} 等）" if projects_list else f"推进日志 {day}"
    meta: dict[str, object] = {
        "date": day,
        # `area: work` 是工作库的既有约定（16 个模板全都带它）。SK 侧的综合类问题按 `area`
        # 过滤「笔记总览」，缺这一行会让日志从总览清单里静默消失——写入方必须补上。
        "area": "work",
        # `title` 同样要写：库规范 §5 要求中文标题进 frontmatter，而 SK 在缺 title 时
        # 会回退成文件名（`2026-09-14-001`），总览里就只剩日期、语义全丢。
        "title": heading,
        "type": "work-log",
        # 日志正文是**使用者自己的原始记录** ⇒ `active`（契约 §3/§9.1，2026-09-19 起）。
        # 此前恒为 `generated`（低权威），把使用者手写的日常日志也一并降了权威；只有
        # **完全由机器生成、无人工正文**的日志才用 `generated`。
        "status": "active",
    }
    if projects_list:
        meta["projects"] = projects_list
    else:
        # 不绑项目：契约 §1.1/§3 规定写 `project: global`（scope=free 允许；`project`
        # 与 `projects` 不得并存）。
        meta["project"] = "global"
    if summary:
        meta["summary"] = summary
    involved_list = list(dict.fromkeys(i.strip() for i in involved if i.strip()))
    if involved_list:
        meta["involved"] = involved_list
    tag_values = list(dict.fromkeys(t.value for t in tags))
    if tag_values:
        meta["tags"] = tag_values
    if next_step:
        meta["next_step"] = next_step
    if decision:
        meta["decision"] = decision

    # 机器写入形态保留 ``## 原文``（+ 摘要时 ``## AI 摘要``）：project_view 的兜底片段
    # 按 ``## 原文`` 读取日志首段、并发落盘测试也以该区块为契约。若调用方给的正文**已经**
    # 带 ``##`` 区块（照模板写的手写日志），就原样用它，不再套一层空的 ``## 原文``。
    if _has_top_level_h2(body_text):
        raw_body = f"# {heading}\n\n{body_text}\n"
    else:
        raw_body = f"# {heading}\n\n## 原文\n\n{body_text}\n"
    if summary:
        raw_body += f"\n## AI 摘要\n\n{summary}\n"
    normalized = normalize_generated_body(
        note_type="work-log",
        title=heading,
        text=raw_body,
        project_links=projects_list,
    )
    if normalized.issues:
        raise ValueError("无法规范化日志正文：" + format_normalization_error(normalized.issues))
    body = normalized.body
    # 序号分配 + 落盘 + 关联档案 touch 整体持锁（P0-4）：两个并发写入不会算出同一
    # 序号互相静默覆盖；写前若目标已被占（如人工预占名）则重取序号，绝不覆盖既有文件。
    with workspace_lock(vault_dir.parent):
        logs_dir = vault_dir / _LOGS_DIRNAME
        seq = _next_seq(logs_dir, day)
        path = logs_dir / f"{day}-{seq:03d}.md"
        while path.exists():
            seq += 1
            path = logs_dir / f"{day}-{seq:03d}.md"
        _write_note(path, meta, body)
        _check(path)
        # 无项目时是空循环（不动任何档案）；迁移投影也只在有项目时才记录。
        _touch_projects_activity(vault_dir, projects_list, day)
        if activity_migration is not None and projects_list:
            activity_migration.record_work_log(
                path,
                projects=projects_list,
                activity_date=day,
                causation_operation_id=causation_operation_id or str(uuid4()),
                occurred_at=occurred_at,
            )
    return path


def save_thread_artifact(
    vault_dir: Path,
    *,
    project: str,
    text: str,
    title: str = "",
    summary: str = "",
    kind: ArtifactKind = ArtifactKind.OTHER,
    now: datetime | None = None,
    causation_operation_id: str | None = None,
    activity_migration: ThreadActivityMigration | None = None,
) -> Path:
    """把一段 AI 产物（阶段总结/PRD/背景包/timeline）存进线程档案目录。"""
    body_text = _clean_text(text)
    if not body_text:
        raise ValueError("产物正文不能为空")
    occurred_at = now or datetime.now(UTC)
    day = _day(occurred_at)

    meta: dict[str, object] = {
        "date": day,
        # 同 append_work_log：`area: work` 保证产物能进 SK 的笔记总览清单。
        "area": "work",
        "type": "thread-doc",
        "status": "generated" if summary else "draft",
        "project": project,
        "kind": kind.value,
    }
    if summary:
        meta["summary"] = summary

    # 序号分配 + 落盘 + 关联档案 touch 整体持锁（P0-4，同 append_work_log）。
    with workspace_lock(vault_dir.parent):
        artifacts_dir = vault_dir / _ARTIFACTS_DIRNAME
        seq = _next_seq(artifacts_dir, project)
        path = artifacts_dir / f"{project}-{seq:03d}.md"
        while path.exists():
            seq += 1
            path = artifacts_dir / f"{project}-{seq:03d}.md"
        heading = title or f"{project} 产物 {seq}"
        # 标题始终落 frontmatter：库规范 §5 要求中文标题进 `title`，而 SK 缺 title 时
        # 回退成文件名（`<project>-001`），总览里会丢掉语义。
        meta["title"] = heading
        # 规范化在写盘前完成：失败即抛错，目标文件不会出现（不落半成品）。
        normalized = normalize_generated_body(
            note_type="thread-doc",
            title=heading,
            text=body_text,
            project_links=[project],
        )
        if normalized.issues:
            raise ValueError("无法规范化产物正文：" + format_normalization_error(normalized.issues))
        _write_note(path, meta, normalized.body)
        _check(path)
        _touch_projects_activity(vault_dir, [project], day)
        if activity_migration is not None:
            activity_migration.record_thread_doc(
                path,
                project=project,
                activity_date=day,
                causation_operation_id=causation_operation_id or str(uuid4()),
                occurred_at=occurred_at,
            )
    return path
