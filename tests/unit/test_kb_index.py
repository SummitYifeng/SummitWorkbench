"""索引层测试：构建/增量/全量、FTS5 与 BM25 两条分支、别名解析、双链扩展、位置约束。

变异验证（每条都对应一个「改坏了就会红」的断言）：
- 去掉 `_EXCLUDED_STATUS` → `draft` 笔记会进索引（本文件会红）；
- 去掉 `_prune` → 删除笔记后索引里仍有陈旧块；
- 去掉 `neighbours` 的入链分支 → 反向双链解析不到；
- 把 `default_index_path` 指回 vault → 位置约束断言失败。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from summit_workbench.repositories import kb_index as kb
from summit_workbench.repositories.kb_index import (
    KnowledgeIndex,
    bm25_scores,
    default_index_path,
    fts5_available,
)


def _note(vault: Path, rel: str, body: str, **front: object) -> Path:
    meta: dict[str, object] = {"date": "2026-09-13", "type": "note", "status": "active"}
    meta.update(front)
    lines = "\n".join(f"{key}: {value}" for key, value in meta.items())
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{lines}\n---\n\n{body}\n", encoding="utf-8")
    return path


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    _note(
        root,
        "hii/notes/20260912-trademark-consensus.md",
        "# HII–HIC 商标共识规范\n\n## 登记主体\n\n所有 registrations 登记在 HII 名下。\n\n"
        "## 逐项商标归属与状态\n\n活满归 HIC（已注册）；和夫曼之旅归 HII（正在注册）。",
        workstream="hii",
        aliases="[商标共识, trademark consensus]",
        people="[Kate Mayer]",
        org="[HII]",
    )
    _note(
        root,
        "hii/notes/20260912-hic-owned-assets.md",
        "# HIC 自有资产\n\n## 活满\n\n[[20260912-trademark-consensus|商标共识规范]] 是相关口径。",
        workstream="hii",
    )
    _note(
        root,
        "hii/sources/20260912-overview.md",
        "# 原文：全景总结\n\n## 六、正式名称\n\n商标共识规范的全部原文都在这里。",
        workstream="hii",
        type="source",
    )
    _note(
        root,
        "index/decisions.md",
        "# 决策台账\n\n## 生效中\n\n商标与版权口径。",
        type="index",
        project="global",
    )
    _note(root, "hii/notes/draft-one.md", "# 草稿\n\n商标共识规范的草稿。", status="draft")
    return root


def _build(vault: Path, tmp_path: Path) -> KnowledgeIndex:
    return KnowledgeIndex(vault, tmp_path / "kb.sqlite")


def test_index_file_lives_outside_the_vault(tmp_path: Path) -> None:
    """索引库默认位置必须在 vault 之外（否则会污染资产与双机同步）。"""
    home = tmp_path / "home"
    target = default_index_path(home)
    assert "Application Support" in str(target)
    assert not str(target).startswith(str(tmp_path / "vault"))


def test_build_indexes_chunks_and_metadata(vault: Path, tmp_path: Path) -> None:
    with _build(vault, tmp_path) as index:
        stats = index.build()
        assert stats.added == 4  # draft 在计数前就被排除（见下一个用例）
        assert index.chunk_count() > 0
        notes = index.notes()
        assert notes["hii/notes/20260912-trademark-consensus"].title == "HII–HIC 商标共识规范"
        assert notes["hii/notes/20260912-trademark-consensus"].workstream == "hii"


def test_draft_notes_are_not_indexed(vault: Path, tmp_path: Path) -> None:
    """`draft` 不是事实，不得进入问答索引（conventions §2.2）。"""
    with _build(vault, tmp_path) as index:
        index.build()
        assert "hii/notes/draft-one" not in index.notes()


def test_incremental_build_skips_unchanged_and_full_rebuilds(vault: Path, tmp_path: Path) -> None:
    with _build(vault, tmp_path) as index:
        index.build()
        again = index.build()
        assert again.added == 0 and again.updated == 0
        assert again.skipped == 4  # 4 篇非 draft
        _note(
            vault, "hii/notes/20260913-new.md", "# 新笔记\n\n商标共识规范补充。", workstream="hii"
        )
        third = index.build()
        assert third.added == 1
        full = index.build(full=True)
        assert full.skipped == 0 and full.added == 5


def test_deleted_note_is_pruned(vault: Path, tmp_path: Path) -> None:
    target = _note(vault, "hii/notes/temp.md", "# 临时\n\n商标共识规范。", workstream="hii")
    with _build(vault, tmp_path) as index:
        index.build()
        assert "hii/notes/temp" in index.notes()
        target.unlink()
        stats = index.build()
        assert stats.removed == 1
        assert "hii/notes/temp" not in index.notes()


def test_fts5_search_returns_block_level_hits(vault: Path, tmp_path: Path) -> None:
    if not fts5_available():
        pytest.skip("本解释器的 SQLite 不支持 FTS5")
    with _build(vault, tmp_path) as index:
        index.build()
        # 关键词只出现在一级标题里 → 命中的是「前言块」，锚点就是笔记本身
        title_hits = index.search("商标共识规范")
        assert title_hits, "FTS5 应能命中中文子串"
        assert "hii/notes/20260912-trademark-consensus" in {hit.anchor for hit in title_hits}

        # 关键词出现在某个 `##` 区块里 → 命中的是**那一块**，锚点带区块标题
        block_hits = index.search("和夫曼之旅")
        assert block_hits, "FTS5 应能命中区块正文"
        assert "hii/notes/20260912-trademark-consensus#逐项商标归属与状态" in {
            hit.anchor for hit in block_hits
        }


def test_bm25_fallback_works_without_fts5(vault: Path, tmp_path: Path, monkeypatch) -> None:
    """FTS5 不可用时检索必须仍然可用（打包环境可能缺 FTS5）。"""
    monkeypatch.setattr(kb, "fts5_available", lambda: False)
    with _build(vault, tmp_path) as index:
        index.build()
        assert index.search("商标共识规范") is None  # 明确告知上层：走兜底
        scored = bm25_scores(index.all_chunks(), "商标共识规范")
        assert scored
        assert scored[0].source_id.endswith("20260912-trademark-consensus")


def test_aliases_resolve_to_notes(vault: Path, tmp_path: Path) -> None:
    """双链解析必须认 `aliases`（重命名后旧链接仍要能解析）。"""
    with _build(vault, tmp_path) as index:
        index.build()
        assert index.resolve_link("商标共识") == "hii/notes/20260912-trademark-consensus"
        assert (
            index.resolve_link("20260912-trademark-consensus.md")
            == "hii/notes/20260912-trademark-consensus"
        )
        assert index.resolve_link("根本不存在的东西") is None


def test_neighbours_expand_outlinks_and_inlinks(vault: Path, tmp_path: Path) -> None:
    """双链扩展要同时走出链与入链（1–2 跳），这是「笔记→逐字稿」走通的机制。"""
    _note(
        vault,
        "meetings/notes/20260907-it-alignment.md",
        "# 对齐会\n\n## 证据索引\n\n[[20260912-hic-owned-assets|HIC 自有资产]]。",
        type="meeting-note",
        projects="[hic-enrollment]",
    )
    with _build(vault, tmp_path) as index:
        index.build()
        out = index.neighbours("hii/notes/20260912-hic-owned-assets", hops=1)
        assert "hii/notes/20260912-trademark-consensus" in out  # 出链
        assert "meetings/notes/20260907-it-alignment" in out  # 入链
        two = index.neighbours("meetings/notes/20260907-it-alignment", hops=2)
        assert "hii/notes/20260912-trademark-consensus" in two
