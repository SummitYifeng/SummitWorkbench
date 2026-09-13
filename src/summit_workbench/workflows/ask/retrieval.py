"""本地 vault 召回（PRD M1-6）。

两条路径：

- :func:`retrieve_candidates`：**旧版**子串打分扫描（ripgrep 等价、零依赖、全量扫全库）。
  保留它有两个作用：索引不可用时兜底；以及作为新检索的对照基线。
- :func:`retrieve_via_index`：**新检索主干**——块级 FTS5/BM25 + 查询路由 + 多信号融合，
  返回 ``路径#区块`` 级引用与检索轨迹（见 :mod:`.fusion` / :mod:`.router`）。

两条路径都只做确定性、可测的本地检索，不调用模型。默认排除派生的 ``qa-insight``
（事实检索不吃自己产出的洞察）与原始逐字稿 / 审批页等非知识内容。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from summit_workbench.repositories.kb_index import IndexStats
from summit_workbench.repositories.vault import iter_markdown_files, load_note
from summit_workbench.workflows.ask.fusion import Trace, Weights, fuse
from summit_workbench.workflows.ask.router import RoutingPlan, route_query

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
    why: tuple[str, ...] = ()  # 融合检索给出的「为什么命中」；旧版召回为空


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


def candidate_by_id(vault_dir: Path, source_id: str) -> Candidate | None:
    """按 source_id（vault 相对路径，无 .md）取回单篇候选，供追问轮重新纳入历史来源。

    只接受 vault 内的普通路径（拒绝越界/派生类型），笔记已删除或不可用时返回 None。
    """
    if not vault_dir.is_dir() or not source_id:
        return None
    # 追问轮可能回传「路径#区块」形式的引用：定位文件时只看路径部分，
    # 但返回值保留完整锚点，保证引用能原样延续。
    path_part = source_id.split("#", 1)[0]
    rel = Path(path_part)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    path = vault_dir.joinpath(rel).with_suffix(".md")
    if not path.is_file():
        return None
    note = load_note(path)
    if note.parse_error is not None:
        return None
    note_type = str(note.meta.get("type") or "")
    if note_type in _EXCLUDED_TYPES:
        return None
    return Candidate(
        source_id=source_id,
        title=_title(note.meta, note.body, path),
        note_type=note_type,
        projects=_projects(note.meta),
        body=note.body[:_BODY_CHAR_CAP].strip(),
        score=0.0,  # 固定召回：不参与相关度排序，仅作为历史延续来源
    )


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


def retrieve_via_index(
    vault_dir: Path,
    query: str,
    *,
    index_path: Path,
    project: str | None = None,
    workstream: str | None = None,
    limit: int | None = None,
    today: date | None = None,
    weights: Weights | None = None,
    plan: RoutingPlan | None = None,
) -> tuple[list[Candidate], Trace]:
    """索引 + 路由 + 融合的检索主干，返回 ``(候选, 检索轨迹)``。

    FTS5 不可用时自动退化为纯 Python BM25（``KnowledgeIndex.search`` 返回 ``None``），
    因此这条路径**不会**因为打包环境缺 FTS5 而失效。
    """
    from summit_workbench.repositories.kb_index import KnowledgeIndex, bm25_scores

    resolved_plan = plan or route_query(query)
    index = KnowledgeIndex(vault_dir, index_path)
    try:
        index.build()
        hits = index.search(query)
        if hits is None:  # FTS5 不可用 / 检索词全在 3 字以下 → BM25 兜底
            hits = bm25_scores(index.all_chunks(), query)
        ranked, trace = fuse(
            hits,
            index=index,
            query=query,
            plan=resolved_plan,
            weights=weights,
            today=today,
            project=project,
            workstream=workstream,
        )
        notes = index.notes()
        candidates = [
            Candidate(
                source_id=chunk.anchor,
                title=chunk.title,
                note_type=chunk.note_type,
                projects=notes[chunk.source_id].projects if chunk.source_id in notes else (),
                body=chunk.text[:_BODY_CHAR_CAP].strip(),
                score=chunk.score,
                why=chunk.why,
            )
            for chunk in ranked[: (limit or resolved_plan.limit)]
        ]
    finally:
        index.close()
    return candidates, trace


def build_index(vault_dir: Path, index_path: Path, *, full: bool = False) -> IndexStats:
    """重建（增量或全量）检索索引；供 ``wb kb index`` 调用。返回 ``IndexStats``。"""
    from summit_workbench.repositories.kb_index import KnowledgeIndex

    index = KnowledgeIndex(vault_dir, index_path)
    try:
        return index.build(full=full)
    finally:
        index.close()
