"""T2：自动产物结构规范化 —— 逐字保留、文首 H1 去重、H2/H3 不被展平、失败即拒绝。"""

from __future__ import annotations

import ast
from pathlib import Path

from summit_workbench.domain.knowledge_normalization import (
    format_normalization_error as domain_format_normalization_error,
)
from summit_workbench.domain.knowledge_normalization import (
    normalize_generated_body as domain_normalize_generated_body,
)
from summit_workbench.domain.retrieval_contract import validate_retrieval_readiness
from summit_workbench.domain.vault import iter_headings
from summit_workbench.workflows.knowledge_normalization import (
    format_normalization_error,
    normalize_generated_body,
)


def _h1s(body: str) -> list[str]:
    return [text for level, text in iter_headings(body) if level == 1]


def test_verbatim_text_is_preserved() -> None:
    text = "第一行含 [[双链]] 与 #不是标题\n\n第二段：1500/次，月底前出 V1.1。"
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text=text, project_links=["P1"]
    )
    assert out.issues == ()
    assert text in out.body


def test_leading_h1_is_deduplicated_against_title() -> None:
    text = "# 阶段性总结\n\n（很长）…"
    out = normalize_generated_body(
        note_type="thread-doc", title="Finance Ops 阶段总结 V2", text=text, project_links=["P1"]
    )
    assert out.issues == ()
    assert _h1s(out.body) == ["Finance Ops 阶段总结 V2"]  # 只有一个 H1
    assert "阶段性总结" not in out.body.split("\n", 1)[0]


def test_thread_doc_without_h2_gets_content_block() -> None:
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text="没有小标题的一段正文。", project_links=["P1"]
    )
    assert out.body.startswith("# T\n")
    assert "## 内容" in out.body
    assert "没有小标题的一段正文。" in out.body


def test_work_log_without_h2_gets_work_record_block() -> None:
    out = normalize_generated_body(
        note_type="work-log",
        title="2026-09-03 工作记录",
        text="今天和木子确认了 Coach 时间表。",
        project_links=["FinanceOps"],
    )
    assert out.body.startswith("# 2026-09-03 工作记录\n")
    assert "## 工作记录" in out.body
    assert "- [[projects/FinanceOps]]" in out.body


def test_existing_h2_structure_is_kept_and_h3_not_promoted() -> None:
    text = "## 背景\n\na\n\n### 细节\n\nb\n"
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text=text, project_links=["P1"]
    )
    assert "## 背景" in out.body
    assert "### 细节" in out.body  # H3 不被提升为 H2
    assert "## 内容" not in out.body  # 已有 H2，不额外套默认区块
    levels = [level for level, _ in iter_headings(out.body)]
    assert levels == [1, 2, 3, 2]  # H1 + 背景 + 细节 + 关联项目


def test_related_project_block_is_not_duplicated() -> None:
    text = "## 内容\n\n正文。\n\n## 关联项目\n\n- [[projects/P1]]\n"
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text=text, project_links=["P1"]
    )
    assert out.body.count("## 关联项目") == 1
    assert out.body.count("- [[projects/P1]]") == 1


def test_project_links_are_deduplicated() -> None:
    out = normalize_generated_body(
        note_type="work-log", title="T", text="x", project_links=["P1", "P1", "P2"]
    )
    assert out.body.count("- [[projects/P1]]") == 1
    assert out.body.count("- [[projects/P2]]") == 1


def test_duplicate_citable_heading_is_rejected_without_partial_body() -> None:
    text = "## 关键结论\n\na\n\n## 关键结论\n\nb\n"
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text=text, project_links=["P1"]
    )
    assert out.body == ""  # 不得返回半成品
    assert [issue.code for issue in out.issues] == ["duplicate-heading"]
    assert "关键结论" in format_normalization_error(out.issues)


def test_duplicate_leading_h1_in_input_is_rejected() -> None:
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text="# A\n\nx\n\n# A\n\ny\n", project_links=["P1"]
    )
    assert out.body == ""
    assert [issue.code for issue in out.issues] == ["duplicate-heading"]


def test_unbalanced_fence_is_rejected() -> None:
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text="## 区块\n\n```python\nprint(1)\n", project_links=[]
    )
    assert out.body == ""
    assert [issue.code for issue in out.issues] == ["invalid-fence"]


def test_empty_text_or_title_is_rejected() -> None:
    assert [
        i.code
        for i in normalize_generated_body(
            note_type="thread-doc", title="T", text="  ", project_links=[]
        ).issues
    ] == ["empty-body"]
    assert [
        i.code
        for i in normalize_generated_body(
            note_type="thread-doc", title=" ", text="x", project_links=[]
        ).issues
    ] == ["missing-title"]


def test_normalized_thread_doc_is_retrieval_ready() -> None:
    out = normalize_generated_body(
        note_type="thread-doc", title="T", text="一段正文。", project_links=["P1"]
    )
    meta = {"date": "2026-09-14", "type": "thread-doc", "status": "generated", "project": "P1"}
    assert validate_retrieval_readiness(meta, out.body) == []


def test_workflow_compatibility_module_reexports_domain_implementation() -> None:
    assert normalize_generated_body is domain_normalize_generated_body
    assert format_normalization_error is domain_format_normalization_error

    expected = normalize_generated_body(
        note_type="thread-doc",
        title="固定样例",
        text="# 重复标题\n\n## 结论\n\n保留原文。",
        project_links=["p1"],
    )
    actual = domain_normalize_generated_body(
        note_type="thread-doc",
        title="固定样例",
        text="# 重复标题\n\n## 结论\n\n保留原文。",
        project_links=["p1"],
    )
    assert expected == actual


def test_repositories_do_not_runtime_import_workflows() -> None:
    root = Path(__file__).parents[2] / "src" / "summit_workbench" / "repositories"
    violations: list[str] = []

    def visit(node: ast.AST, *, in_type_checking: bool = False) -> None:
        if isinstance(node, ast.If):
            is_type_checking = isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
            for child in node.body:
                visit(child, in_type_checking=in_type_checking or is_type_checking)
            for child in node.orelse:
                visit(child, in_type_checking=in_type_checking)
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)) and not in_type_checking:
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(module.startswith("summit_workbench.workflows") for module in modules):
                violations.append(f"{node.lineno}: {modules}")
        for child_node in ast.iter_child_nodes(node):
            visit(child_node, in_type_checking=in_type_checking)

    for path in sorted(root.glob("*.py")):
        visit(ast.parse(path.read_text(encoding="utf-8")))

    assert violations == []
