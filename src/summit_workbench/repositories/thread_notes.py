"""线程知识笔记的落盘：推进日志（work-log）与 AI 产物（thread-doc）。

两条写入都遵守 vault schema（统一 frontmatter + 固定区块），落盘后即时 self-check，
保证任何写进 vault 的内容都能通过 ``wb vault check``：

- 推进日志 ``_vault/logs/YYYY-MM-DD-<seq>.md``：``type: work-log``，可关联 1..n 个
  线程/仓库项目（``projects: [...]``），正文保留原文 + AI 摘要；模型不可用时原文照存。
- AI 产物 ``_vault/artifacts/<project>-<seq>.md``：``type: thread-doc``，单项目
  （``project: <id>``），frontmatter 带 ``title / summary / kind`` 供检索命中。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.threaddoc import ArtifactKind, LogTag
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import load_note

_SLUG_RE = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff_-]+")
_LOGS_DIRNAME = "logs"
_ARTIFACTS_DIRNAME = "artifacts"


def _day(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


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
    """写盘后自检：load + schema 校验失败即抛错（不落坏笔记）。"""
    from summit_workbench.domain.vault import validate_note

    note = load_note(path)
    if note.parse_error is not None:
        raise ValueError(f"笔记 frontmatter 无法解析：{path}：{note.parse_error}")
    issues = validate_note(note.meta, note.body)
    if issues:
        raise ValueError(f"笔记不符合 vault schema：{path}：" + "; ".join(str(i) for i in issues))


def _clean_text(text: str) -> str:
    """去掉首尾空白但保留正文换行（不要像单行捕捉那样折叠）。"""
    return text.strip()


def _project_links(projects: Sequence[str]) -> str:
    """正文的「关联项目」回链：每条 ``- [[projects/<id>]]``。

    vault 以 ``_vault`` 为 Obsidian 库根，``[[projects/<id>]]`` 即指向
    ``_vault/projects/<id>.md`` 主档案——日志/产物由此在 Obsidian 图谱里
    连回项目（frontmatter 关联之外的实体双链）。
    """
    return "\n".join(f"- [[projects/{project}]]" for project in projects)


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


def append_work_log(
    vault_dir: Path,
    *,
    projects: Sequence[str],
    text: str,
    summary: str = "",
    involved: Iterable[str] = (),
    tags: Iterable[LogTag] = (),
    next_step: str | None = None,
    decision: str | None = None,
    now: datetime | None = None,
) -> Path:
    """落一条推进日志（可关联多线程）。``text`` 必填；``summary`` 空 = 模型未消化，原文照存。"""
    body_text = _clean_text(text)
    if not body_text:
        raise ValueError("日志正文不能为空")
    if not projects:
        raise ValueError("推进日志至少要关联一个项目/线程")
    day = _day(now)
    projects_list = list(dict.fromkeys(projects))
    meta: dict[str, object] = {
        "date": day,
        "type": "work-log",
        "status": "generated" if summary else "draft",
        "projects": projects_list,
    }
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

    body = f"# 推进日志 {day}（{projects_list[0]} 等）\n\n"
    body += "## 原文\n\n" + body_text + "\n"
    if summary:
        body += "\n## AI 摘要\n\n" + summary + "\n"
    # 实体双链（改进 1）：正文回链到所关联项目的主档案，供 Obsidian 图谱/反链使用。
    body += "\n## 关联项目\n\n" + _project_links(projects_list) + "\n"
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
        _touch_projects_activity(vault_dir, projects_list, day)
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
) -> Path:
    """把一段 AI 产物（阶段总结/PRD/背景包/timeline）存进线程档案目录。"""
    body_text = _clean_text(text)
    if not body_text:
        raise ValueError("产物正文不能为空")
    day = _day(now)

    meta: dict[str, object] = {
        "date": day,
        "type": "thread-doc",
        "status": "generated" if summary else "draft",
        "project": project,
        "kind": kind.value,
    }
    if title:
        meta["title"] = title
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
        body = f"# {heading}\n\n" + body_text + "\n"
        # 实体双链（改进 1）：产物回链到所属项目的主档案（Obsidian 图谱/反链）。
        body += "\n## 关联项目\n\n" + _project_links([project]) + "\n"
        _write_note(path, meta, body)
        _check(path)
        _touch_projects_activity(vault_dir, [project], day)
    return path
