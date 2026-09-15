"""契约文档 ↔ 可执行校验：文档与代码不得漂移（契约 §10 的自检）。

为什么需要这一层：共享契约的价值在于「两侧对同一份文字达成一致」，而文档最容易悄悄落后于
代码——新增一个 `status`/`type`、改了引用定义，只要没人重读文档就无人发现。这里把文档里的
状态词表、类型清单、引用定义钉到代码常量上。

变异验证：

- 从 `STATUS_VOCAB` 加/删一个状态而文档 §3 表格没跟上 → `test_status_table_matches_code` 变红；
- 给 `NOTE_TYPES` 加一个类型而文档没命名它 → `test_every_note_type_is_named` 变红。
"""

from __future__ import annotations

import re
from pathlib import Path

from summit_workbench.domain.vault import NOTE_TYPES, STATUS_VOCAB

DOC = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "WORK-KB-RETRIEVAL-CONTRACT.md"


def _doc() -> str:
    assert DOC.is_file(), f"契约文档不存在：{DOC}"
    return DOC.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    assert start in text, f"契约文档缺少小节：{start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def test_shared_reference_contract_is_documented_verbatim() -> None:
    """§2 的三行引用定义是两侧共用的接口，必须逐字一致（仅忽略排版空白）。"""
    section = _section(_doc(), "## 2. 共享引用契约", "## 3.")
    flattened = re.sub(r"\s+", " ", section)
    for line in (
        "source_id = 相对当前知识库根目录的 POSIX 路径，不含 .md",
        "heading = Markdown 标题文字，不含 # 前缀",
        "anchor = heading 非空时为 source_id#heading，否则为 source_id",
    ):
        assert re.sub(r"\s+", " ", line) in flattened, f"引用契约缺少：{line}"


def test_status_table_matches_code() -> None:
    """§3 状态表必须正好覆盖 `STATUS_VOCAB`（不多不少）。"""
    section = _section(_doc(), "## 3. 状态语义", "## 4.")
    documented = set(re.findall(r"^\|\s*`([a-z-]+)`\s*\|", section, re.MULTILINE))
    assert documented == set(STATUS_VOCAB)


def test_every_note_type_is_named() -> None:
    """`NOTE_TYPES` 里每个类型都必须在文档里被点名（新增类型必须同步文档）。"""
    text = _doc()
    missing = [note_type for note_type in NOTE_TYPES if f"`{note_type}`" not in text]
    assert missing == [], f"契约文档没有登记这些类型：{missing}"


def test_archived_and_superseded_are_distinguished() -> None:
    """`archived` ≠ `superseded` 是契约里最容易被解释错的一条，必须写成明文。"""
    assert "`archived` ≠ `superseded`" in _doc()


def test_authority_order_lists_the_four_tiers() -> None:
    section = _section(_doc(), "## 6. 工作库权威顺序", "## 7.")
    assert "证据层" in section
    assert "当前项目主页" in section
    # 权威度只能在语义相关候选内调整——这条约束必须留在文档里
    assert "不得让无关" in section
