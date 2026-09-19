"""自动产物的确定性结构规范化：**不调用模型**，只做可复现的 Markdown 处理。

为什么需要它：SWB 自动沉淀的日志与产物过去直接把用户原文（或模型产物）拼在 H1 之后。
原文常自带 ``# 标题``、偶尔自带 ``##``，于是同一篇笔记出现两个 H1、或缺少「关联项目」
回链——SK 侧按「文首 H1 是笔记标题、后续 ``#``/``##`` 是块边界」切块时，引用就会退化
或指向一个假的「标题 2」区块。

本模块只做三件事，且都可被单测逐字验证：

1. 清掉正文里**重复的文首 H1**（笔记标题由调用方给定，只保留一个）；
2. 已有 H2 时保留原结构（含 H3），缺内容区块时按类型补一个默认区块；
3. 补上缺失的 ``## 关联项目`` 双链区块（已存在则原样保留，绝不重复生成）。

无法安全规范化时**拒绝落盘**：返回 issues，调用方据此抛错，目标文件不会出现。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from summit_workbench.domain.retrieval_contract import RetrievalIssue
from summit_workbench.domain.vault import has_unbalanced_fence, iter_headings

# 该类型「没有 H2」时的默认内容区块。注意 work-log 的生产路径（``append_work_log``）
# 会显式带上 ``## 原文`` 区块——那是既有读者（project_view 的兜底片段）与并发落盘测试
# 共同锁定的契约，因此走「已有 H2 → 保留原结构」分支；这里的默认值服务的是
# 「调用方只给一段裸文本」的情形。
_DEFAULT_CONTENT_HEADING: dict[str, str] = {
    "thread-doc": "## 内容",
    "work-log": "## 工作记录",
}
_FALLBACK_CONTENT_HEADING = "## 内容"

# 关联项目区块：正文的实体双链落点（Obsidian 图谱 / 反链）。
_RELATED_HEADING = "## 关联项目"

# 可引用块边界：``#`` / ``##``。``###`` 及更深留在父块内，不参与重复判定。
_CITABLE_LEVELS = frozenset({1, 2})


@dataclass(frozen=True)
class NormalizedKnowledgeBody:
    """规范化结果。``issues`` 非空时 ``body`` 为空字符串——调用方必须拒绝落盘。"""

    body: str
    issues: tuple[RetrievalIssue, ...]


def _project_links(projects: Sequence[str]) -> str:
    seen: list[str] = []
    for project in projects:
        if project and project not in seen:
            seen.append(project)
    return "\n".join(f"- [[projects/{project}]]" for project in seen)


def _strip_leading_h1(lines: list[str]) -> list[str]:
    """去掉文档开头的 H1（允许中间夹空行），返回剩余行。

    只处理**文首**：正文中段的 H1 属于内容，原样保留（其重复由契约另行判定）。
    """
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            index += 1
            continue
        break
    return lines[index:]


def normalize_generated_body(
    *,
    note_type: str,
    title: str,
    text: str,
    project_links: Sequence[str],
) -> NormalizedKnowledgeBody:
    """把一段自动生成/用户原文规范化为可被 SK 稳定切块的 Markdown 正文。

    返回的 ``body`` 始终以 ``# <title>`` 开头；原文内容逐字保留（只剥掉文首重复 H1）。
    """
    issues: list[RetrievalIssue] = []
    clean_title = title.strip()
    raw = text.strip()
    if not clean_title:
        issues.append(RetrievalIssue("missing-title", "生成型笔记必须有标题（H1 不能为空）"))
    if not raw:
        issues.append(RetrievalIssue("empty-body", "正文不能为空"))
    if issues:
        return NormalizedKnowledgeBody("", tuple(issues))

    if has_unbalanced_fence(raw):
        return NormalizedKnowledgeBody(
            "",
            (
                RetrievalIssue(
                    "invalid-fence",
                    "正文存在未闭合的代码围栏，无法确定区块边界；请补齐围栏后重试",
                ),
            ),
        )

    counts: dict[str, int] = {}
    for level, heading in iter_headings(raw):
        if level not in _CITABLE_LEVELS or not heading:
            continue
        counts[heading.casefold()] = counts.get(heading.casefold(), 0) + 1
    duplicated = sorted(text for text, count in counts.items() if count > 1)
    if duplicated:
        return NormalizedKnowledgeBody(
            "",
            tuple(
                RetrievalIssue(
                    "duplicate-heading",
                    f"正文含重复的可引用标题 {text!r}："
                    f"拒绝自动改名成「{text} 2」（那会制造假引用），请人工改写",
                )
                for text in duplicated
            ),
        )

    content = "\n".join(_strip_leading_h1(raw.splitlines())).strip()
    has_h2 = any(level == 2 and heading for level, heading in iter_headings(content))

    parts = [f"# {clean_title}", ""]
    if has_h2:
        parts.append(content)
    else:
        heading = _DEFAULT_CONTENT_HEADING.get(note_type, _FALLBACK_CONTENT_HEADING)
        parts.append(heading)
        parts.append("")
        parts.append(content)

    existing = {heading.casefold() for level, heading in iter_headings(content) if level == 2}
    links = _project_links(project_links)
    if _RELATED_HEADING.removeprefix("## ").casefold() not in existing and links:
        parts.append("")
        parts.append(_RELATED_HEADING)
        parts.append("")
        parts.append(links)

    return NormalizedKnowledgeBody("\n".join(parts).rstrip() + "\n", ())


def format_normalization_error(issues: Sequence[RetrievalIssue]) -> str:
    """把规范化问题渲染成一句可读错误（不泄露内部栈）。"""
    return "；".join(f"{issue.code}: {issue.message}" for issue in issues)


__all__ = [
    "NormalizedKnowledgeBody",
    "format_normalization_error",
    "normalize_generated_body",
]
