"""自助入库路线端到端：模板 → 合法页面 → 过 schema → 建索引 → **问一句能召回**。

承诺来源：`docs/product/INTAKE-GUIDE.html` 与 `_vault/index/sop.md` 的「入口指南」告诉使用者
「复制模板 → 改 3 处 → 保存，**下一次提问就能检索到**」。在使用者选择「自己在
Workbench / Obsidian 里操作」之后，这条链就是他的主路径。

在它之前，这条路只有「模板插入即合法」一环有守卫（`scripts/kb_check_templates.py`），
**整条链仍属于"我验证过一次"**。本用例把两件事变成可重复验证（零 token、不调模型）：

1. 用仓库自带的种子模板渲染出的页面，必须**通过 `check_vault`**（否则使用者建完就红）；
2. 写进 vault 的新页面必须能被**建索引并检索到**——对应「``index.build()`` 在问答路径里
   做增量同步、所以写完不必手动重建」。

变异验证：
- 把 `templates/vault/*.template.md` 里任一 `{{…}}` 的引号去掉 → 第 1 组断言变红；
- 把 `_SKIP_DIRS` 移除 `templates` 或让索引跳过新文件 → 第 2 组断言变红。
"""

from __future__ import annotations

import re
from pathlib import Path

from summit_workbench.repositories.kb_index import KnowledgeIndex
from summit_workbench.repositories.vault import check_vault, parse_frontmatter
from summit_workbench.workflows.ask.retrieval import build_index
from summit_workbench.workflows.onboarding import default_vault_templates_dir

DAY = "2026-09-14"
# 一个在任何模板里都不存在的短语，用来证明「新页面能被检索到」而不是命中别的内容。
TOKEN = "独角兽紫水晶入库验证标记"

# 种子模板 → 它在真实工作台里的落点。集合必须与 `templates/vault/` 完全一致：
# 新增种子模板却没在这里登记时，本用例会直接失败（避免"加了模板没人验"）。
_SEED_TARGETS: dict[str, str] = {
    "conventions.template.md": "conventions.md",
    "inbox.template.md": "inbox.md",
    "review-meetings.template.md": "review/meetings.md",
    "meeting-note.template.md": "meetings/notes/20260914-sample.md",
    "meeting-transcript.template.md": "meetings/transcripts/2026-09-14-sample-transcript.md",
    "project-main.template.md": "projects/sample.md",
    "workstream.template.md": "hii/hii-sample.md",
    "note.template.md": "hr/notes/20260914-sample.md",
    "decision.template.md": "decisions/20260914-sample.md",
    "source.template.md": "hr/sources/20260914-sample.md",
    "index.template.md": "index/projects.md",
    "long-form-thought.template.md": "community/thinking/sample.md",
    "work-log.template.md": "hr/logs/20260914.md",
}

_AUTO = {"{{date}}": DAY, "{{time}}": "12:00", "{{title}}": "样例标题"}


def _render(template_text: str) -> str:
    """模拟 Obsidian 插入模板后，人把剩下的占位符都填成合法值。"""
    text = template_text
    for key, value in _AUTO.items():
        text = text.replace(key, value)
    return re.sub(r"\{\{[^{}]*\}\}", "sample", text)


def _write(vault: Path, rel: str, text: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_project(vault: Path) -> None:
    _write(
        vault,
        "projects/hr.md",
        f"""---
date: {DAY}
type: project-main
status: active
project: hr
---

# 公司人事

## 当前状态

x

## 下一步

x

## 阻塞

x

## 决策记录

x
""",
    )


def test_seed_template_set_is_fully_covered() -> None:
    """`templates/vault/` 里每个种子模板都必须在 `_SEED_TARGETS` 里登记落点。"""
    names = {p.name for p in default_vault_templates_dir().glob("*.template.md")}
    assert names == set(_SEED_TARGETS), {
        "未登记落点": sorted(names - set(_SEED_TARGETS)),
        "已登记但文件不存在": sorted(set(_SEED_TARGETS) - names),
    }


def test_seed_templates_parse_even_with_placeholders_left() -> None:
    """第 0 组（原始缺陷的直接守卫）：模板**留着占位符**也必须能被 YAML 解析。

    为什么单独一条：上面两组都在"占位符已填"的前提下验证，因此抓不到 2026-09-14 发现的那个
    原始缺陷——frontmatter 里未加引号的 ``{{meeting_id}}`` / ``{{project}}`` 是**非法 YAML 映射**，
    使用者一插入模板、还没填任何东西时就已经是一份解析不了的页面。
    本组只做 Obsidian 的自动替换，其余占位符原样保留，要求 ``parse_frontmatter`` 不报错。

    变异验证：把任一模板里的 ``"{{…}}"`` 引号去掉 → 本用例立刻变红。
    """
    templates_dir = default_vault_templates_dir()
    broken: dict[str, str] = {}
    for path in sorted(templates_dir.glob("*.template.md")):
        text = path.read_text(encoding="utf-8")
        for key, value in _AUTO.items():
            text = text.replace(key, value)
        _meta, _body, error = parse_frontmatter(text)
        if error is not None:
            broken[path.name] = str(error).splitlines()[0]
    assert broken == {}, f"这些种子模板留着占位符就解析失败：{broken}"


def test_rendered_templates_pass_vault_check(tmp_path: Path) -> None:
    """第 1 组：模板渲染成真实页面后必须通过 `check_vault`。"""
    vault = tmp_path / "vault"
    _make_project(vault)
    templates_dir = default_vault_templates_dir()

    written: list[Path] = []
    for name, rel in _SEED_TARGETS.items():
        text = _render((templates_dir / name).read_text(encoding="utf-8"))
        written.append(_write(vault, rel, text))

    results = check_vault(vault)
    offenders = {
        path: [str(i) for i in issues] for path, issues in results.items() if path in written
    }
    assert offenders == {}, f"以下页面由种子模板渲染而来却过不了校验：{offenders}"


def test_new_note_is_retrievable_after_index_build(tmp_path: Path) -> None:
    """第 2 组：写进 vault 的新页面必须能被检索到（＝「下一次提问就能检索到」）。"""
    vault = tmp_path / "vault"
    _make_project(vault)
    templates_dir = default_vault_templates_dir()

    text = _render((templates_dir / "note.template.md").read_text(encoding="utf-8"))
    # `draft` 不进索引——要验证"能被检索到"，这里必须是 active（模板默认值另有断言）。
    text = text.replace("status: draft", "status: active")
    rel = "hr/notes/20260914-sample.md"
    _write(vault, rel, text + f"\n## 入库验证\n\n{TOKEN}。\n")

    index_path = tmp_path / "kb.sqlite"
    build_index(vault, index_path)

    with KnowledgeIndex(vault, index_path) as index:
        hits = index.search(TOKEN)

    assert hits, "新写入的页面没有被索引检索到——「写完即可检索」的承诺不成立"
    assert any(hit.source_id == "hr/notes/20260914-sample" for hit in hits), [
        hit.source_id for hit in hits
    ]


def test_draft_pages_stay_out_of_the_index(tmp_path: Path) -> None:
    """反向断言：`draft` 页面**不该**被检索到（这正是指南要求「想被引用就用 active」的原因）。"""
    vault = tmp_path / "vault"
    _make_project(vault)
    _write(
        vault,
        "hr/notes/20260914-draft.md",
        f"""---
date: {DAY}
type: note
status: draft
---

# 草稿

## 结论一｜{TOKEN}
""",
    )

    index_path = tmp_path / "kb.sqlite"
    build_index(vault, index_path)

    with KnowledgeIndex(vault, index_path) as index:
        hits = index.search(TOKEN)

    assert not hits, "draft 页面不应进入检索索引"
