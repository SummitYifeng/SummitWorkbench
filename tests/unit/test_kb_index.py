"""索引层测试：构建/增量/全量、FTS5 与 BM25 两条分支、别名解析、双链扩展、位置约束。

变异验证（每条都对应一个「改坏了就会红」的断言）：
- 去掉 `_EXCLUDED_STATUS` → `draft` 笔记会进索引（本文件会红）；
- 去掉 `_prune` → 删除笔记后索引里仍有陈旧块；
- 去掉 `neighbours` 的入链分支 → 反向双链解析不到；
- 把 `default_index_path` 指回 vault → 位置约束断言失败。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import cast

import pytest

from summit_workbench.repositories import kb_index as kb
from summit_workbench.repositories.kb_index import (
    IndexUnavailableError,
    KnowledgeIndex,
    bm25_scores,
    default_index_path,
    fts5_available,
)
from summit_workbench.workflows.ask.retrieval import retrieve_candidates, retrieve_via_index


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
        # R2：关键词出现在**一级标题**里 → 一级标题也是块边界，命中的是那一块，
        # 锚点从「笔记本身」变成「笔记#一级标题」（Obsidian 的 [[文件#标题]] 同样不区分级别）。
        # 只有首个标题**之前**的正文才是「前言块」（锚点＝笔记本身），见
        # tests/unit/test_ask_chunking_terms_router.py 的
        # test_text_before_first_heading_is_a_preamble_chunk
        title_hits = index.search("商标共识规范")
        assert title_hits, "FTS5 应能命中中文子串"
        assert "hii/notes/20260912-trademark-consensus#HII–HIC 商标共识规范" in {
            hit.anchor for hit in title_hits
        }

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


# ---- 索引库损坏 / 不可用：三种真实失败形态都必须自愈或优雅降级 ----
#
# 这一组对应使用者 2026-09-13 实测的线上缺陷：索引文件被写坏时 `wb ask` 直接抛
# `sqlite3.DatabaseError: file is not a database`，而模块文档承诺的是「退化为纯 Python BM25」。
# 三条断言分别锁住：垃圾文件自愈、只读目录降级、旧表结构自愈。


def test_corrupt_index_file_is_rebuilt_and_ask_still_works(vault: Path, tmp_path: Path) -> None:
    """索引文件是垃圾内容时：删掉重建，问答不崩（这是本轮修的真实缺陷）。"""
    target = tmp_path / "kb.sqlite"
    target.write_bytes(b"this is definitely not a sqlite database" * 32)

    with KnowledgeIndex(vault, target) as index:
        stats = index.build()
        assert stats.added == 4
        assert index.chunk_count() > 0
    # 文件已被换成真正的库，而不是继续拿着垃圾文件
    assert target.read_bytes()[:16] == b"SQLite format 3\x00"


def test_corrupt_index_does_not_raise_out_of_retrieve_via_index(
    vault: Path, tmp_path: Path
) -> None:
    """端到端：坏索引库绝不能把 sqlite3 的栈抛给 `wb ask`。"""
    target = tmp_path / "kb.sqlite"
    target.write_bytes(b"\x00\x01\x02 not a database" * 64)
    candidates, trace = retrieve_via_index(vault, "商标共识规范", index_path=target)
    assert candidates, "坏索引库之后仍须能召回（重建后的索引或降级扫描）"
    assert trace.degraded == ""  # 自愈成功，没有降级


def test_readonly_directory_degrades_to_substring_scan(vault: Path, tmp_path: Path) -> None:
    """目录只读、索引库建不出来：抛 IndexUnavailableError，检索退回纯 Markdown 扫描。"""
    if os.geteuid() == 0:  # root 无视目录权限，这条断言在本机无意义
        pytest.skip("以 root 运行时目录权限不生效")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    target = locked / "kb.sqlite"
    try:
        with pytest.raises(IndexUnavailableError):
            KnowledgeIndex(vault, target)

        expected = retrieve_candidates(vault, "商标共识规范")
        assert expected, "前置条件：子串扫描本身要有命中"
        candidates, trace = retrieve_via_index(vault, "商标共识规范", index_path=target)
        assert [c.source_id for c in candidates] == [c.source_id for c in expected]
        assert trace.degraded, "降级必须在检索轨迹里写明原因，否则使用者以为这是块级检索"
        assert "索引库打不开" in trace.degraded
    finally:
        locked.chmod(0o700)


def test_mismatched_table_schema_is_rebuilt(vault: Path, tmp_path: Path) -> None:
    """旧版本残留 / 被手工改坏的表结构：`CREATE TABLE IF NOT EXISTS` 修不了，必须删表重建。"""
    target = tmp_path / "kb.sqlite"
    stale = sqlite3.connect(target)
    stale.executescript(
        "CREATE TABLE notes (source_id TEXT PRIMARY KEY, title TEXT);"
        " CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_id TEXT);"
    )
    stale.commit()
    stale.close()

    with KnowledgeIndex(vault, target) as index:
        stats = index.build()  # 旧表少了 hash/meta_json 等列，不自愈这里就会 OperationalError
        assert stats.added == 4
        assert index.notes()["hii/notes/20260912-trademark-consensus"].workstream == "hii"
        assert index.search("商标共识规范") is not None or not fts5_available()


def test_broken_fts_shadow_table_falls_back_to_bm25(vault: Path, tmp_path: Path) -> None:
    """内容表还在但 FTS 影子表坏了：本会话退化为 BM25，而不是让检索失败。"""
    target = tmp_path / "kb.sqlite"
    with KnowledgeIndex(vault, target) as index:
        index.build()

    broken = sqlite3.connect(target)
    broken.executescript("DROP TABLE IF EXISTS chunks_fts;")
    broken.commit()
    broken.close()

    with KnowledgeIndex(vault, target) as index:
        index.build()
        if fts5_available():
            # 影子表被丢弃后 _prepare_schema 会重建它；要么重建成功（返回命中），
            # 要么明确告知上层走兜底（None）——两者都不能抛异常。
            hits = index.search("商标共识规范")
            assert hits is None or hits
        else:  # pragma: no cover - 本机 FTS5 可用
            assert index.search("商标共识规范") is None


def test_runtime_diagnostic_proves_both_paths_in_this_interpreter() -> None:
    """包内探针的判定逻辑：FTS5 可用与否都要证明块级检索活着，且兜底分支真的被执行到。

    这个函数就是 `SummitWorkbenchServer --kb-diagnostic` 的实现，因此它的语义必须有单测：
    只打印「FTS5 可用」不足以证明「FTS5 不可用时还能用」。
    """
    report = kb.runtime_diagnostic()
    assert report["sqlite_version"]
    assert report["chunk_level_ok"] is True
    assert report["bm25_fallback_ok"] is True
    assert report["forced_no_fts_search_is_none"] is True
    # runtime_diagnostic 返回 dict[str, object]（要 JSON 序列化），取列表时显式收窄
    forced = cast(list[str], report["forced_no_fts_bm25_hit"])
    assert any("#" in anchor for anchor in forced)
    if report["fts5_trigram"]:
        fts_hits = cast(list[str], report["fts_hit"])
        assert any("#" in anchor for anchor in fts_hits)
    else:  # pragma: no cover - 本机 FTS5 可用
        assert report["fts_hit"] is None
