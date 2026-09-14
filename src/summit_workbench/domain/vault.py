"""工作 vault 的稳定 schema 与校验规则（PRD 3.1.5 / 3.1.9）。

这些规则是「为未来 SummitKnowledge 接入付出的兼容成本」的落点：统一 frontmatter、
固定区块、项目关联字段。纯逻辑，不读文件——由 repositories 层解析后调用本模块。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

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

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
            "## AI 建议",
            "## 关联项目",
            "## 证据索引",
        ),
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


@dataclass(frozen=True)
class ValidationIssue:
    """一条校验问题。``field`` 可选，指向出问题的 frontmatter 字段。"""

    message: str
    field: str | None = None

    def __str__(self) -> str:
        return f"[{self.field}] {self.message}" if self.field else self.message


def validate_note(meta: Mapping[str, object], body: str) -> list[ValidationIssue]:
    """校验一篇笔记的 frontmatter（``meta``）与正文（``body``）。

    返回问题列表；空列表表示通过。校验只依据已确认规则，不猜测意图。
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
    issues.extend(_check_project_scope(spec, meta))
    issues.extend(_check_required_blocks(spec, body))
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


def _check_required_blocks(spec: NoteTypeSpec, body: str) -> list[ValidationIssue]:
    lines = {line.rstrip() for line in body.splitlines()}
    missing = [block for block in spec.required_blocks if block not in lines]
    return [ValidationIssue(f"缺少固定区块 {block!r}") for block in missing]
