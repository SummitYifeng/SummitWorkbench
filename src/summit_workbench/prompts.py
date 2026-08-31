"""版本化 prompt 加载（PRD 3.2.1）。

prompt 正文写在仓库 ``prompts/<name>.md``，禁止在业务代码内联 prompt 字符串。
每个文件带 frontmatter（name / version / capability / output），本模块解析后交给上层。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from summit_workbench.repositories.vault import parse_frontmatter


def prompts_dir() -> Path:
    """定位 prompts 目录：优先 ``WB_PROMPTS_DIR``，否则取仓库根的 prompts/。"""
    override = os.environ.get("WB_PROMPTS_DIR")
    if override:
        return Path(override).expanduser()
    # src/summit_workbench/prompts.py → parents[2] 为仓库根
    return Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    capability: str
    body: str

    @property
    def version_label(self) -> str:
        return f"{self.name}@v{self.version}"


def load_prompt(name: str, base_dir: Path | None = None) -> Prompt:
    path = (base_dir or prompts_dir()) / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt 文件不存在：{path}")
    meta, body, error = parse_frontmatter(path.read_text(encoding="utf-8"))
    if error is not None:
        raise ValueError(f"prompt {name} frontmatter 无效：{error}")
    return Prompt(
        name=str(meta.get("name", name)),
        version=int(str(meta.get("version", 0))),
        capability=str(meta.get("capability", "")),
        body=body.strip(),
    )
