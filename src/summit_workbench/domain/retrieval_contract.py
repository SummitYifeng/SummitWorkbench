"""工作库检索就绪契约：把「能被 SummitKnowledge 稳定索引、引用与判权威」变成可执行校验。

位置说明：本模块**不是** SK 的检索实现，而是 SWB 作为写入方对外的**承诺**——凡由 SWB
自动沉淀进工作库的 Markdown，都必须满足这份契约。SK 侧的切块策略（``#``/``##`` 边界、
文首 H1 是标题、围栏代码不算标题）与本文件的规则是同一条契约的两端。

设计取舍：

- **复用 ``STATUS_VOCAB`` / ``NOTE_TYPES``**：type/status 词表只有 vault schema 一个真源，
  本模块不新增第二份；分类（是否被检索、是否有固定区块）从 ``NOTE_TYPES`` 推导。
- **只校验会被检索的类型**：``index`` / ``conventions`` / ``inbox`` / ``template`` 等
  只写不检索，正文结构自由，不因「没有 ##」而报错。
- **短笔记允许文件级引用**：``note`` / ``work-log`` / ``thread-doc`` 没有固定区块要求，
  没有 ``##`` 不是缺陷（SK 会退化为文件级块，``heading=""``）。
- **``archived`` 是合法历史知识**：它表示「项目已结束」，不表示「被推翻」；只有
  ``superseded`` 才是被替代，且必须留下替代链接。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from summit_workbench.domain.vault import (
    DERIVED_STATUSES,
    FIXED_BLOCK_TYPES,
    NON_FACT_STATUSES,
    NOTE_TYPES,
    RETRIEVED_TYPES,
    STATUS_VOCAB,
    has_unbalanced_fence,
    iter_headings,
    iter_missing_required_blocks,
)

# 可引用的块边界级别：``#``（文首标题 / 一级区块）与 ``##``（区块）。``###`` 及更深
# 保留在父块内，因此**不参与**重复判定——三级标题重复是很常见的正文写法。
_CITABLE_LEVELS = frozenset({1, 2})


@dataclass(frozen=True)
class RetrievalIssue:
    """一条检索就绪问题。``code`` 供程序判定，``message`` 供人读。"""

    code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return f"[{self.field}] {self.message}" if self.field else self.message


def is_fact_retrieval_eligible(meta: Mapping[str, object]) -> bool:
    """该笔记当前状态是否构成**事实问答语料**。

    ``draft`` / ``pending-review`` / ``ignored`` 可以合法保存，但不代表已确认事实，
    因而不进入事实问答；``generated`` 属于低权威派生内容，仍可参与回答。
    """
    note_type = meta.get("type")
    if not isinstance(note_type, str) or note_type not in RETRIEVED_TYPES:
        return False
    return not is_non_fact_status(meta)


def is_non_fact_status(meta: Mapping[str, object]) -> bool:
    """状态是否表示「可保存但不得作为事实依据」。"""
    status = meta.get("status")
    return isinstance(status, str) and status in NON_FACT_STATUSES


def is_derived_low_authority(meta: Mapping[str, object]) -> bool:
    """是否为低权威派生内容（``generated``）：可参与回答，不能单独支撑高置信事实。"""
    status = meta.get("status")
    return isinstance(status, str) and status in DERIVED_STATUSES


def validate_retrieval_readiness(
    meta: Mapping[str, object],
    body: str,
) -> list[RetrievalIssue]:
    """校验一篇笔记是否满足工作库检索就绪契约。

    返回问题列表；空列表表示通过。**不改变**任何文件——调用方据此决定是否拒绝落盘。
    """
    issues: list[RetrievalIssue] = []

    status = meta.get("status")
    if isinstance(status, str) and status and status not in STATUS_VOCAB:
        issues.append(
            RetrievalIssue(
                "unknown-status",
                f"status {status!r} 不在词表 {sorted(STATUS_VOCAB)}",
                field="status",
            )
        )

    note_type = meta.get("type")
    if not isinstance(note_type, str) or not note_type:
        # 缺 type 由 validate_note 报错；这里不重复，也不猜测。
        return issues
    if note_type not in NOTE_TYPES or note_type not in RETRIEVED_TYPES:
        # 未知 type：交回 validate_note；只写不检索的类型：不做检索就绪校验。
        return issues

    issues.extend(_check_citable_structure(body))
    issues.extend(_check_fixed_blocks(note_type, body))
    issues.extend(_check_superseded_decision(meta, note_type, status))
    return issues


def _check_citable_structure(body: str) -> list[RetrievalIssue]:
    """检查可引用区块结构：围栏闭合 + H1/H2 不重复。"""
    issues: list[RetrievalIssue] = []
    if has_unbalanced_fence(body):
        issues.append(
            RetrievalIssue(
                "invalid-fence",
                "正文存在未闭合的代码围栏，无法确定可引用区块边界",
            )
        )

    counts: dict[str, int] = {}
    for level, text in iter_headings(body):
        if level not in _CITABLE_LEVELS or not text:
            continue
        counts[text.casefold()] = counts.get(text.casefold(), 0) + 1
    for text, count in counts.items():
        if count > 1:
            issues.append(
                RetrievalIssue(
                    "duplicate-heading",
                    f"可引用标题重复 {count} 次：{text!r}。"
                    f"请改写其中一个标题；**不得**自动改名成「{text} 2」制造假引用",
                )
            )
    return issues


def _check_fixed_blocks(note_type: str, body: str) -> list[RetrievalIssue]:
    """固定区块类型继续执行 vault schema 的固定区块规则。"""
    if note_type not in FIXED_BLOCK_TYPES:
        return []
    return [
        RetrievalIssue("missing-required-block", f"缺少固定区块 {block!r}")
        for block in iter_missing_required_blocks(note_type, body)
    ]


def _check_superseded_decision(
    meta: Mapping[str, object], note_type: str, status: object
) -> list[RetrievalIssue]:
    """被替代的决策必须留下替代链接，否则引用无法回溯、旧结论会继续参与回答。"""
    if note_type != "decision" or status != "superseded":
        return []
    issues: list[RetrievalIssue] = []
    if meta.get("decision_status") != "superseded":
        issues.append(
            RetrievalIssue(
                "superseded-missing-field",
                "status: superseded 的决策必须同时写 decision_status: superseded",
                field="decision_status",
            )
        )
    superseded_by = meta.get("superseded_by")
    if not (isinstance(superseded_by, str) and superseded_by.strip()):
        issues.append(
            RetrievalIssue(
                "superseded-missing-link",
                "被替代的决策必须写 superseded_by: <替代页 source_id>，否则引用无法回溯",
                field="superseded_by",
            )
        )
    return issues


__all__ = [
    "RetrievalIssue",
    "is_derived_low_authority",
    "is_fact_retrieval_eligible",
    "is_non_fact_status",
    "validate_retrieval_readiness",
]
