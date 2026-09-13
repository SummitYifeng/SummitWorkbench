"""知识库检索索引：frontmatter 结构化表 + 按 ``##`` 分块的 FTS5(trigram) 全文索引。

三条硬约束（见 `_vault/conventions.md` §0）：

1. **索引库放在 vault 之外**（默认 ``Application Support/SummitWorkbench/kb-index.sqlite``），
   以免污染资产与双机同步；
2. **可重建**：全量重建必须随时可用，增量按 ``(path, mtime, size, hash)`` 跳过未变文件；
3. **不是阅读前提**：索引缺失/损坏时，检索退化为纯 Python BM25 扫描（本模块自带），
   纯 Markdown + Git 始终自足。

FTS5 是否可用**先探测再决定**，不假设：探测失败时 `search` 返回 ``None``，
由上层走 BM25 兜底，而不是让整次问答失败。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from summit_workbench.config.app_support import app_support_dir
from summit_workbench.workflows.ask.chunking import chunk_markdown
from summit_workbench.workflows.ask.terms import fts_query, query_terms

_SKIP_DIRS = {".git", ".obsidian", "_signals", ".summit-workbench", "templates"}
# 不进索引的 status：草稿不是事实，不得被问答当成依据（conventions §2.2）。
_EXCLUDED_STATUS = frozenset({"draft"})
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
# 存在 meta_json 里的双链键名（避免为此加一列而破坏既有索引库）
_LINKS_KEY = "__links__"
TITLE = re.compile(r"^#\s+(.*?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class NoteMeta:
    """一篇笔记的结构化元数据（frontmatter 的检索侧投影）。"""

    source_id: str
    title: str
    area: str
    workstream: str
    type: str
    status: str
    date: str
    updated: str
    summary: str
    domain: str
    projects: tuple[str, ...]
    people: tuple[str, ...]
    org: tuple[str, ...]
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    links: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    """一次块级命中。``anchor`` 即可直接写进答案的 ``路径#区块`` 引用。"""

    source_id: str
    heading: str
    text: str
    score: float

    @property
    def anchor(self) -> str:
        return f"{self.source_id}#{self.heading}" if self.heading else self.source_id


@dataclass(frozen=True)
class IndexStats:
    added: int
    updated: int
    removed: int
    skipped: int
    chunks: int

    def summary(self) -> str:
        return (
            f"新增 {self.added}，更新 {self.updated}，移除 {self.removed}，"
            f"跳过（未变）{self.skipped}，总块数 {self.chunks}"
        )


def fts5_available() -> bool:
    """探测当前解释器的 SQLite 是否支持 FTS5 与 trigram 分词器。"""
    try:
        connection = sqlite3.connect(":memory:")
    except sqlite3.Error:  # pragma: no cover - 解释器级异常
        return False
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(x, tokenize='trigram')")
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def default_index_path(home: Path | None = None) -> Path:
    """索引库默认位置：vault **之外**的本机 Application Support。"""
    return app_support_dir(home) / "kb-index.sqlite"


def _as_list(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _title(meta: dict[str, object], body: str, source_id: str) -> str:
    front = _text(meta.get("title"))
    if front:
        return front
    match = TITLE.search(body)
    if match:
        return match.group(1)
    return source_id.rsplit("/", 1)[-1]


def parse_note(text: str) -> tuple[dict[str, object], str] | None:
    """切出 frontmatter 与正文；无 frontmatter / YAML 非法时返回 None（该文件不进索引）。"""
    if not text.startswith("---"):
        return None
    rest = text.split("\n", 1)[1] if "\n" in text else ""
    end = rest.find("\n---")
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(rest[:end]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    return meta, rest[end + len("\n---") :].lstrip("\n")


def note_meta(source_id: str, meta: dict[str, object], body: str) -> NoteMeta:
    """由 frontmatter 与正文构造检索侧元数据。``project`` 与 ``projects`` 合并成一个列表。"""
    projects = list(_as_list(meta.get("projects")))
    single = _text(meta.get("project"))
    if single and single != "global" and single not in projects:
        projects.insert(0, single)
    return NoteMeta(
        source_id=source_id,
        title=_title(meta, body, source_id),
        area=_text(meta.get("area")),
        workstream=_text(meta.get("workstream")),
        type=_text(meta.get("type")),
        status=_text(meta.get("status")),
        date=_text(meta.get("date")),
        updated=_text(meta.get("updated")) or _text(meta.get("date")),
        summary=_text(meta.get("summary")),
        domain=_text(meta.get("domain")),
        projects=tuple(projects),
        people=_as_list(meta.get("people")),
        org=_as_list(meta.get("org")),
        tags=_as_list(meta.get("tags")),
        aliases=_as_list(meta.get("aliases")),
        links=tuple(match.group(1).strip() for match in WIKILINK.finditer(body)),
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    source_id TEXT PRIMARY KEY,
    hash TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    title TEXT NOT NULL,
    area TEXT, workstream TEXT, type TEXT, status TEXT, domain TEXT,
    date TEXT, updated TEXT, summary TEXT, meta_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    heading TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);
"""

_FTS_SCHEMA = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
    "heading, text, content='chunks', content_rowid='id', tokenize='trigram')"
)


class KnowledgeIndex:
    """可重建的本地检索索引。所有写操作都只碰 ``db_path``，从不写 vault。"""

    def __init__(self, vault_dir: Path, db_path: Path) -> None:
        self.vault_dir = vault_dir.expanduser().resolve()
        self.db_path = db_path.expanduser()
        self.fts_ok = fts5_available()
        self._notes: dict[str, NoteMeta] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        if self.fts_ok:
            self._connection.execute(_FTS_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> KnowledgeIndex:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---- 构建 ----

    def _markdown_files(self) -> Iterator[Path]:
        for path in sorted(self.vault_dir.rglob("*.md")):
            parts = path.relative_to(self.vault_dir).parts
            if any(part in _SKIP_DIRS for part in parts):
                continue
            yield path

    def build(self, *, full: bool = False) -> IndexStats:
        """增量（默认）或全量重建索引。"""
        if full:
            self._connection.executescript("DELETE FROM chunks; DELETE FROM notes;")
            self._connection.commit()
        known = {
            row["source_id"]: row["hash"]
            for row in self._connection.execute("SELECT source_id, hash FROM notes")
        }
        seen: set[str] = set()
        added = updated = skipped = 0
        for path in self._markdown_files():
            source_id = path.relative_to(self.vault_dir).with_suffix("").as_posix()
            seen.add(source_id)
            try:
                text = path.read_text(encoding="utf-8")
                stat = path.stat()
            except (OSError, UnicodeDecodeError):
                continue  # 非 UTF-8 / 不可读：不是笔记，跳过而不是让整次构建失败
            digest = _digest(text)
            previous = known.get(source_id)
            if previous == digest and not full:
                skipped += 1
                continue
            parsed = parse_note(text)
            if parsed is None:
                continue
            meta, body = parsed
            if _text(meta.get("status")) in _EXCLUDED_STATUS:
                self._delete_note(source_id)
                continue
            info = note_meta(source_id, meta, body)
            self._upsert_note(info, digest, stat.st_mtime, stat.st_size, meta, body)
            if previous is None:
                added += 1
            else:
                updated += 1
        removed = self._prune(seen)
        self._rebuild_fts()
        self._connection.commit()
        self._notes = {}
        total = int(self._connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        return IndexStats(
            added=added, updated=updated, removed=removed, skipped=skipped, chunks=total
        )

    def _delete_note(self, source_id: str) -> None:
        self._connection.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        self._connection.execute("DELETE FROM notes WHERE source_id = ?", (source_id,))

    def _upsert_note(
        self,
        info: NoteMeta,
        digest: str,
        mtime: float,
        size: int,
        meta: dict[str, object],
        body: str,
    ) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO notes (source_id, hash, mtime, size, title, area, workstream,"
            " type, status, domain, date, updated, summary, meta_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                info.source_id,
                digest,
                mtime,
                size,
                info.title,
                info.area,
                info.workstream,
                info.type,
                info.status,
                info.domain,
                info.date,
                info.updated,
                info.summary,
                # 双链随元数据一起落库：不加这个，`notes()` 重建出来的 NoteMeta 会丢掉
                # `links`（正文不在库里），双链扩展与「笔记→逐字稿」链路会永远为空。
                json.dumps({**meta, _LINKS_KEY: list(info.links)}, ensure_ascii=False, default=str),
            ),
        )
        self._connection.execute("DELETE FROM chunks WHERE source_id = ?", (info.source_id,))
        chunks = chunk_markdown(info.source_id, body)
        self._connection.executemany(
            "INSERT INTO chunks (source_id, heading, text) VALUES (?,?,?)",
            [(chunk.source_id, chunk.heading, chunk.text) for chunk in chunks],
        )

    def _prune(self, seen: set[str]) -> int:
        stale = [
            row["source_id"]
            for row in self._connection.execute("SELECT source_id FROM notes")
            if row["source_id"] not in seen
        ]
        for source_id in stale:
            self._delete_note(source_id)
        return len(stale)

    def _rebuild_fts(self) -> None:
        if self.fts_ok:
            self._connection.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")

    # ---- 读取 ----

    def notes(self) -> dict[str, NoteMeta]:
        """全部笔记元数据（首次调用时从库里加载）。"""
        if not self._notes:
            loaded: dict[str, NoteMeta] = {}
            for row in self._connection.execute("SELECT * FROM notes"):
                raw = json.loads(row["meta_json"])
                links = tuple(str(item) for item in raw.pop(_LINKS_KEY, []) or [])
                info = note_meta(row["source_id"], raw, "")
                loaded[row["source_id"]] = replace(info, title=row["title"], links=links)
            self._notes = loaded
        return self._notes

    def aliases(self) -> dict[str, str]:
        """别名 / 文件名 → source_id，供双链与 ``aliases`` 解析。"""
        index: dict[str, str] = {}
        for info in self.notes().values():
            index.setdefault(info.source_id.casefold(), info.source_id)
            index.setdefault(Path(info.source_id).stem.casefold(), info.source_id)
            for alias in info.aliases:
                index.setdefault(alias.casefold(), info.source_id)
        return index

    def resolve_link(self, target: str, *, aliases: dict[str, str] | None = None) -> str | None:
        """把双链目标（文件名 / 路径 / 别名）解析成 source_id；解析不到返回 None。"""
        table = aliases if aliases is not None else self.aliases()
        key = target.strip().removesuffix(".md").casefold()
        if not key:
            return None
        return table.get(key) or table.get(key.rsplit("/", 1)[-1])

    def neighbours(self, source_id: str, *, hops: int = 1) -> set[str]:
        """双链扩展：出链 + 入链，支持 1–2 跳（别名参与解析）。"""
        notes = self.notes()
        aliases = self.aliases()
        reached = {source_id}
        frontier = {source_id}
        for _ in range(max(1, hops)):
            out: set[str] = set()
            for current in frontier:
                info = notes.get(current)
                if info is None:
                    continue
                for link in info.links:
                    resolved = self.resolve_link(link, aliases=aliases)
                    if resolved:
                        out.add(resolved)
            for other, info in notes.items():
                if other in reached or other in out:
                    continue
                if any(self.resolve_link(link, aliases=aliases) in frontier for link in info.links):
                    out.add(other)
            new = out - reached
            if not new:
                break
            reached |= new
            frontier = new
        reached.discard(source_id)
        return reached

    def search(self, query: str, *, limit: int = 300) -> list[Hit] | None:
        """FTS5 块级检索；FTS5 不可用或无可用检索词时返回 None（交给 BM25 兜底）。"""
        if not self.fts_ok:
            return None
        expression = fts_query(query_terms(query))
        if not expression:
            return None
        rows = self._connection.execute(
            "SELECT c.source_id, c.heading, c.text, bm25(chunks_fts) AS rank"
            " FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
            " WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (expression, limit),
        )
        return [
            Hit(
                source_id=row["source_id"],
                heading=row["heading"],
                text=row["text"],
                # bm25() 越小越相关；取负号让「越大越相关」与其它信号同向
                score=-float(row["rank"]),
            )
            for row in rows
        ]

    def all_chunks(self) -> Iterable[Hit]:
        """全部块（BM25 兜底用）。"""
        for row in self._connection.execute("SELECT source_id, heading, text FROM chunks"):
            yield Hit(
                source_id=row["source_id"],
                heading=row["heading"],
                text=row["text"],
                score=0.0,
            )

    def representative_chunk(self, source_id: str) -> Hit | None:
        """取一篇笔记的代表块（首块），供双链扩展把证据层带进检索轨迹。"""
        row = self._connection.execute(
            "SELECT heading, text FROM chunks WHERE source_id = ? ORDER BY id LIMIT 1",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return Hit(source_id=source_id, heading=row["heading"], text=row["text"], score=0.0)

    def chunk_count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])


def bm25_scores(hits: Iterable[Hit], query: str, *, k1: float = 1.2, b: float = 0.75) -> list[Hit]:
    """纯 Python BM25（FTS5 不可用时的兜底）。

    只对**查询词**做子串计数，因此成本与查询词数成正比，而不是与词表大小成正比。
    """
    terms = query_terms(query)
    if not terms:
        return []
    items = list(hits)
    if not items:
        return []
    lengths = [len(item.text) or 1 for item in items]
    average = sum(lengths) / len(lengths)
    total = len(items)
    lowered = [item.text.casefold() for item in items]
    document_frequency = {
        term: sum(1 for text in lowered if term.casefold() in text) for term in terms
    }
    scored: list[Hit] = []
    for item, length, text in zip(items, lengths, lowered, strict=True):
        score = 0.0
        for term in terms:
            frequency = text.count(term.casefold())
            if not frequency:
                continue
            idf = math.log(
                1 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * length / average)
            score += idf * frequency * (k1 + 1) / denominator
        if score > 0:
            scored.append(
                Hit(source_id=item.source_id, heading=item.heading, text=item.text, score=score)
            )
    scored.sort(key=lambda hit: (-hit.score, hit.source_id, hit.heading))
    return scored
