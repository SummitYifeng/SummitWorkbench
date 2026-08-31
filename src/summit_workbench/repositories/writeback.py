"""审批后的本地 Markdown 写回；稳定候选标记保证重复执行不重复追加。"""

from __future__ import annotations

from pathlib import Path

from summit_workbench.domain.review import CandidateKind


def _append_under_heading(path: Path, heading: str, line: str, candidate_id: str) -> bool:
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
    addition = ["", f"- {line}", f"  {marker}", ""]
    updated = [*lines[:end], *addition, *lines[end:]]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return True


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


def append_global_inbox(
    vault_dir: Path, description: str, candidate_id: str
) -> tuple[Path, bool]:
    path = vault_dir / "inbox.md"
    return path, _append_under_heading(path, "## 待处理条目", f"[ ] {description}", candidate_id)


def append_project_inbox(
    work_root: Path, project: str, description: str, candidate_id: str
) -> tuple[Path, bool]:
    path = work_root / project / "input" / "inbox.md"
    return path, _append_under_heading(path, "## 待处理条目", f"[ ] {description}", candidate_id)
