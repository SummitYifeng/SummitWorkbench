"""把已解析项目并入多项目笔记 frontmatter 的 ``projects``（审批应用后的会议回链解析）。

背景（改进 2）：会议提取时若模型无法判断目标项目，会议笔记 frontmatter 的
``projects`` 以 ``unresolved`` 占位；用户在审批页把候选批准到某个项目并应用写回后，
该会议笔记仍留在 ``unresolved``——既不进该项目的时间线，Obsidian 图谱里也连不上
项目主档案。本模块在写回成功后把实际项目并入来源会议笔记：

- 只处理带 ``projects`` 数组的笔记（meeting-note 等多项目类型）；移除
  ``unresolved`` 占位并把 ``project`` 并入（去重、保序）；
- 与 :func:`~summit_workbench.repositories.note_status.update_note_status` 同一写路径
  约定：``read -> mutate -> atomic_write`` 整体落在工作区锁内；幂等，无变化不写盘。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.review import UNRESOLVED
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter


def merge_note_project(vault_dir: Path, path: Path, project: str) -> bool:
    """把 ``project`` 并入笔记的 ``projects``（移除 ``unresolved`` 占位，去重保序）。

    返回是否发生写入（False = 无事可做或幂等跳过）：

    - 文件不存在 → False；
    - frontmatter 解析失败 → 抛 :class:`ValueError`（与其他写路径同语义：宁可暴露，
      不静默改坏笔记）；
    - 笔记没有 ``projects`` 数组（非多项目类型，如单项目产物/主档案）→ False；
    - ``project`` 非法（空/``unresolved``）→ False；
    - ``project`` 已在列表中且无 ``unresolved`` 可清 → False（幂等）。
    """
    if not project or project == UNRESOLVED:
        return False
    if not path.is_file():
        return False
    # 锁只包文件临界区（parse -> mutate -> atomic_write），同线程嵌套按重入放行。
    with workspace_lock(vault_dir.parent):
        meta, body, error = parse_frontmatter(path.read_text(encoding="utf-8"))
        if error is not None:
            raise ValueError(f"无法更新无效笔记：{path}：{error}")
        projects = meta.get("projects")
        if not isinstance(projects, list):
            return False
        cleaned = [p for p in projects if isinstance(p, str) and p and p != UNRESOLVED]
        if project in cleaned:
            return False
        cleaned.append(project)
        meta["projects"] = cleaned
        fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        atomic_write_text(path, f"---\n{fm}\n---\n\n{body}")
        return True
