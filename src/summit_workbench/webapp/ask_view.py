"""问答 workflow ↔ HTML 桥（LEGACY-APP-SPLIT-PLAN Step 13 / S4）。

承载原 ``legacy_app`` 的 ``_ask_html`` 与 ``_cited_source_ids``：跑一次 ``wb ask``
（可带追问上下文与项目/线程范围）并渲染为面板 HTML，并从结构化答案中抽取引用来源。

``_ask_html`` 的函数体逐字保留（依赖仍在函数内局部 import），以维持既有 monkeypatch
契约——迁移后测试 patch 的是 ``summit_workbench.webapp.routers.ask._ask_html``。
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from summit_workbench.workflows.ask.ask import AskTurn


def _cited_source_ids(answer: dict[str, object] | None) -> list[str]:
    if not answer:
        return []
    cited: set[str] = set()
    facts = answer.get("facts")
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict) and isinstance(fact.get("source_id"), str):
                cited.add(fact["source_id"])
    conflicts = answer.get("conflicts")
    if isinstance(conflicts, list):
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            sides = conflict.get("sides")
            if isinstance(sides, list):
                for side in sides:
                    if isinstance(side, dict) and isinstance(side.get("source_id"), str):
                        cited.add(side["source_id"])
    return sorted(cited)


def _ask_html(
    vault_dir: Path,
    question: str,
    history: tuple[AskTurn, ...] = (),
    project: str | None = None,
    *,
    config_file: Path | None = None,
    workspace_id: str | None = None,
) -> tuple[str, list[str], dict[str, object] | None]:
    """跑一次 wb ask（可带追问上下文与项目/线程范围）并渲染为 HTML。

    模型不可用时返回可见错误；source_ids 供前端存进会话，追问时回传给后端。
    """
    from summit_workbench.config.secrets import CredentialError, resolve_credential
    from summit_workbench.prompts import load_prompt
    from summit_workbench.providers.llm import LLMError, load_model_config
    from summit_workbench.repositories.kb_index import default_index_path
    from summit_workbench.workflows.ask.ask import answer_question

    try:
        if config_file is None and workspace_id is None:
            cfg = load_model_config("qa")
        else:
            cfg = load_model_config("qa", config_file, workspace_id=workspace_id)
        api_key = resolve_credential(cfg.api_key_ref)
        prompt = load_prompt("qa-answer")
        result = answer_question(
            vault_dir,
            question,
            cfg,
            api_key,
            prompt=prompt,
            history=history,
            project=project,
            index_path=default_index_path(),
        )
    except (LLMError, CredentialError, FileNotFoundError, ValueError) as exc:
        return f'<p class="not-actionable">问答不可用：{escape(str(exc))}</p>', [], None

    answer = result.answer
    parts = [f"<p><strong>{escape(answer.summary)}</strong></p>"]
    if answer.facts:
        parts.append("<h4>事实（带来源）</h4><ul>")
        parts += [
            f"<li>{escape(f.text)} <span class='wikilink'>[[{escape(f.source_id)}]]</span></li>"
            for f in answer.facts
        ]
        parts.append("</ul>")
    if answer.suggestions:
        parts.append("<h4>建议（模型推断）</h4><ul>")
        parts += [f"<li>{escape(s)}</li>" for s in answer.suggestions]
        parts.append("</ul>")
    source_ids = [c.source_id for c in result.sources]
    if result.sources:
        srcs = "、".join(f"[[{escape(c.source_id)}]]" for c in result.sources)
        parts.append(f'<p class="not-actionable">召回来源：{srcs}</p>')
    trace_html = _trace_html(result)
    if trace_html:
        parts.append(trace_html)
    return "\n".join(parts), source_ids, answer.model_dump(mode="json")


def _trace_html(result: object) -> str:
    """把检索轨迹渲染成一个可折叠区块：命中了哪些块、走了哪些双链、排除了什么、为什么。"""
    trace = getattr(result, "trace", None)
    sources = getattr(result, "sources", ())
    if trace is None and not sources:
        return ""
    rows: list[str] = []
    if trace is not None:
        rows.append(
            f"<p>路由：<code>{escape(trace.route)}</code>（{escape(trace.route_reason)}）</p>"
        )
        rows.append("<p>检索词：" + escape("、".join(trace.terms) or "—") + "</p>")
        if trace.expanded:
            items = "".join(
                f"<li><code>{escape(anchor)}</code> ← {escape(seed)}</li>"
                for anchor, seed in trace.expanded
            )
            rows.append(f"<p>双链扩展：</p><ul>{items}</ul>")
        if trace.dropped:
            items = "".join(
                f"<li><code>{escape(anchor)}</code>：{escape(reason)}</li>"
                for anchor, reason in trace.dropped
            )
            rows.append(f"<p>已排除：</p><ul>{items}</ul>")
    if sources:
        items = "".join(
            "<li><code>"
            + escape(candidate.source_id)
            + "</code>（"
            + escape(candidate.note_type or "—")
            + "）"
            + (("：" + escape("；".join(candidate.why))) if candidate.why else "")
            + "</li>"
            for candidate in sources
        )
        rows.append(f"<p>命中块与命中理由：</p><ul>{items}</ul>")
    return "<details class='kb-trace'><summary>检索轨迹</summary>" + "".join(rows) + "</details>"


__all__ = ["_ask_html", "_cited_source_ids", "_trace_html"]
