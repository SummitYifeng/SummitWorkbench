"""全局收件箱（`inbox.md`）的解析、条目移除与提升建议（契约 §10）。

**只读 + 纯逻辑**：本模块不调模型、不写盘。三种提升的落点各自复用既有实现
（项目页 → `repositories/writeback.py`；飞书待办 → `workflows/external_actions.py` 的
outbox；工作思考 → `repositories/thread_notes.py` 的思考落盘），本模块只负责
**认得出条目、说得清该提升成什么、并把它干净地移出收件箱**。

条目形状由写入口 `writeback._append_under_heading` 决定（本模块不另立一套 Markdown 规则）：

    ## 待处理条目

    - [ ] 把课程材料翻译流程定稿 #it-development
      <!-- wb-candidate: web-20260919123456789012 -->
      <!-- wb-capture-kind: task -->
      <!-- wb-capture-due: 2026-09-20 -->
      <!-- wb-capture-project: it-development -->

条目 = 一条 `- [ ] ` 复选框行 + 紧随其后的**缩进行**（机器标记注释、或手工续行）。
契约 §10：被提升/已处理的条目**移出**收件箱、**不留占位行**——`remove_inbox_entry` 的
唯一职责就是把这件事做干净（不产生双空行、不在文末留空行）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from summit_workbench.repositories.writeback import GLOBAL_INBOX_HEADING

# `## 待处理条目` 区里的一条待处理条目（与 `project_scan.count_inbox_pending` 同一判据）。
_CHECKBOX_PENDING = "- [ ] "
# 机器标记注释：`<!-- wb-candidate: … -->`（capture 与 writeback 都写这一族）。
_MARKER = re.compile(r"^<!--\s*(wb-[a-z-]+)\s*:\s*(.*?)\s*-->$")

# 三种提升目标（契约 §10）。'project' 还分两个区块，由调用方的 block 参数决定。
PROMOTION_TARGETS = ("project", "feishu-task", "thought")


@dataclass(frozen=True)
class InboxEntry:
    """一条待处理条目。

    ``start`` / ``stop`` 是它在 ``inbox.md`` 里的行区间（``[start, stop)``，0 基），
    供 :func:`remove_inbox_entry` 精确移除；``id`` 是**稳定标识**——有 `wb-candidate`
    标记就用它（写入口写的，唯一且跨次读取稳定），手工写的条目退化为
    ``local-<正文摘要>-<同正文序号>``（正文不变则稳定）。
    """

    id: str
    text: str
    kind: str | None = None
    due: str | None = None
    project: str | None = None
    candidate_id: str | None = None
    start: int = 0
    stop: int = 0


def _local_id(text: str, ordinal: int) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"local-{digest}-{ordinal}"


def _region(lines: list[str]) -> tuple[int, int]:
    """返回 ``## 待处理条目`` 区的 ``[正文起点, 区块终点)``。

    缺该区块 ⇒ 空区间（还没写过收件箱）。**重复**该区块 ⇒ 抛 ``ValueError``：与写入口
    `writeback._append_under_heading` 同一纪律——"提升哪一条"必须唯一，静默取第一处会让
    使用者在错误的区里删条目。
    """
    matches = [index for index, line in enumerate(lines) if line.rstrip() == GLOBAL_INBOX_HEADING]
    if not matches:
        return 0, 0
    if len(matches) > 1:
        raise ValueError(
            f"inbox.md 存在重复区块 {GLOBAL_INBOX_HEADING!r}（{len(matches)} 处）；"
            "请先合并为唯一区块再提升条目"
        )
    start = matches[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def parse_inbox_entries(text: str) -> list[InboxEntry]:
    """解析出全部待处理条目（按文件顺序）。非 ``- [ ] `` 行原样不动。"""
    lines = text.splitlines()
    start, end = _region(lines)
    entries: list[InboxEntry] = []
    ordinals: dict[str, int] = {}
    index = start
    while index < end:
        line = lines[index]
        if not line.lstrip().startswith(_CHECKBOX_PENDING):
            index += 1
            continue
        body = line.strip()[len(_CHECKBOX_PENDING) :].strip()
        markers: dict[str, str] = {}
        stop = index + 1
        # 条目 = 复选框行 + 紧随的**缩进**行（标记注释 / 手工续行）；空行或另一条复选框行结束它。
        while stop < end and lines[stop].startswith((" ", "\t")) and lines[stop].strip():
            matched = _MARKER.match(lines[stop].strip())
            if matched is not None:
                markers.setdefault(matched.group(1), matched.group(2))
            stop += 1
        candidate_id = markers.get("wb-candidate") or None
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
        if candidate_id:
            entry_id = candidate_id
        else:
            ordinals[digest] = ordinals.get(digest, 0) + 1
            entry_id = _local_id(body, ordinals[digest])
        entries.append(
            InboxEntry(
                id=entry_id,
                text=body,
                kind=markers.get("wb-capture-kind") or None,
                due=markers.get("wb-capture-due") or None,
                project=markers.get("wb-capture-project") or None,
                candidate_id=candidate_id,
                start=index,
                stop=stop,
            )
        )
        index = stop
    return entries


def find_entry(entries: list[InboxEntry], entry_id: str) -> InboxEntry | None:
    for entry in entries:
        if entry.id == entry_id:
            return entry
    return None


def remove_inbox_entry(text: str, entry: InboxEntry) -> str:
    """把一条条目移出收件箱，**不留占位行**（契约 §10）。

    只吸收条目**后面**的那一个分隔空行：这样条目之间不会出现双空行，文末的孤立空行由
    结尾的 ``rstrip`` 收掉，区块后紧跟其它 ``##`` 区块时也不会把分隔空行吞掉。
    """
    lines = text.splitlines()
    start, stop = entry.start, entry.stop
    if stop < len(lines) and not lines[stop].strip():
        stop += 1
    remaining = [*lines[:start], *lines[stop:]]
    return "\n".join(remaining).rstrip() + "\n"


def suggest_promotion(entry: InboxEntry) -> tuple[str, str]:
    """**本地启发式**给出默认提升目标（不调模型）+ 一句说明为什么。

    三条规则，只决定弹层默认选中哪个，最终一律由使用者确认：

    1. 有截止日期 ⇒ ``feishu-task``（待办的真源在飞书，库内不留可检索正文）；
    2. 有 ``#项目`` ⇒ ``project``（项目标签是使用者自己打的**路由信号**，默认归到该项目页；
       写「下一步」还是「跟进事项」由弹层里再选）；
    3. 其余 ⇒ ``thought``（跨项目、组织层面的沉淀）。
    """
    if entry.due:
        return "feishu-task", f"有截止日期 {entry.due} ⇒ 按待办处理（真源在飞书）"
    if entry.project:
        return "project", f"有 #{entry.project} ⇒ 归到该项目页（下一步 / 跟进事项）"
    return "thought", "没有截止日期、也没有项目归属 ⇒ 先沉淀成一篇工作思考"


__all__ = [
    "PROMOTION_TARGETS",
    "InboxEntry",
    "find_entry",
    "parse_inbox_entries",
    "remove_inbox_entry",
    "suggest_promotion",
]
