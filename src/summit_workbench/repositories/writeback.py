"""审批后的本地 Markdown 写回；稳定候选标记保证重复执行不重复追加。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from summit_workbench.domain.review import CandidateKind
from summit_workbench.repositories._atomic import atomic_write_text

_GLOBAL_INBOX_HEADING = "## 待处理条目"

# 知识线程项目的「他人行动项责任记录」区块（主档案内可选固定区块，见 conventions.md）。
_PROJECT_FOLLOWUP_HEADING = "## 跟进事项"


def _ensure_global_inbox(path: Path) -> None:
    """全局 inbox 是「目标项目不明」的兜底落点，缺失时按 vault schema 创建。"""
    if path.is_file():
        return
    today = datetime.now(UTC).date().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndate: {today}\ntype: inbox\nstatus: active\nproject: global\n---\n\n"
        f"# 全局收件箱（inbox）\n\n{_GLOBAL_INBOX_HEADING}\n",
        encoding="utf-8",
    )


def _append_under_heading(
    path: Path, heading: str, line: str, candidate_id: str, markers: Sequence[str] | None = None
) -> bool:
    if not path.is_file():
        raise ValueError(f"写回目标不存在：{path}")
    text = path.read_text(encoding="utf-8")
    marker = f"<!-- wb-candidate: {candidate_id} -->"
    if marker in text:
        return False
    lines = text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as exc:
        raise ValueError(f"写回目标缺少固定区块 {heading!r}：{path}") from exc
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    while end > start and not lines[end - 1].strip():
        end -= 1
    extra = [f"  <!-- {m} -->" for m in (markers or [])]
    addition = ["", f"- {line}", f"  {marker}", *extra, ""]
    updated = [*lines[:end], *addition, *lines[end:]]
    atomic_write_text(path, "\n".join(updated).rstrip() + "\n")
    return True


def set_project_status(vault_dir: Path, project: str, text: str) -> tuple[Path, bool]:
    """把主档案「当前状态」区块内容整体替换为一段文本（P3：产物摘要 → 状态草案）。

    只改该区块内的内容行，其余区块与 frontmatter 原样保留（原子写；旧版可由 vault
    git 找回）。调用方负责确认语义与更新 frontmatter ``updated``。
    """
    path = vault_dir / "projects" / f"{project}.md"
    if not path.is_file():
        raise ValueError(f"写回目标不存在：{path}")
    body = path.read_text(encoding="utf-8")
    lines = body.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## 当前状态") + 1
    except StopIteration as exc:
        raise ValueError(f"主档案缺少固定区块「当前状态」：{path}") from exc
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    # 去掉被替换区间首尾的空行，再以「文本 + 空行」接入下一个区块。
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    updated = [*lines[:start], text, "", *lines[end:]]
    atomic_write_text(path, "\n".join(updated).rstrip() + "\n")
    return path, True


def append_project_main(
    vault_dir: Path,
    project: str,
    description: str,
    candidate_id: str,
    kind: CandidateKind,
) -> tuple[Path, bool]:
    path = vault_dir / "projects" / f"{project}.md"
    heading = "## 决策记录" if kind is CandidateKind.DECISION else "## 下一步"
    return path, _append_under_heading(path, heading, description, candidate_id)


def _ensure_heading(path: Path, heading: str) -> None:
    """正文缺少某固定二级标题时在文末补齐（只加标题，不动既有内容）。

    用于主档案新增的可选区块（如「跟进事项」）：老档案可能没有该区块，首次写回时先补上，
    避免把写回目标拒之门外。
    """
    text = path.read_text(encoding="utf-8")
    if heading in text.splitlines():
        return
    atomic_write_text(path, text.rstrip() + f"\n\n{heading}\n\n")


def append_project_followup(
    vault_dir: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    """把「他人行动项」写成主档案「跟进事项」下的待闭环责任记录（``- [ ] `` 复选框）。

    产品语义（R4）：他人承诺的事沉淀为责任记录，不进本人待办；勾选闭环与否由本人后续
    人工维护，系统不自动置为完成。
    """
    path = vault_dir / "projects" / f"{project}.md"
    if not path.is_file():
        raise ValueError(f"写回目标不存在：{path}")
    _ensure_heading(path, _PROJECT_FOLLOWUP_HEADING)
    written = _append_under_heading(
        path, _PROJECT_FOLLOWUP_HEADING, f"[ ] {description}", candidate_id
    )
    return path, written


def _ensure_thread_inbox(path: Path, project: str) -> None:
    """知识线程项目的 inbox 落点：``_vault/inboxes/<project>.md``（无 Work 文件夹时）。"""
    if path.is_file():
        return
    today = datetime.now(UTC).date().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndate: {today}\ntype: project-inbox\nstatus: active\nproject: {project}\n---\n\n"
        f"# {project} · inbox\n\n{_GLOBAL_INBOX_HEADING}\n",
        encoding="utf-8",
    )


def append_thread_inbox(
    vault_dir: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    """把未成熟想法写进线程项目的 vault inbox（``_vault/inboxes/<project>.md``）。"""
    path = vault_dir / "inboxes" / f"{project}.md"
    _ensure_thread_inbox(path, project)
    written = _append_under_heading(path, _GLOBAL_INBOX_HEADING, f"[ ] {description}", candidate_id)
    return path, written


def append_global_inbox(
    vault_dir: Path,
    description: str,
    candidate_id: str,
    *,
    markers: Sequence[str] | None = None,
) -> tuple[Path, bool]:
    path = vault_dir / "inbox.md"
    _ensure_global_inbox(path)
    written = _append_under_heading(
        path, _GLOBAL_INBOX_HEADING, f"[ ] {description}", candidate_id, markers=markers
    )
    return path, written


def append_project_inbox(
    work_root: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    path = work_root / project / "input" / "inbox.md"
    return path, _append_under_heading(path, "## 待处理条目", f"[ ] {description}", candidate_id)
