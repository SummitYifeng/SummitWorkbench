"""`scripts/kb_index_people.py`：人员/组织索引页的聚合与再生成。

为什么需要它：`index/people.md` 在自己正文里写着「由聚合脚本重生成，不需要手工维护条目」，
但那个脚本当时写在 `/tmp`，没进仓库——页面因此不可复现。这些断言锁住三件事：

- **排序**：条目数降序、同数按名字升序（与已发布的页面一致）；
- **预览**：只列前 4 篇，超过就补 `（共 N 篇）`；
- **`--check`**：页面与 frontmatter 不一致时必须非零退出（否则「可脚本再生成」是空话）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    """按**源码**执行脚本，绕过 `__pycache__`。

    `spec.loader.exec_module` 走字节码缓存，而 pyc 头里的源 mtime 只有 1 秒粒度——
    同秒内等长改动会命中过期 pyc，让变异验证得出错误结论（2026-09-19 实测踩到）。
    """
    path = ROOT / "scripts" / f"{name}.py"
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


people_index = _load("kb_index_people")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "_vault"
    vault.mkdir(parents=True)
    (vault / "conventions.md").write_text("# 规范\n", encoding="utf-8")
    return vault


def _note(vault: Path, rel: str, people: str = "[]", org: str = "[]") -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndate: 2026-09-13\ntype: note\nstatus: active\n"
        f"people: {people}\norg: {org}\n---\n\n# {path.stem}\n",
        encoding="utf-8",
    )


def test_orders_by_count_then_name_and_collapses_the_tail(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    for stem in ("a", "b", "c", "d", "e"):
        _note(vault, f"n/{stem}.md", people="[甲]")
    for stem in ("a", "b", "c"):
        _note(vault, f"m/{stem}.md", people="[乙]")
    _note(vault, "z/alone.md", people="[丙]")

    people, orgs = people_index.collect(vault)
    assert people_index._ranked(people) == ["甲", "乙", "丙"]

    rendered = people_index.render(people, orgs, created="2026-09-13", updated="2026-09-13")
    assert "- **甲**：[[a|a]]、[[b|b]]、[[c|c]]、[[d|d]]（共 5 篇）" in rendered
    assert "- **乙**：[[a|a]]、[[b|b]]、[[c|c]]" in rendered  # 恰好 4 篇：不补「共 N 篇」
    assert "- **丙**：[[alone|alone]]" in rendered


def test_templates_and_machine_dirs_are_excluded(tmp_path: Path) -> None:
    """模板与机器目录不是知识，不能进索引页（否则模板里的示例人名会变成真人）。"""
    vault = _vault(tmp_path)
    _note(vault, "n/real.md", people="[甲]")
    _note(vault, "templates/note.template.md", people="[模板示例人]")
    _note(vault, "_signals/x.md", people="[机器信号]")
    _note(vault, ".summit-workbench/y.md", people="[内部状态]")

    people, _orgs = people_index.collect(vault)
    assert set(people) == {"甲"}


def test_check_flags_a_stale_page_and_passes_once_regenerated(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    _note(vault, "n/a.md", people="[甲]", org="[HII]")
    target = vault / "index" / "people.md"

    # 页面还不存在 → --check 必须红
    stale = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "kb_index_people.py"),
            "--vault",
            str(vault),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert stale.returncode == 1

    written = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "kb_index_people.py"), "--vault", str(vault)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert written.returncode == 0, written.stderr
    assert "- **甲**：[[a|a]]" in target.read_text(encoding="utf-8")

    fresh = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "kb_index_people.py"),
            "--vault",
            str(vault),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr

    # frontmatter 变了但页面没重生成 → 必须再红（这条才是「可再生成」的真正含义）
    _note(vault, "n/b.md", people="[甲]")
    again = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "kb_index_people.py"),
            "--vault",
            str(vault),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode == 1
    assert "已过期" in again.stderr


def test_write_keeps_the_pages_existing_frontmatter(tmp_path: Path) -> None:
    """回归：写入时不得用自己的最小 frontmatter 覆盖页面已有字段。

    `render()` 自带的 frontmatter 只有 date/type/status/project/updated/title/aliases；
    直接写盘会把新规范要求的 `id` / `area` / `workstream` / `summary` 整段抹掉
    （2026-09-14 实测发现）。写入必须保留既有 frontmatter、只替换正文。
    """
    vault = _vault(tmp_path)
    _note(vault, "n/a.md", people="[甲]")
    target = vault / "index" / "people.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nid: 2026-09-14-c022\ntitle: 人物与组织索引\narea: work\nworkstream: cross\n"
        "project: global\ntype: index\ndomain: system\nstatus: active\n"
        "updated: 2026-09-14\ndate: 2026-09-14\nsummary: 由 frontmatter 聚合。\n---\n\n"
        "# 人物与组织索引\n\n## 人物\n\n_（待回填）_\n\n## 组织\n\n## 维护规则\n\n- 手工规则\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "kb_index_people.py"), "--vault", str(vault)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = target.read_text(encoding="utf-8")
    for needle in (
        "id: 2026-09-14-c022",
        "area: work",
        "workstream: cross",
        "summary: 由 frontmatter 聚合。",
    ):
        assert needle in text, f"写入把既有 frontmatter 抹掉了：缺 {needle}"
    assert "- **甲**：[[a|a]]" in text


def test_refuses_a_directory_that_is_not_a_work_vault(tmp_path: Path) -> None:
    """给错目录时必须拒绝，而不是在任意目录下写一个 people.md。"""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "kb_index_people.py"), "--vault", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not (tmp_path / "index" / "people.md").exists()


def test_accepts_work_root_or_vault_path(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    _note(vault, "n/a.md", people="[甲]")
    for supplied in (tmp_path, vault):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "kb_index_people.py"),
                "--vault",
                str(supplied),
                "--check",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
