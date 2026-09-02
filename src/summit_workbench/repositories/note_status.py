"""保留正文地更新 vault 笔记 frontmatter 状态。"""

from __future__ import annotations

from pathlib import Path

import yaml

from summit_workbench.domain.vault import STATUS_VOCAB
from summit_workbench.repositories._atomic import atomic_write_text
from summit_workbench.repositories.vault import parse_frontmatter


def update_note_status(path: Path, status: str, *, extra: dict[str, object] | None = None) -> None:
    if status not in STATUS_VOCAB:
        raise ValueError(f"未知笔记状态：{status}")
    if not path.is_file():
        return
    meta, body, error = parse_frontmatter(path.read_text(encoding="utf-8"))
    if error is not None:
        raise ValueError(f"无法更新无效笔记：{path}：{error}")
    meta["status"] = status
    if extra:
        meta.update(extra)
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    atomic_write_text(path, f"---\n{fm}\n---\n\n{body}")
