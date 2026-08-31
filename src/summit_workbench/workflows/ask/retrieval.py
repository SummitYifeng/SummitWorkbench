"""本地 vault 召回：按路径 / frontmatter / 全文筛选候选笔记（PRD M1-6）。

只做确定性、可测的本地检索（ripgrep 等价的全文子串打分），不调用模型。默认排除派生的
``qa-insight``（事实检索不吃自己产出的洞察）与原始逐字稿 / 审批页等非知识内容。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from summit_workbench.repositories.vault import iter_markdown_files, load_note

# 默认不进入问答上下文的笔记类型：派生洞察、原始证据、临时审批页。
_EXCLUDED_TYPES = frozenset({"qa-insight", "meeting-transcript", "approval-page"})
_BODY_CHAR_CAP = 4000  # 单篇进入上下文的正文上限，避免单篇长文挤占预算
_TOKEN_RE = re.compile(r"[^\s]+")


@dataclass(frozen=True)
class Candidate:
    source_id: str  # vault 相对路径（无 .md），既是引用锚点也是 [[wikilink]]
    title: str
    note_type: str
    projects: tuple[str, ...]
    body: str
    score: float


def _terms(query: str) -> list[str]:
    """把查询拆成匹配词：空白分词；单词且够长时补 2-gram，改善中文子串召回。"""
    tokens = [t.lower() for t in _TOKEN_RE.findall(query) if t.strip()]
    if len(tokens) <= 1:
        compact = "".join(tokens)
        if len(compact) >= 3:
            tokens.extend(compact[i : i + 2] for i in range(len(compact) - 1))
    return list(dict.fromkeys(tokens))  # 去重保序


def _title(meta: dict[str, object], body: str, path: Path) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raw = meta.get("project")
    return str(raw) if isinstance(raw, str) and raw else path.stem


def _projects(meta: dict[str, object]) -> tuple[str, ...]:
    single = meta.get("project")
    if isinstance(single, str) and single and single != "global":
        return (single,)
    multi = meta.get("projects")
    if isinstance(multi, list):
        return tuple(str(item) for item in multi if str(item))
    return ()


def _matches_project(project: str, note_projects: tuple[str, ...], source_id: str) -> bool:
    if project in note_projects:
        return True
    return source_id.startswith(f"projects/{project}")


def _score(terms: list[str], title: str, meta_blob: str, body: str) -> float:
    lowered_body = body.lower()
    lowered_title = title.lower()
    lowered_meta = meta_blob.lower()
    total = 0.0
    for term in terms:
        total += 3.0 * lowered_title.count(term)
        total += 2.0 * lowered_meta.count(term)
        total += 1.0 * lowered_body.count(term)
    return total


def retrieve_candidates(
    vault_dir: Path,
    query: str,
    *,
    project: str | None = None,
    limit: int = 6,
) -> list[Candidate]:
    """返回按相关度降序、最多 ``limit`` 篇的候选。查询为空或无命中时返回空列表。"""
    terms = _terms(query)
    if not terms or not vault_dir.is_dir():
        return []
    scored: list[Candidate] = []
    for path in iter_markdown_files(vault_dir):
        note = load_note(path)
        if note.parse_error is not None:
            continue
        note_type = str(note.meta.get("type") or "")
        if note_type in _EXCLUDED_TYPES:
            continue
        source_id = path.relative_to(vault_dir).with_suffix("").as_posix()
        projects = _projects(note.meta)
        if project is not None and not _matches_project(project, projects, source_id):
            continue
        title = _title(note.meta, note.body, path)
        meta_blob = " ".join([source_id, note_type, *projects])
        score = _score(terms, title, meta_blob, note.body)
        if score <= 0:
            continue
        scored.append(
            Candidate(
                source_id=source_id,
                title=title,
                note_type=note_type,
                projects=projects,
                body=note.body[:_BODY_CHAR_CAP].strip(),
                score=score,
            )
        )
    scored.sort(key=lambda c: (-c.score, c.source_id))
    return scored[:limit]
