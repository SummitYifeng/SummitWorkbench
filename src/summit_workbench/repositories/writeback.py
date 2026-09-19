"""审批后的本地 Markdown 写回；稳定候选标记保证重复执行不重复追加。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.review import CandidateKind
from summit_workbench.domain.time import business_date
from summit_workbench.repositories._atomic import atomic_write_text

# 全局收件箱的待处理区标题。**公开**为唯一真源：解析侧（`repositories/inbox.py`）与
# 写入口必须用同一个字符串，否则会出现"写得进去、读不出来"的静默错位。
GLOBAL_INBOX_HEADING = "## 待处理条目"
_GLOBAL_INBOX_HEADING = GLOBAL_INBOX_HEADING

# 知识线程项目的「他人行动项责任记录」区块（主档案内可选固定区块，见 conventions.md）。
PROJECT_FOLLOWUP_HEADING = "## 跟进事项"
_PROJECT_FOLLOWUP_HEADING = PROJECT_FOLLOWUP_HEADING


def _ensure_global_inbox(path: Path) -> None:
    """全局 inbox 是「目标项目不明」的兜底落点，缺失时按 vault schema 创建。"""
    if path.is_file():
        return
    today = business_date(datetime.now(UTC))
    atomic_write_text(
        path,
        f"---\ndate: {today}\ntype: inbox\nstatus: active\nproject: global\n---\n\n"
        f"# 全局收件箱（inbox）\n\n{_GLOBAL_INBOX_HEADING}\n",
        ensure_parents=True,
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
    matches = [index for index, line in enumerate(lines) if line.rstrip() == heading]
    if not matches:
        raise ValueError(f"写回目标缺少固定区块 {heading!r}：{path}")
    if len(matches) > 1:
        # 重复区块标题会让「写回哪一节」变得不确定（旧实现静默写进第一处）。
        # 这里拒绝并给出可读原因，让使用者在审批页看到问题、先合并区块。
        raise ValueError(
            f"写回目标存在重复区块标题 {heading!r}（{len(matches)} 处）：{path}；"
            "请先合并为唯一区块再批准"
        )
    start = matches[0] + 1
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
    with workspace_lock(vault_dir.parent):
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
    with workspace_lock(vault_dir.parent):
        path = vault_dir / "projects" / f"{project}.md"
        heading = "## 决策记录" if kind is CandidateKind.DECISION else "## 下一步"
        written = _append_under_heading(path, heading, description, candidate_id)
        return path, written


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
    with workspace_lock(vault_dir.parent):
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
    today = business_date(datetime.now(UTC))
    atomic_write_text(
        path,
        f"---\ndate: {today}\ntype: project-inbox\nstatus: active\nproject: {project}\n---\n\n"
        f"# {project} · inbox\n\n{_GLOBAL_INBOX_HEADING}\n",
        ensure_parents=True,
    )


def append_thread_inbox(
    vault_dir: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    """把未成熟想法写进线程项目的 vault inbox（``_vault/inboxes/<project>.md``）。"""
    with workspace_lock(vault_dir.parent):
        path = vault_dir / "inboxes" / f"{project}.md"
        _ensure_thread_inbox(path, project)
        written = _append_under_heading(
            path, _GLOBAL_INBOX_HEADING, f"[ ] {description}", candidate_id
        )
        return path, written


def append_global_inbox(
    vault_dir: Path,
    description: str,
    candidate_id: str,
    *,
    markers: Sequence[str] | None = None,
) -> tuple[Path, bool]:
    with workspace_lock(vault_dir.parent):
        path = vault_dir / "inbox.md"
        _ensure_global_inbox(path)
        written = _append_under_heading(
            path, _GLOBAL_INBOX_HEADING, f"[ ] {description}", candidate_id, markers=markers
        )
        return path, written


def append_project_inbox(
    work_root: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    with workspace_lock(work_root):
        path = work_root / project / "input" / "inbox.md"
        written = _append_under_heading(path, "## 待处理条目", f"[ ] {description}", candidate_id)
        return path, written


# 知识沉淀的默认落点区块：小项目页与项目主页都用它承载「一句话级结论」。
_DEFAULT_KNOWLEDGE_HEADING = "## 关键结论"


def parse_sink_target(sink_target: str) -> tuple[PurePosixPath, str]:
    """把 `<vault 相对页面路径>#<区块标题>` 解析成 ``(相对路径, 完整区块标题行)``。

    - 缺 `#区块` 时默认 ``## 关键结论``；
    - 区块标题允许写成 `关键结论` 或 `## 关键结论`，统一规整成后者；
    - **只接受 vault 相对路径**：绝对路径或含 `..` 的目标一律拒绝——否则一条审批写回
      就能把内容写到库外（这是审批链路上最需要守住的边界）。

    变异验证：把 `..` 检查去掉，`tests/unit/test_review_apply_meeting_links.py` 里
    针对路径穿越的用例必须变红。
    """
    raw = sink_target.strip()
    if "\n" in raw or "\r" in raw:
        raise ValueError(f"知识沉淀目标不能含换行：{sink_target!r}")
    page, _, block = raw.partition("#")
    page = page.strip()
    if page.endswith(".md"):
        page = page[: -len(".md")]
    if not page:
        raise ValueError(f"知识沉淀目标缺少页面路径：{sink_target!r}")
    rel = PurePosixPath(page)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"知识沉淀目标必须是 vault 相对路径（不得越出库）：{sink_target!r}")
    # 区块标题允许 `关键结论` 或 `## 关键结论`；剥掉前导 `#` 后仍含 `#` 说明锚点无法解析
    # （例如 `page#a#b`）——旧实体会拼出一个永远匹配不到的 `## a#b` 标题，报错指向
    # 「缺少固定区块」而不是真因，所以在这一层就拒绝。
    title = block.strip().lstrip("#").strip()
    if "#" in title:
        raise ValueError(f"知识沉淀目标的区块标题无法解析（含多余的 '#'）：{sink_target!r}")
    if not title:
        title = _DEFAULT_KNOWLEDGE_HEADING.removeprefix("## ")
    return rel, f"## {title}"


def append_knowledge_note(
    vault_dir: Path,
    sink_target: str,
    description: str,
    candidate_id: str,
    *,
    source_ref: str | None = None,
    today: str | None = None,
) -> tuple[Path, bool]:
    """「知识沉淀」落点：把一条结论追加到目标页的指定区块，并留出处。

    为什么它与其它落点不同：待办要落到飞书 / 项目主页，而**知识结论**要落回它所属的
    小项目页（如 `hii-ip-license/ip-trademark#关键结论`）。落点由使用者在审批页显式指定，
    app 不自动猜——「这条结论该进哪一页的哪一节」是业务判断。

    写入行格式：``- YYYY-MM-DD <结论>（出处：<source_ref>）``，
    幂等标记沿用 `_append_under_heading`（同一 candidate_id 重复批准不会重复追加）。
    """
    rel, heading = parse_sink_target(sink_target)
    with workspace_lock(vault_dir.parent):
        path = vault_dir / rel.with_suffix(".md")
        if not path.is_file():
            raise ValueError(f"写回目标不存在：{path}")
        stamp = today or business_date(datetime.now(UTC))
        line = f"{stamp} {description.strip()}"
        if source_ref and source_ref.strip():
            line += f"（出处：{source_ref.strip()}）"
        written = _append_under_heading(path, heading, line, candidate_id)
        return path, written
