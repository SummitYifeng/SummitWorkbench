"""保留正文地更新 vault 笔记 frontmatter 状态。

``read -> 变换 -> atomic_write_text`` 的整体落在工作区锁内（P0 写路径并发加固）：
同一时间只有一个 wb 写入者改同一份 frontmatter，避免并发 RMW 静默丢失更新。
锁根由调用方显式给出（``vault_dir.parent``），测试环境天然隔离在各自 tmp 下。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from summit_workbench.config.locking import workspace_lock
from summit_workbench.domain.vault import STATUS_VOCAB
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter


def update_note_status(
    vault_dir: Path,
    path: Path,
    status: str,
    *,
    extra: dict[str, object] | None = None,
) -> None:
    if status not in STATUS_VOCAB:
        raise ValueError(f"未知笔记状态：{status}")
    if not path.is_file():
        return
    # 锁只包文件临界区（parse -> mutate -> atomic_write），同线程嵌套时按重入放行。
    with workspace_lock(vault_dir.parent):
        meta, body, error = parse_frontmatter(path.read_text(encoding="utf-8"))
        if error is not None:
            raise ValueError(f"无法更新无效笔记：{path}：{error}")
        meta["status"] = status
        if extra:
            meta.update(extra)
        fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        atomic_write_text(path, f"---\n{fm}\n---\n\n{body}")
