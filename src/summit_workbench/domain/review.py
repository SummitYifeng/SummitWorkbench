"""审批候选、证据引用与执行动作路由的稳定 schema（供应商无关，纯逻辑）。

对应 PRD 3.1.9 L21（集中待确认页）与 L22（跨项目关联 / 路由）：

- ``EvidenceRef``：指向逐字稿的说话人 + 时间戳或稳定锚点；缺依据的候选不可勾选。
- ``ApprovalCandidate``：稳定唯一 ID、类型、目标项目、拟执行动作、来源引用；缺目标或
  依据者不进入可勾选状态。
- ``route_candidate``：把一条候选路由到飞书任务 / 项目主笔记 / 项目 inbox / 全局 inbox。

本模块只定义形状与决策规则，不生成 Markdown、不写盘（那是 M1-4 的 repositories 层）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# AI 无法可靠判断目标项目时的占位（L22）；不得自行造新项目名。
UNRESOLVED = "unresolved"


class CandidateKind(StrEnum):
    """待确认候选的类型（L21）。"""

    DECISION = "decision"  # 候选决策
    ACTION_ITEM = "action-item"  # 明确行动项
    PROJECT_STATUS_CHANGE = "project-status-change"  # 项目状态变化
    TASK_CREATE = "task-create"  # 拟创建任务


class RouteTarget(StrEnum):
    """执行动作的写入位置（L22 路由规则）。"""

    FEISHU_TASK = "feishu-task"  # 有期限或涉及他人
    FEISHU_MEETING = "feishu-meeting"  # 会议结论落成未来日历日程（新建飞书日历事件）
    PROJECT_MAIN = "project-main"  # 明确内部下一步
    PROJECT_INBOX = "project-inbox"  # 未成熟想法
    GLOBAL_INBOX = "global-inbox"  # 目标项目不明


class CandidateDecision(StrEnum):
    """用户在待确认页对一条候选的裁决（L21 的 ``- [ ]`` / ``- [x]`` / ``#ignore``）。"""

    PENDING = "pending"  # - [ ]
    APPROVED = "approved"  # - [x]
    REJECTED = "rejected"  # ~~...~~ #ignore


@dataclass(frozen=True)
class EvidenceRef:
    """指向逐字稿的来源引用：说话人 + 时间戳/锚点，可选原话。"""

    speaker: str | None = None
    anchor: str | None = None  # 相对时间戳或稳定段落锚点
    quote: str | None = None

    def is_valid(self) -> bool:
        """至少要有时间戳/锚点或原话之一才算有依据。"""
        return bool((self.anchor and self.anchor.strip()) or (self.quote and self.quote.strip()))


def _has_project(target_project: str | None) -> bool:
    """目标项目是否已解析（非空且非 ``unresolved``）。"""
    return bool(target_project) and target_project != UNRESOLVED


@dataclass(frozen=True)
class ApprovalCandidate:
    """一条待确认候选。缺目标项目或缺来源依据者不可进入可勾选状态（L21）。"""

    candidate_id: str
    kind: CandidateKind
    description: str
    target_project: str | None = None
    route: RouteTarget | None = None
    evidence: EvidenceRef | None = None
    due_date: str | None = None  # YYYY-MM-DD；无期限留空
    start_at: str | None = None  # 新建日历会议的开始时间（本地 naive YYYY-MM-DDTHH:MM）
    end_at: str | None = None  # 新建日历会议的结束时间（同上；缺省按开始 + 1 小时）
    involves_others: bool = False
    is_next_step: bool = False  # 明确的内部下一步（区别于未成熟想法）
    decision: CandidateDecision = CandidateDecision.PENDING
    historical: bool = False  # 历史补导产生的候选（L14 第 10 条）

    def is_actionable(self) -> bool:
        """是否可进入可勾选状态：必须有有效来源依据，且目标可写。

        目标可写的判定按 route 区分（贴合真实场景：多数会议未必对应已建项目）：
        - 全局 inbox 与新建日历会议（个人日程排期）正是「目标项目不明」的兜底，
          不需要已解析项目即可捕获/落日程；
        - 其余落点（项目主笔记 / 项目 inbox / 飞书任务 / 未定 route）需已解析目标项目。
        """
        if self.evidence is None or not self.evidence.is_valid():
            return False
        if self.route in (RouteTarget.GLOBAL_INBOX, RouteTarget.FEISHU_MEETING):
            return True
        return _has_project(self.target_project)


@dataclass(frozen=True)
class ReviewEntry:
    """审批页中的完整条目：可编辑候选 + AI 原值 + 会议来源。"""

    candidate: ApprovalCandidate
    ai_original: str
    meeting_date: str
    meeting_title: str
    note_link: str
    transcript_link: str
    apply_error: str | None = None


def route_candidate(
    *,
    target_project: str | None,
    has_due_date: bool,
    involves_others: bool,
    is_next_step: bool,
) -> RouteTarget:
    """按 L22 规则决定一条候选的写入位置。

    优先级：目标不明 → 全局 inbox；有期限或涉及他人 → 飞书任务；明确内部下一步 → 项目
    主笔记；否则（未成熟想法）→ 项目 inbox。
    """
    if not _has_project(target_project):
        return RouteTarget.GLOBAL_INBOX
    if has_due_date or involves_others:
        return RouteTarget.FEISHU_TASK
    if is_next_step:
        return RouteTarget.PROJECT_MAIN
    return RouteTarget.PROJECT_INBOX


def candidate_id(idem_key: str, kind: CandidateKind, index: int) -> str:
    """由会议幂等键 + 类型 + 序号派生的稳定唯一候选 ID。

    同一会议重跑得到同样的 ID，避免待确认页重复条目（L21 稳定唯一 ID 要求）。
    """
    return f"{idem_key}#{kind.value}-{index}"
