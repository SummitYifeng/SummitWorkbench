"""``wb kb``：工作知识库检索索引的构建与体检。

索引库**放在 vault 之外**（`Application Support/SummitWorkbench/kb-index.sqlite`），
因此这里的所有命令都不会往知识库里写任何东西。
"""

from __future__ import annotations

from pathlib import Path

import typer

from summit_workbench.config.settings import load_settings
from summit_workbench.repositories.kb_index import (
    KnowledgeIndex,
    default_index_path,
    fts5_available,
)
from summit_workbench.workflows.ask.retrieval import build_index
from summit_workbench.workflows.ask.router import heuristic_route

kb_app = typer.Typer(
    name="kb",
    help="工作知识库检索索引（构建 / 状态 / 路由试算）。",
    no_args_is_help=True,
    add_completion=False,
)


def _vault_dir(path: Path | None) -> Path:
    return path or load_settings().work_paths().vault_dir


@kb_app.command("index")
def index(
    path: Path | None = typer.Argument(None, help="vault 目录；默认取配置解析出的 vault_dir。"),
    full: bool = typer.Option(False, "--full", help="全量重建（忽略增量哈希）。"),
    index_file: Path | None = typer.Option(
        None, "--index-file", help="索引库路径（默认在 vault 之外）。"
    ),
) -> None:
    """构建或增量更新检索索引。"""
    vault_dir = _vault_dir(path)
    if not vault_dir.is_dir():
        typer.echo(f"vault 目录不存在：{vault_dir}")
        raise typer.Exit(code=2)
    target = index_file or default_index_path()
    if target.is_relative_to(vault_dir):
        typer.echo("✗ 索引库不能放在 vault 内（会污染资产与双机同步）")
        raise typer.Exit(code=2)
    stats = build_index(vault_dir, target, full=full)
    typer.echo(f"✓ 索引已{'全量重建' if full else '增量更新'}：{stats.summary()}")
    typer.echo(f"  索引库：{target}")
    typer.echo(f"  FTS5/trigram：{'可用' if fts5_available() else '不可用（退化为自建 BM25）'}")


@kb_app.command("status")
def status(
    index_file: Path | None = typer.Option(None, "--index-file", help="索引库路径。"),
) -> None:
    """查看索引状态（库位置、块数、FTS5 可用性）。"""
    target = index_file or default_index_path()
    if not target.is_file():
        typer.echo(f"索引尚未建立：{target}")
        typer.echo("先跑 `wb kb index`。")
        raise typer.Exit(code=1)
    vault_dir = _vault_dir(None)
    with KnowledgeIndex(vault_dir, target) as index:
        typer.echo(f"索引库：{target}")
        typer.echo(f"笔记数：{len(index.notes())}，块数：{index.chunk_count()}")
        typer.echo(f"FTS5/trigram：{'可用' if fts5_available() else '不可用（退化为自建 BM25）'}")


@kb_app.command("route")
def route(question: str = typer.Argument(..., help="要试算路由的问题。")) -> None:
    """试算查询路由（点查 / 综合 / 回溯 / 决策 / 回顾），不检索、不调用模型。"""
    kind, reason = heuristic_route(question)
    typer.echo(f"{kind.value}：{reason}")
