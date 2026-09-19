#!/usr/bin/env python3
"""工作库契约自检（只读）：`conventions.md` 声明的目录 / 类型 vs 库内实际。

存在理由：`_vault/conventions.md` 是工作库的规范单一真源，但它与库内实际内容是**两份**
东西——新增一个顶层目录、删掉一个项目页、把某个类型改掉，契约不会自动跟上。上一批
（2026-09-19 批次 A）已经出现过「`daily/` 与空 `reviews/` 还在库里、契约却已声明不在库内」
这类漂移，靠人工比对不可靠。第一阶段 vault agent 写过一个只读自检脚本，但只留在 `/tmp`，
会话一结束就丢了；本文件是它的版本化替代。

**判据分两层（这是本脚本的关键，不要合并）**：

- **FAIL = 契约错了 / 自相矛盾 / 与库内硬冲突**：例如契约声明的主线项目页集合与
  `projects/*.md` 对不上、契约明说已撤销的旧目录又出现在 §1 目录树里、契约声明"不在库内"
  的目录却在库里、库内页面的 `type` 不在契约词表里。
- **WARN = 契约已声明、但按需创建/库内还没有**：例如 `thinking/`（顶层目录待批次 B1 建立）、
  `long-form-thought` / `qa-insight` / `thread-doc` 等 0 篇类型。第一阶段正是靠这个区分
  才没有被误报挡住。

**数据来源（避免把历史沿革文字误当声明）**：

- 目录名：只取 §1「目录结构」代码块里的**顶层**条目（`├──` / `└──` 在行首）；
  契约里其它地方出现的 `hii/`、`clusters/` 等是「已撤销」的历史沿革，不是声明。
- 类型名：只取 §3 表格 `type` 列；§5.2 之类是检索侧分层，含 `prompt`/`workflow`/`standard`
  等 SWB 词表外的名字，不能当 vault schema 词表。

用法：

    ./.venv/bin/python scripts/kb_check_contract.py
    ./.venv/bin/python scripts/kb_check_contract.py --vault ~/Documents/Work/_vault

退出码：0 = 通过（允许 WARN）；1 = 有 FAIL；2 = vault 不存在 / 不是工作库。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from summit_workbench.domain.vault import NOTE_TYPES  # noqa: E402
from summit_workbench.repositories.vault import parse_frontmatter  # noqa: E402

DEFAULT_VAULT = Path("~/Documents/Work/_vault")
CONVENTIONS_NAME = "conventions.md"

# 不进契约目录一致性检查的项：机器目录 / 工具目录 / 版本控制（契约 §0.2 已声明它们
# 不进知识索引，是否在 §1 树里逐条列出不构成库内一致性判据）。
IGNORED_TOP_LEVEL = {".git", ".obsidian", ".DS_Store", "_signals", ".summit-workbench"}

# 契约 §1 显式声明"不在库内"的顶层目录：简报/周报自 2026-09-19 起写在本机程序目录。
# 它们若出现在库里 = 契约与库内硬冲突（旧 App 回写）→ FAIL。
NOT_IN_VAULT_DIRS = {"daily", "reviews"}

# 契约 §1/§14 显式声明"已撤销"的旧顶层目录：不得再出现在 §1 目录树里（自相矛盾）。
REVOKED_DIRS = {"hii", "it", "community", "hr", "logistics"}

# 契约 §3 声明"不在 vault 内"的类型（与上面的目录对应）。库内出现即 FAIL；
# 反过来，它们库内 0 篇是**符合契约**的，不算"按需创建"告警。
NOT_IN_VAULT_TYPES = {"daily", "weekly-review"}

# 契约 §1 硬规则例外②：每个主线项目目录随项目预建 notes/ 与 sources/。
PROJECT_SCAFFOLD_SUBDIRS = ("notes", "sources")

_TREE_TOP_LEVEL = re.compile(r"^[├└]── (.+)$")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  \033[32m✅\033[0m {label}" + (f" — {detail}" if detail else ""))

    def warn(self, label: str, detail: str = "") -> None:
        self.warnings.append(label)
        print(f"  \033[33m⚠️\033[0m  {label}" + (f" — {detail}" if detail else ""))

    def fail(self, label: str, detail: str = "") -> None:
        self.failures.append(label)
        print(f"  \033[31m❌\033[0m {label}" + (f" — {detail}" if detail else ""))


def _section(text: str, start: str, end: str) -> str:
    if start not in text:
        return ""
    tail = text.split(start, 1)[1]
    return tail.split(end, 1)[0] if end in tail else tail


def _tree_top_level_names(conventions: str) -> tuple[set[str], set[str]]:
    """§1 目录树的顶层条目 → (目录名集合, 占位符集合)。

    只看行首的 `├──` / `└──`（嵌套项前面有 `│`），所以不会把 `notes/`、`sources/`
    这些"项目目录内部"的项算成顶层目录。
    """
    section = _section(conventions, "## 1. 目录结构", "### 1.1")
    match = re.search(r"```(.*?)```", section, re.S)
    if match is None:
        return set(), set()
    dirs: set[str] = set()
    placeholders: set[str] = set()
    for line in match.group(1).splitlines():
        row = _TREE_TOP_LEVEL.match(line.strip())
        if row is None:
            continue
        # 行内 `# 注释` 不算条目；一行可能列多项（`artifacts/ insights/ inboxes/`）。
        for token in row.group(1).split("#", 1)[0].split():
            segment = token.strip().strip("/").split("/", 1)[0]
            if not segment:
                continue
            if segment.startswith("<") and segment.endswith(">"):
                placeholders.add(segment)
                continue
            if segment.endswith(".md") or segment.startswith("."):
                continue  # 文件与点文件（.gitignore 等）不参与目录一致性检查
            dirs.add(segment)
    return dirs, placeholders


def _section3(conventions: str) -> str:
    return _section(conventions, "## 3. `type` 与 scope", "> **本库不使用")


def _declared_project_ids(conventions: str) -> set[str]:
    for line in _section3(conventions).splitlines():
        if line.startswith("| `project-main`"):
            return set(re.findall(r"`([a-z0-9-]+)`", line)) - {"project-main"}
    return set()


def _declared_types(conventions: str) -> set[str]:
    """§3 表格 `type` 列的类型名（跳过表头行与 `|---|` 分隔行）。"""
    types: set[str] = set()
    body_started = False
    for line in _section3(conventions).splitlines():
        if line.startswith("|") and set(line) <= set("|-: "):
            body_started = True
            continue
        if not body_started:
            continue
        match = re.match(r"^\|\s*`([a-z0-9-]+)`\s*\|", line)
        if match:
            types.add(match.group(1))
    return types


def _iter_pages(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in vault.rglob("*.md")
        if not any(
            part in IGNORED_TOP_LEVEL or part == "templates"
            for part in path.relative_to(vault).parts
        )
    )


def _page_types(vault: Path) -> tuple[dict[str, int], list[str]]:
    """库内页面（排除 templates/ 与机器目录）的 type 计数与无法解析的文件。"""
    counts: dict[str, int] = {}
    broken: list[str] = []
    for path in _iter_pages(vault):
        meta, _body, error = parse_frontmatter(path.read_text(encoding="utf-8"))
        if error is not None or not isinstance(meta.get("type"), str):
            broken.append(str(path.relative_to(vault)))
            continue
        note_type = str(meta["type"]).strip()
        counts[note_type] = counts.get(note_type, 0) + 1
    return counts, broken


def check_contract(vault: Path) -> int:
    rep = Report()
    conventions_path = vault / CONVENTIONS_NAME
    if not conventions_path.is_file():
        print(f"✗ 不是工作库：{vault} 下没有 {CONVENTIONS_NAME}", file=sys.stderr)
        return 2
    conventions = conventions_path.read_text(encoding="utf-8")

    declared_dirs, placeholders = _tree_top_level_names(conventions)
    declared_projects = _declared_project_ids(conventions)
    declared_types = _declared_types(conventions)
    if not declared_dirs or not declared_projects or not declared_types:
        print("✗ 契约解析失败：§1 目录树 / §3 类型表为空（契约结构可能被改动）", file=sys.stderr)
        return 1

    actual_dirs = {p.name for p in vault.iterdir() if p.is_dir()}
    page_types, broken = _page_types(vault)
    project_pages = (
        {p.stem for p in (vault / "projects").glob("*.md")}
        if (vault / "projects").is_dir()
        else set()
    )

    print(f"vault ：{vault}")
    print(f"契约 ：{conventions_path}")
    print(
        f"声明 ：顶层目录 {len(declared_dirs)}"
        f"｜主线项目 {len(declared_projects)}｜类型 {len(declared_types)}"
    )

    # ── FAIL 组：契约错了 / 自相矛盾 / 与库内硬冲突 ──
    print("\n[FAIL 组] 契约与库内硬一致性")
    if broken:
        rep.fail("存在 frontmatter 无法解析的页面", f"{len(broken)} 篇：{broken[:5]}")
    else:
        rep.ok("全部页面 frontmatter 可解析", f"{sum(page_types.values())} 篇")

    revoked_in_tree = sorted(REVOKED_DIRS & declared_dirs)
    if revoked_in_tree:
        rep.fail("契约 §1 目录树仍列着已声明撤销的旧目录（自相矛盾）", str(revoked_in_tree))
    else:
        rep.ok("§1 目录树不含已撤销的旧目录")

    present_not_in_vault = sorted(NOT_IN_VAULT_DIRS & actual_dirs)
    if present_not_in_vault:
        rep.fail(
            "契约声明'不在库内'的目录却出现在库里",
            f"{present_not_in_vault}（旧 App 回写？契约 §1/§3）",
        )
    else:
        rep.ok("库内无 daily/ 与 reviews/（契约声明不在库内）")

    missing_pages = sorted(declared_projects - project_pages)
    extra_pages = sorted(project_pages - declared_projects)
    if missing_pages or extra_pages:
        rep.fail(
            "projects/*.md 与契约 §3 声明的主线项目集合不一致",
            f"库内缺少 {missing_pages}；契约未声明 {extra_pages}",
        )
    else:
        rep.ok("projects/*.md 与契约主线项目集合一致", f"{len(project_pages)} 页")

    unknown_types = sorted(set(page_types) - declared_types)
    if unknown_types:
        rep.fail(
            "库内出现契约 §3 未声明的 type",
            f"{unknown_types}（契约词表只做加法，需同步 §3 表格）",
        )
    else:
        rep.ok("库内全部 type 都在契约 §3 表格内", f"{sorted(page_types)}")

    unknown_to_swb = sorted(declared_types - set(NOTE_TYPES))
    if unknown_to_swb:
        rep.fail("契约 §3 声明的 type 不在 SWB 词表（契约词表真源漂移）", str(unknown_to_swb))
    else:
        rep.ok("契约 §3 全部 type 都在 SWB NOTE_TYPES 内")

    present_not_in_vault_types = sorted(t for t in NOT_IN_VAULT_TYPES if page_types.get(t))
    if present_not_in_vault_types:
        rep.fail(
            "契约声明'不在库内'的 type 却出现在库里",
            f"{present_not_in_vault_types}（旧 App 回写？）",
        )
    else:
        rep.ok("库内无 daily / weekly-review 类型页面（契约声明不在库内）")

    scaffold_bad: list[str] = []
    dir_bad: list[str] = []
    for pid in sorted(declared_projects):
        project_dir = vault / pid
        if not project_dir.is_dir():
            dir_bad.append(pid)
            continue
        absent = [sub for sub in PROJECT_SCAFFOLD_SUBDIRS if not (project_dir / sub).is_dir()]
        if absent:
            scaffold_bad.append(f"{pid}:{','.join(absent)}")
    if dir_bad:
        rep.fail("契约声明的项目目录在库内不存在（§13.4：不再有'只有项目页'的形态）", str(dir_bad))
    elif scaffold_bad:
        rep.fail("项目目录缺 notes/ 或 sources/ 脚手架（契约 §1 例外②）", str(scaffold_bad))
    else:
        rep.ok("每个项目目录都有 notes/ 与 sources/", f"{len(declared_projects)} 个项目")

    undeclared_dirs = sorted(actual_dirs - declared_dirs - declared_projects - IGNORED_TOP_LEVEL)
    if undeclared_dirs:
        rep.fail("库内顶层目录未在契约 §1 声明（契约落后于库）", str(undeclared_dirs))
    else:
        rep.ok("库内顶层目录都已在契约 §1 声明")

    # ── WARN 组：契约已声明、但按需创建 / 库内还没有 ──
    print("\n[WARN 组] 契约已声明但库内尚未出现（按需创建，不算失败）")
    absent_declared_dirs = sorted(declared_dirs - actual_dirs - IGNORED_TOP_LEVEL)
    if absent_declared_dirs:
        rep.warn("契约声明的顶层目录库内还没有", str(absent_declared_dirs))
    else:
        rep.ok("契约声明的顶层目录库内都已建立")

    empty_types = sorted(t for t in declared_types - NOT_IN_VAULT_TYPES if not page_types.get(t))
    if empty_types:
        rep.warn("契约声明的 type 库内 0 篇", str(empty_types))
    else:
        rep.ok("契约声明的每个 type 库内都有页面")
    if placeholders:
        rep.ok(
            "目录树占位符按项目展开", f"{sorted(placeholders)} → {len(declared_projects)} 个项目"
        )

    print("\n" + "=" * 72)
    if rep.failures:
        print(
            f"结果：\033[31mFAIL\033[0m —— {len(rep.failures)} 项失败，{len(rep.warnings)} 项告警"
        )
        for item in rep.failures:
            print(f"  ❌ {item}")
        print("=" * 72)
        return 1
    print(f"结果：\033[32mPASS\033[0m（{len(rep.warnings)} 项告警，见上）")
    print("=" * 72)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="工作库契约自检（只读）")
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"工作库路径（默认 {DEFAULT_VAULT}）",
    )
    args = parser.parse_args(argv)
    vault = args.vault.expanduser()
    if not vault.is_dir():
        print(f"✗ 工作库不存在：{vault}", file=sys.stderr)
        print("  提示：用 --vault <路径> 指定；默认路径是 ~/Documents/Work/_vault", file=sys.stderr)
        return 2
    return check_contract(vault)


if __name__ == "__main__":
    raise SystemExit(main())
