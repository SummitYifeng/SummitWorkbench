"""工作 vault 的稳定 schema 与校验规则（PRD 3.1.5 / 3.1.9）。

这些规则是「为未来 SummitKnowledge 接入付出的兼容成本」的落点：统一 frontmatter、
固定区块、项目关联字段。纯逻辑，不读文件——由 repositories 层解析后调用本模块。
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import PurePath

# 所有笔记必须包含的 frontmatter 字段（PRD 3.1.5）。
REQUIRED_FRONTMATTER = ("date", "type", "status")

# 状态词表：并集自 MyKnowledge 规范与本产品的会议/问答状态机。
STATUS_VOCAB = frozenset(
    {
        "active",
        "paused",
        "archived",
        "draft",
        "superseded",
        "pending-review",
        "generated",
        "applied",
        "ignored",
    }
)

WORKSTREAM_VOCAB = frozenset({"hii", "it", "community", "logistics", "docs", "company", "cross"})

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 项目 ID 字符集：**唯一真源**（`repositories/project_registry.py` 复用本常量）。
# 注意它只在**创建项目**时强制（`wb project new`），schema 层**不**据此判定页面：
#
# 2026-09-14 踩坑记录：曾把字符集校验加进 `validate_note`，结果两条既有测试立刻变红——
# 会议提取管线里，模型给出的 `projects:` 允许是**自然语言项目名**（例如 `网课系统`），
# 之后才按别名解析成规范 ID；解析不到则落 `unresolved` → 全局收件箱。也就是说
# `meeting-note` / `meeting-transcript` 的 `projects:` 是**线索**而不是最终绑定，
# 在 schema 层按字符集判定会**打断会议导入**。⇒ 字符集约束保留为"创建时 + 约定"，不在此处强制。
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 未替换的模板占位符（Obsidian 只会替换 {{date}}/{{time}}/{{title}}，其余要人填）。
_PLACEHOLDER_MARKERS = ("{{", "}}")


@dataclass(frozen=True)
class NoteTypeSpec:
    """一种笔记类型的约束。

    scope:
      - ``single``：绑定单一项目，必须有 ``project: <id>``，禁止 ``projects``。
      - ``multi`` ：可关联多个项目，必须有非空 ``projects: [...]``，禁止 ``project``。
      - ``global``：系统级笔记，必须 ``project: global``，禁止 ``projects``。
      - ``free`` ：工作知识库笔记；``project`` / ``projects`` 二者只能出现一个、也可都不出现，
        但**不得同时出现**（工作线层面的笔记常常不属于任何单一项目）。
    required_blocks: 正文中必须存在的固定二级标题（Agent 依赖其定位，不得改名）。
    """

    scope: str
    required_blocks: tuple[str, ...] = ()
    # 曾经的必填区块，现降级为可选（如 `## AI 建议`，2026-09-18 起不再生成）。
    # 保留声明是为了让"已存在的旧笔记"仍合法——区块标题只增不减是兼容面。
    optional_blocks: tuple[str, ...] = ()


NOTE_TYPES: dict[str, NoteTypeSpec] = {
    "project-main": NoteTypeSpec(
        scope="single",
        required_blocks=("## 当前状态", "## 下一步", "## 阻塞", "## 决策记录"),
    ),
    # 知识线程项目（无 Work 文件夹）的收件箱：_vault/inboxes/<project>.md。
    # 仓库项目沿用各仓库文件夹内的 input/inbox.md，不属于 vault schema 校验范围。
    "project-inbox": NoteTypeSpec(scope="single"),
    # 推进日志：可关联 1..n 个线程/项目（R3 工作日志总结多个工作），projects 必填。
    "work-log": NoteTypeSpec(scope="multi"),
    # AI 产物（阶段总结/PRD/背景包/timeline）：绑定单一线程，project 必填。
    "thread-doc": NoteTypeSpec(scope="single"),
    "meeting-note": NoteTypeSpec(
        scope="multi",
        required_blocks=(
            "## 一分钟摘要",
            "## 会议信息",
            "## 事实与进展",
            "## 已形成决策",
            "## 明确行动项",
            "## 未决问题",
            "## 关联项目",
            "## 证据索引",
        ),
        # 2026-09-18：`## AI 建议` 不再是必填区块（使用者要求会议笔记不再生成 AI 推断）。
        # 仍列为合法区块，避免已存在的旧笔记被判非法——区块标题是只增不减的兼容面。
        optional_blocks=("## AI 建议",),
    ),
    "meeting-transcript": NoteTypeSpec(scope="multi"),
    "daily": NoteTypeSpec(scope="global"),
    "weekly-review": NoteTypeSpec(scope="global"),
    "qa-insight": NoteTypeSpec(scope="global"),
    "inbox": NoteTypeSpec(scope="global"),
    "conventions": NoteTypeSpec(scope="global"),
    "approval-page": NoteTypeSpec(scope="global"),
    # ---- 工作知识库（work knowledge base）新增类型 ----
    # 全部为**加法**：不删改上面任何既有 type 的行为，旧 vault 校验结果不变。
    # 线索主页（`hii/hii-loyalty.md` 等）：工作线层面的入口页，不属于任何单一项目。
    "workstream": NoteTypeSpec(
        scope="global",
        required_blocks=(
            "## 现在在哪",
            "## 关键结论",
            "## 未决问题",
            "## 决策记录",
            "## 时间线",
            "## 关联",
        ),
    ),
    # 一般知识笔记：正文结构自由，不设固定区块（粒度由入库样例决定）。
    "note": NoteTypeSpec(scope="free"),
    # 决策记录（集中在 `decisions/`）：固定六段，供「决策支持」检索定点取块。
    "decision": NoteTypeSpec(
        scope="free",
        required_blocks=(
            "## 背景",
            "## 选项",
            "## 决定",
            "## 理由",
            "## 影响",
            "## 证据",
            # 第 7 区块：双链的固定落点。2026-09-14 之前 decision 没有放关联的地方，
            # 只能把 `[[…]]` 塞进 `## 影响` 末尾（语义不符，实测踩到）。
            "## 关联",
        ),
    ),
    # 原始材料笔记：正文尽量不改写原文，改写产物放对应 note。
    "source": NoteTypeSpec(
        scope="free",
        required_blocks=("## 来源", "## 要点", "## 关联"),
    ),
    # 导航层（MOC）：只提供导航与简短说明，不复制正文。
    "index": NoteTypeSpec(scope="global"),
    # 工作思考长文：沿用 MyKnowledge 的三段式。
    "long-form-thought": NoteTypeSpec(
        scope="free",
        required_blocks=("## 问题缘起", "## 思考展开", "## 当前结论"),
    ),
}


# ---- 检索就绪（SummitKnowledge 接入）共享分类 ----
# 这些分类**只在这里定义一次**：检索契约（``domain/retrieval_contract.py``）与生成物
# 规范化（``workflows/knowledge_normalization.py``）都从这里取，避免各写一份词表而漂移。

# 会被 SummitKnowledge 工作库检索实际读入的类型。其余类型（导航页、规范页、收件箱、
# 模板、派生洞察、项目收件箱）只写不检索，不做检索就绪校验。
NON_RETRIEVED_TYPES = frozenset(
    {
        "index",
        "conventions",
        "inbox",
        "approval-page",
        "prompt",
        "workflow",
        "standard",
        "template",
        "qa-insight",
        "project-inbox",
    }
)

RETRIEVED_TYPES = frozenset(NOTE_TYPES) - NON_RETRIEVED_TYPES

# 有固定区块要求的类型：结构被 Agent / 定点取块依赖，检索就绪校验必须守住。
FIXED_BLOCK_TYPES = frozenset(name for name, spec in NOTE_TYPES.items() if spec.required_blocks)

# 可合法保存、但**不构成事实问答语料**的状态：草稿与待确认内容不得被当成已确认事实。
NON_FACT_STATUSES = frozenset({"draft", "pending-review", "ignored"})

# 低权威派生内容：可以参与回答，但不能单独支撑高置信事实。
DERIVED_STATUSES = frozenset({"generated"})

# 围栏代码块（``` / ~~~）与标题的识别；索引/引用只认**代码块之外**的标题。
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")


def iter_headings(body: str) -> Iterator[tuple[int, str]]:
    """按文档顺序产出**围栏代码块之外**的 Markdown 标题 ``(级别, 标题文字)``。

    标题文字已去掉 ``#`` 前缀与首尾空白（与检索契约的 ``heading`` 定义一致）。
    围栏代码里的 ``#`` 是代码示例，不是引用区块边界——若按行首匹配，一段内嵌的
    Markdown 示例会被误判成区块，进而产生假的重复标题。
    """
    fence: str | None = None
    for line in body.splitlines():
        opener = _FENCE_RE.match(line)
        if opener:
            marker = opener.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = _HEADING_RE.match(line)
        if match:
            yield len(match.group(1)), match.group(2).strip()


def has_unbalanced_fence(body: str) -> bool:
    """正文是否含未闭合的代码围栏。未闭合时后续内容无法判断是否为区块边界。"""
    fence: str | None = None
    for line in body.splitlines():
        opener = _FENCE_RE.match(line)
        if not opener:
            continue
        marker = opener.group(1)[0]
        if fence is None:
            fence = marker
        elif marker == fence:
            fence = None
    return fence is not None


def iter_missing_required_blocks(note_type: str, body: str) -> tuple[str, ...]:
    """该类型在正文里缺失的固定区块（未知类型返回空元组）。

    是 ``validate_note`` 固定区块规则的**只读复用入口**：检索契约据此判定
    「结构是否还能被定点取块」，而不必复制一份区块表。
    """
    spec = NOTE_TYPES.get(note_type)
    if spec is None:
        return ()
    return _missing_blocks(spec, body)


@dataclass(frozen=True)
class ValidationIssue:
    """一条校验问题。``field`` 可选，指向出问题的 frontmatter 字段。"""

    message: str
    field: str | None = None

    def __str__(self) -> str:
        return f"[{self.field}] {self.message}" if self.field else self.message


def validate_note(
    meta: Mapping[str, object],
    body: str,
    *,
    work_vault: bool = False,
    relative_path: PurePath | None = None,
) -> list[ValidationIssue]:
    """校验一篇笔记的 frontmatter（``meta``）与正文（``body``）。

    返回问题列表；空列表表示通过。校验只依据已确认规则，不猜测意图。
    ``work_vault=True`` 时，``area: work`` 笔记还会校验工作库的 workstream 词表。
    ``relative_path`` 用于识别机器写入页；这些页面只豁免缺失的 workstream，已有但非法
    的值仍会被拒绝。
    """
    issues: list[ValidationIssue] = []

    # 1. 必填字段
    for name in REQUIRED_FRONTMATTER:
        if name not in meta or meta[name] in (None, ""):
            issues.append(ValidationIssue("缺少必填字段", field=name))

    note_type = meta.get("type")
    status = meta.get("status")
    date = meta.get("date")

    # 2. date 格式
    if isinstance(date, str) and not _DATE_RE.match(date):
        issues.append(ValidationIssue(f"date 必须是 YYYY-MM-DD，实际为 {date!r}", field="date"))

    # 3. status 词表
    if status is not None and status not in STATUS_VOCAB:
        issues.append(
            ValidationIssue(f"status {status!r} 不在词表 {sorted(STATUS_VOCAB)}", field="status")
        )

    # 4. type 已知性
    if note_type is None:
        return issues  # 无 type 时后续规则无从判断
    if not isinstance(note_type, str) or note_type not in NOTE_TYPES:
        issues.append(
            ValidationIssue(f"未知 type {note_type!r}，允许值 {sorted(NOTE_TYPES)}", field="type")
        )
        return issues

    spec = NOTE_TYPES[note_type]
    if work_vault and meta.get("area") == "work":
        issues.extend(_check_workstream(meta, relative_path=relative_path))
    issues.extend(_check_project_scope(spec, meta))
    issues.extend(_check_project_placeholders(meta))
    issues.extend(_check_required_blocks(spec, body))
    return issues


def _is_machine_page(relative_path: PurePath | None) -> bool:
    if relative_path is None:
        return False

    parts = relative_path.parts
    if not parts:
        return False
    if parts[0] in {"daily", "logs", "artifacts", "reviews"}:
        return True
    if relative_path in {
        PurePath("inbox.md"),
        PurePath("review/meetings.md"),
        PurePath("README.md"),
    }:
        return True
    return len(parts) == 2 and parts[0] == "index" and relative_path.suffix == ".md"


def _check_workstream(
    meta: Mapping[str, object], *, relative_path: PurePath | None = None
) -> list[ValidationIssue]:
    value = meta.get("workstream")
    if not isinstance(value, str) or not value.strip():
        if _is_machine_page(relative_path):
            return []
        return [ValidationIssue("工作库笔记必须有 workstream", field="workstream")]
    if value not in WORKSTREAM_VOCAB:
        return [
            ValidationIssue(
                f"workstream {value!r} 不在词表 {sorted(WORKSTREAM_VOCAB)}",
                field="workstream",
            )
        ]
    return []


def _check_project_placeholders(meta: Mapping[str, object]) -> list[ValidationIssue]:
    """拒绝 ``project`` / ``projects`` 里**未替换的模板占位符**（与 scope 无关的硬规则）。

    为什么只查占位符、不查字符集：
    - **占位符一定错**：`project: "{{project}}"` 意味着模板没填完，页面会静默绑到一个不存在的项目。
      这正是 2026-09-14 修掉的那类缺陷（`wb vault check` 此前完全不看 `project`，坏值也能通过）。
    - **字符集不能在这里判**：会议提取管线允许 `projects:` 是自然语言项目名（如 `网课系统`），
      稍后才按别名解析；解析不到则落 `unresolved`。按字符集判定会打断会议导入（有测试守着）。
    - 也**不查项目是否已建档**：`type: project-inbox` / `thread-doc` 允许指向尚未建档的知识线程项目
      （见 `repositories/project_scan.py` 的 registered 语义）。
    """
    issues: list[ValidationIssue] = []

    candidates: list[tuple[str, object]] = []
    project = meta.get("project")
    if isinstance(project, str) and project.strip():
        candidates.append(("project", project))
    projects = meta.get("projects")
    if isinstance(projects, list):
        candidates.extend(("projects", item) for item in projects)

    for field, value in candidates:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            issues.append(ValidationIssue("项目 ID 必须是非空字符串", field=field))
            continue
        if any(marker in text for marker in _PLACEHOLDER_MARKERS):
            issues.append(
                ValidationIssue(
                    f"项目 ID 里还有未替换的占位符 {text!r}；"
                    "请填真实项目 ID（见 frontmatter 注释）",
                    field=field,
                )
            )
    return issues


def _check_project_scope(spec: NoteTypeSpec, meta: Mapping[str, object]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    has_project = "project" in meta and meta["project"] not in (None, "")
    has_projects = "projects" in meta and meta["projects"] not in (None, "", [])

    if spec.scope == "single":
        if not has_project:
            issues.append(ValidationIssue("单项目笔记必须有 project: <id>", field="project"))
        elif meta.get("project") == "global":
            issues.append(ValidationIssue("单项目笔记的 project 不能是 global", field="project"))
        if has_projects:
            issues.append(ValidationIssue("单项目笔记不得同时出现 projects", field="projects"))
    elif spec.scope == "multi":
        if not has_projects:
            issues.append(ValidationIssue("多项目笔记必须有非空 projects: [...]", field="projects"))
        elif not isinstance(meta.get("projects"), list):
            issues.append(ValidationIssue("projects 必须是数组", field="projects"))
        if has_project:
            issues.append(ValidationIssue("多项目笔记不得同时出现 project", field="project"))
    elif spec.scope == "free":
        # 工作线层面的笔记：绑定单一项目、多个项目、或都不绑定都可以，
        # 唯一硬规则仍是二者不得同时出现（与 single/multi 保持同一不变量）。
        if has_project and has_projects:
            issues.append(ValidationIssue("不得同时出现 project 与 projects", field="projects"))
        if has_projects and not isinstance(meta.get("projects"), list):
            issues.append(ValidationIssue("projects 必须是数组", field="projects"))
    else:  # global
        if meta.get("project") != "global":
            issues.append(ValidationIssue("系统级笔记必须 project: global", field="project"))
        if has_projects:
            issues.append(ValidationIssue("系统级笔记不得出现 projects", field="projects"))

    return issues


def _missing_blocks(spec: NoteTypeSpec, body: str) -> tuple[str, ...]:
    lines = {line.rstrip() for line in body.splitlines()}
    return tuple(block for block in spec.required_blocks if block not in lines)


def _check_required_blocks(spec: NoteTypeSpec, body: str) -> list[ValidationIssue]:
    return [ValidationIssue(f"缺少固定区块 {block!r}") for block in _missing_blocks(spec, body)]
