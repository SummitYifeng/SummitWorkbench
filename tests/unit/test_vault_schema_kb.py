"""工作知识库新增 type / scope 的校验规则测试（纯加法，不得改变既有类型行为）。

每个新增 type 一例；``free`` scope 覆盖「绑定单项目 / 绑定多项目 / 都不绑定 / 同时出现」四种
形态，其中最后一种是反例——它是 ``free`` 唯一的硬不变量，必须能被判出来（变异验证：把
``_check_project_scope`` 里的 free 分支删掉，本文件必须变红）。
"""

from __future__ import annotations

from summit_workbench.domain.vault import NOTE_TYPES, validate_note

WORKSTREAM_BODY = "\n".join(
    [
        "## 现在在哪",
        "## 关键结论",
        "## 未决问题",
        "## 决策记录",
        "## 时间线",
        "## 关联",
    ]
)
DECISION_BODY = "\n".join(["## 背景", "## 选项", "## 决定", "## 理由", "## 影响", "## 证据"])
SOURCE_BODY = "\n".join(["## 来源", "## 要点", "## 关联"])
THOUGHT_BODY = "\n".join(["## 问题缘起", "## 思考展开", "## 当前结论"])


def _base(note_type: str, **extra: object) -> dict[str, object]:
    meta: dict[str, object] = {"date": "2026-09-13", "type": note_type, "status": "active"}
    meta.update(extra)
    return meta


# ---- 1. 新增 type 全部被认作已知类型 ----


def test_new_types_are_known():
    for name in ("workstream", "note", "decision", "source", "index", "long-form-thought"):
        assert name in NOTE_TYPES


# ---- 2. 每型一个通过例 ----


def test_workstream_page_passes():
    assert validate_note(_base("workstream", project="global"), WORKSTREAM_BODY) == []


def test_plain_note_passes_without_project_binding():
    # 工作线层面的笔记：不绑定任何项目也必须合法。
    assert validate_note(_base("note"), "# 商标共识规范\n\n正文。\n") == []


def test_decision_passes():
    assert validate_note(_base("decision", projects=["hii-ip-trademark"]), DECISION_BODY) == []


def test_source_passes():
    assert validate_note(_base("source", project="global"), SOURCE_BODY) == []


def test_index_page_passes():
    assert validate_note(_base("index", project="global"), "# 项目索引\n") == []


def test_long_form_thought_passes():
    assert validate_note(_base("long-form-thought"), THOUGHT_BODY) == []


# ---- 3. 固定区块缺失必须报出来（每型可判定的失败模式） ----


def test_decision_missing_block_is_reported():
    msgs = " ".join(str(i) for i in validate_note(_base("decision"), "## 背景\n"))
    for block in ("选项", "决定", "理由", "影响", "证据"):
        assert block in msgs


def test_source_missing_block_is_reported():
    msgs = " ".join(
        str(i) for i in validate_note(_base("source", project="global"), "# 只有标题\n")
    )
    assert "来源" in msgs and "要点" in msgs and "关联" in msgs


def test_workstream_missing_block_is_reported():
    msgs = " ".join(
        str(i) for i in validate_note(_base("workstream", project="global"), "## 现在在哪\n")
    )
    for block in ("关键结论", "未决问题", "决策记录", "时间线", "关联"):
        assert block in msgs


# ---- 4. free scope：四种形态 ----


def test_free_scope_allows_single_project():
    assert validate_note(_base("note", project="hii-loyalty"), "# t\n") == []


def test_free_scope_allows_multiple_projects():
    assert validate_note(_base("note", projects=["a", "b"]), "# t\n") == []


def test_free_scope_allows_neither():
    assert validate_note(_base("note"), "# t\n") == []


def test_free_scope_rejects_both_project_and_projects():
    issues = validate_note(_base("note", project="a", projects=["b"]), "# t\n")
    assert any(i.field == "projects" for i in issues), issues


def test_free_scope_rejects_non_list_projects():
    issues = validate_note(_base("note", projects="a,b"), "# t\n")
    assert any(i.field == "projects" for i in issues), issues


# ---- 5. 既有类型行为未被改变（回归护栏） ----


def test_existing_global_scope_still_rejects_non_global():
    assert any(
        i.field == "project"
        for i in validate_note(
            {"project": "P", "date": "2026-09-13", "type": "inbox", "status": "active"}, ""
        )
    )


def test_existing_single_scope_still_requires_project():
    body = "## 当前状态\n## 下一步\n## 阻塞\n## 决策记录\n"
    assert any(
        i.field == "project"
        for i in validate_note(
            {"date": "2026-09-13", "type": "project-main", "status": "active"}, body
        )
    )
