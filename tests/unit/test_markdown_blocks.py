"""Markdown block splitting semantics shared by retrieval and approval sources."""

from summit_workbench.domain.markdown_blocks import chunk_markdown

BODY = """# 标题

前言段落。

## 第一个区块

内容一。

## 第二个区块

内容二。

```
## 代码里的井号不是标题
```

## 第一个区块

重复标题的内容。

### 三级标题不算块边界
"""


def test_leading_h1_is_the_note_title_not_a_block() -> None:
    chunks = chunk_markdown("hii/notes/foo", BODY)
    assert [chunk.heading for chunk in chunks] == ["", "第一个区块", "第二个区块", "第一个区块 2"]
    assert chunks[0].anchor == "hii/notes/foo"
    assert "# 标题" in chunks[0].text


def test_level_one_heading_is_a_block_boundary() -> None:
    body = (
        "# 原文：全景总结\n"
        "\n## 原文（逐字，未改写）\n"
        "\n# 六、正式名称\n\n正文甲。\n"
        "\n## 6.1 登记主体\n\n正文乙。\n"
        "\n# 七、落地事项\n\n正文丙。\n"
    )
    chunks = chunk_markdown("hii/sources/overview", body)
    assert [chunk.heading for chunk in chunks] == [
        "",
        "原文（逐字，未改写）",
        "六、正式名称",
        "6.1 登记主体",
        "七、落地事项",
    ]
    assert chunks[2].anchor == "hii/sources/overview#六、正式名称"
    assert chunks[4].anchor == "hii/sources/overview#七、落地事项"
    assert "正文丙" in chunks[4].text


def test_text_before_first_heading_is_a_preamble_chunk() -> None:
    chunks = chunk_markdown("a/b", "前言段落。\n\n## 第一个区块\n\n内容。\n")
    assert [chunk.heading for chunk in chunks] == ["", "第一个区块"]
    assert chunks[0].anchor == "a/b"
    assert chunks[1].anchor == "a/b#第一个区块"


def test_fenced_code_block_does_not_split() -> None:
    body = "# t\n\n## 真区块\n\n```\n## 假区块\n```\n\n```\n# 假一级标题\n```\n\n尾部。\n"
    chunks = chunk_markdown("a/b", body)
    assert [chunk.heading for chunk in chunks] == ["", "真区块"]
    assert "## 假区块" in chunks[1].text
    assert "# 假一级标题" in chunks[1].text


def test_third_level_heading_stays_inside_its_block() -> None:
    duplicate = next(
        chunk for chunk in chunk_markdown("hii/notes/foo", BODY) if chunk.heading == "第一个区块 2"
    )
    assert "### 三级标题不算块边界" in duplicate.text


def test_empty_body_yields_no_chunks() -> None:
    assert chunk_markdown("a/b", "   \n") == []
