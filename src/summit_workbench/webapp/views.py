"""面板的 HTML 渲染（纯函数，无 IO；便于快照测试）。"""

from __future__ import annotations

import re
from html import escape

from summit_workbench.domain.pipeline import ProcessingState
from summit_workbench.domain.review import (
    CandidateDecision,
    ReviewEntry,
    RouteTarget,
)
from summit_workbench.observability.status import StatusReport

_ROUTE_LABELS = {
    RouteTarget.FEISHU_TASK: "飞书任务",
    RouteTarget.FEISHU_MEETING: "新建会议",
    RouteTarget.PROJECT_MAIN: "项目主笔记",
    RouteTarget.PROJECT_FOLLOWUP: "跟进事项",
    RouteTarget.PROJECT_INBOX: "项目 inbox",
    RouteTarget.GLOBAL_INBOX: "全局 inbox",
    RouteTarget.KNOWLEDGE_NOTE: "知识沉淀",
}
_DECISION_BADGE = {
    CandidateDecision.PENDING: ("待确认", "pending"),
    CandidateDecision.APPROVED: ("已批准", "approved"),
    CandidateDecision.REJECTED: ("已拒绝", "rejected"),
}

_STYLE = """
:root { color-scheme: light dark; --fg:#1a1a1a; --bg:#fafafa; --card:#fff; --border:#e2e2e2;
  --muted:#666; --accent:#2b6cb0; --ok:#2f855a; --bad:#c53030; --warn:#b7791f; }
@media (prefers-color-scheme: dark) { :root { --fg:#e8e8e8; --bg:#16181c; --card:#1f2228;
  --border:#31353c; --muted:#9aa0a6; --accent:#63b3ed; --ok:#68d391; --bad:#fc8181; --warn:#f6ad55; } }
* { box-sizing: border-box; } body { font-family: -apple-system, "PingFang SC", sans-serif;
  margin:0; background:var(--bg); color:var(--fg); line-height:1.5; }
header { position:sticky; top:0; background:var(--card); border-bottom:1px solid var(--border);
  padding:12px 20px; display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
header h1 { font-size:17px; margin:0; } .spacer { flex:1; }
main { max-width:900px; margin:0 auto; padding:20px; }
.msg { background:var(--card); border:1px solid var(--accent); border-radius:8px; padding:10px 14px;
  margin-bottom:16px; } .err { border-color:var(--bad); color:var(--bad); }
.meeting { margin:24px 0 8px; font-size:14px; color:var(--muted); border-bottom:1px solid var(--border);
  padding-bottom:6px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px;
  margin:12px 0; } .card.approved { border-left:4px solid var(--ok); }
.card.rejected { border-left:4px solid var(--bad); opacity:.7; }
.card.pending { border-left:4px solid var(--warn); }
.desc { font-size:15px; margin:0 0 8px; } .kind { font-size:12px; color:var(--muted); }
.badge { font-size:12px; padding:2px 8px; border-radius:999px; border:1px solid var(--border); }
.badge.approved { color:var(--ok); } .badge.rejected { color:var(--bad); } .badge.pending { color:var(--warn); }
.meta { font-size:13px; color:var(--muted); margin:6px 0; }
.row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
button { font:inherit; padding:6px 12px; border-radius:7px; border:1px solid var(--border);
  background:var(--card); color:var(--fg); cursor:pointer; }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button.ok { color:var(--ok); } button.bad { color:var(--bad); }
input, select, textarea { font:inherit; padding:5px 8px; border:1px solid var(--border);
  border-radius:6px; background:var(--bg); color:var(--fg); }
textarea { width:100%; min-height:48px; } details { margin-top:8px; }
summary { cursor:pointer; color:var(--accent); font-size:13px; }
.grid { display:grid; grid-template-columns:auto 1fr; gap:6px 10px; align-items:center; margin-top:8px; }
a { color:var(--accent); } .not-actionable { color:var(--warn); font-size:12px; }
pre { white-space:pre-wrap; background:var(--bg); border:1px solid var(--border); border-radius:8px;
  padding:12px; font-size:13px; overflow-x:auto; }
nav a { margin-right:14px; text-decoration:none; font-size:14px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:8px 0 20px; }
.tile { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
.tile .k { font-size:12px; color:var(--muted); } .tile .v { font-size:20px; font-weight:600; margin-top:2px; }
.tile.ok .v { color:var(--ok); } .tile.warn .v { color:var(--warn); } .tile.bad .v { color:var(--bad); }
.brief { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:4px 18px 16px; }
.brief h2 { font-size:18px; } .brief h3 { font-size:15px; color:var(--accent); margin-bottom:4px; }
.brief h4 { font-size:13px; color:var(--muted); margin:10px 0 2px; }
.brief ul { margin:4px 0; padding-left:20px; } .brief li { margin:2px 0; }
.brief blockquote { border-left:3px solid var(--warn); margin:8px 0; padding:2px 12px; color:var(--muted); }
.wikilink { color:var(--accent); } code { background:var(--bg); padding:1px 5px; border-radius:4px; font-size:.9em; }
.actions { display:flex; gap:10px; flex-wrap:wrap; margin:16px 0; }
.ask textarea { min-height:44px; } .answer { background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:12px 16px; margin-top:12px; } .section-title { font-size:14px; color:var(--muted);
  margin:24px 0 6px; border-bottom:1px solid var(--border); padding-bottom:6px; }
"""


_FENCE_RE = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s*(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
# 表格分隔行：至少要有一列 `---`，允许首尾竖线与对齐冒号。
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_INDENTED_RE = re.compile(r"^\s{2,}")
# CJK（含全角标点）：软换行拼接时中文之间不插空格，否则会出现「收口； 相关方培训」这种缝。
_CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def _inline_md(text: str) -> str:
    """行内 Markdown → HTML（先转义，再处理 **粗体** / *斜体* / `代码` / [[目标|显示名]]）。"""
    html = escape(text)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"(^|[^*])\*([^*\n]+?)\*", r"\1<em>\2</em>", html)
    html = re.sub(r"`([^`]+?)`", r"<code>\1</code>", html)
    return re.sub(r"\[\[([^\]]+?)\]\]", _wikilink_md, html)


def _wikilink_md(match: re.Match[str]) -> str:
    """[[目标|显示名]] → 只显示「显示名」（目标留在 title）；[[目标]] → 显示目标。"""
    inner = match.group(1)
    target, _, label = inner.partition("|")
    shown = label if label.strip() else target
    return f'<span class="wikilink" title="{target}">{shown}</span>'


# 判断边界字符时要跳过行内标记（**、`、空白），否则「…HII**、」接「**「活满」…」会在
# 两个 ** 之间判定成非中文，缝出一个空格。
_EDGE_LEAD_RE = re.compile(r"^[\s*`]+")
_EDGE_TAIL_RE = re.compile(r"[\s*`]+$")


def _cjk_boundary(left: str, right: str) -> bool:
    a = _EDGE_TAIL_RE.sub("", left)[-1:]
    b = _EDGE_LEAD_RE.sub("", right)[:1]
    return bool(a) and bool(b) and bool(_CJK_RE.search(a)) and bool(_CJK_RE.search(b))


def _join_soft(parts: list[str]) -> str:
    """按 Markdown 软换行拼接多行：中文接中文直接连，其余补一个空格。"""
    out = ""
    for part in parts:
        if not out:
            out = part
            continue
        out += part if _cjk_boundary(out, part) else " " + part
    return out


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        "|" in lines[index]
        and index + 1 < len(lines)
        and bool(_TABLE_SEP_RE.match(lines[index + 1]))
    )


def _is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    return bool(
        _FENCE_RE.match(line)
        or _HEADING_RE.match(line)
        or _QUOTE_RE.match(line)
        or _LIST_ITEM_RE.match(line)
        or _is_table_start(lines, index)
    )


def _split_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _list_item_content(item: dict[str, object]) -> str:
    text = str(item["text"])
    task = _TASK_RE.match(text)
    if task:
        done = task.group(1).lower() == "x"
        cls = "task done" if done else "task"
        return f'<span class="{cls}">{"☑" if done else "☐"}</span> {_inline_md(task.group(2))}'
    return _inline_md(text)


def _collect_list(lines: list[str], start: int) -> tuple[list[dict[str, object]], int]:
    """收一段列表：项本身 + 缩进续行（Markdown 的惰性续行，如「2. …」下面那行说明）。"""
    items: list[dict[str, object]] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            break
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(
                {
                    "indent": len(match.group(1)),
                    "ordered": match.group(2)[0].isdigit(),
                    "text": match.group(3),
                }
            )
            i += 1
            continue
        if items and _INDENTED_RE.match(line) and not _is_block_start(lines, i):
            items[-1]["text"] = _join_soft([str(items[-1]["text"]), line.strip()])
            i += 1
            continue
        break
    return items, i


def _render_items(items: list[dict[str, object]]) -> str:
    """渲染嵌套列表。

    ``reclose``：嵌套列表要落在父项 ``<li>`` **内部**，所以开嵌套列表前先把父项的 ``</li>``
    摘下来，等嵌套列表收尾再补回去（否则会渲染成 ``<li>外层</li><ul>…</ul>`` 这种兄弟结构）。
    """
    html = ""
    stack: list[dict[str, object]] = []

    def open_list(ordered: bool, indent: int) -> None:
        nonlocal html
        reclose = False
        if stack and html.endswith("</li>"):
            html = html[: -len("</li>")]
            reclose = True
        html += "<ol>" if ordered else "<ul>"
        stack.append({"ordered": ordered, "indent": indent, "reclose": reclose})

    def close_list() -> None:
        nonlocal html
        top = stack.pop()
        html += "</ol>" if top["ordered"] else "</ul>"
        if top["reclose"]:
            html += "</li>"

    for item in items:
        while stack and int(item["indent"]) < int(stack[-1]["indent"]):  # type: ignore[call-overload]
            close_list()
        top = stack[-1] if stack else None
        if top is None or int(item["indent"]) > int(top["indent"]):  # type: ignore[call-overload]
            open_list(bool(item["ordered"]), int(item["indent"]))  # type: ignore[call-overload]
        elif bool(top["ordered"]) != bool(item["ordered"]):
            close_list()
            open_list(bool(item["ordered"]), int(item["indent"]))  # type: ignore[call-overload]
        html += f"<li>{_list_item_content(item)}</li>"
    while stack:
        close_list()
    return html


def md_to_html(md: str) -> str:
    """Markdown 子集 → HTML（标题 / 段落 / 有序·无序·任务列表 / 表格 / 引用 / 代码块）。

    与前端 ``web/src/md.ts::mdToHtml`` **同规则**：改一边必须改另一边。
    """
    lines = str(md or "").split("\n")
    parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if _FENCE_RE.match(line):
            lang = line.strip().lstrip("`").strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # 跳过收尾 fence（缺失时也不吞掉后面的内容）
            cls = f' class="lang-{escape(lang)}"' if lang else ""
            parts.append(f"<pre><code{cls}>{escape(chr(10).join(body))}</code></pre>")
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = min(len(heading.group(1)), 3) + 1
            parts.append(f"<h{level}>{_inline_md(heading.group(2))}</h{level}>")
            i += 1
            continue

        if _QUOTE_RE.match(line):
            body = []
            while i < len(lines) and _QUOTE_RE.match(lines[i]):
                body.append(_QUOTE_RE.match(lines[i]).group(1))  # type: ignore[union-attr]
                i += 1
            parts.append(f"<blockquote><p>{_inline_md(_join_soft(body))}</p></blockquote>")
            continue

        if _is_table_start(lines, i):
            head = _split_row(line)
            i += 2
            rows: list[list[str]] = []
            # 行里含 `|` 不等于还是表格行：紧跟其后的列表项（尤其 [[目标|显示名]]）不能被吞成一行。
            while (
                i < len(lines)
                and lines[i].strip()
                and "|" in lines[i]
                and not _is_block_start(lines, i)
            ):
                rows.append(_split_row(lines[i]))
                i += 1
            head_html = "".join(f"<th>{_inline_md(cell)}</th>" for cell in head)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{_inline_md(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            parts.append(
                f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"
            )
            continue

        if _LIST_ITEM_RE.match(line):
            items, nxt = _collect_list(lines, i)
            parts.append(_render_items(items))
            i = nxt
            continue

        # 段落：连续的非空、非块起始行合并成一段（Markdown 的软换行）。
        para: list[str] = []
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines, i):
            para.append(lines[i].strip())
            i += 1
        if not para:
            para.append(line.strip())
            i += 1
        parts.append(f"<p>{_inline_md(_join_soft(para))}</p>")
    return "\n".join(parts)


def _route_options(current: RouteTarget | None) -> str:
    opts = ['<option value="">（未定）</option>']
    for route in RouteTarget:
        sel = " selected" if route is current else ""
        opts.append(f'<option value="{route.value}"{sel}>{_ROUTE_LABELS[route]}</option>')
    return "".join(opts)


def _card(entry: ReviewEntry) -> str:
    c = entry.candidate
    label, cls = _DECISION_BADGE[c.decision]
    cid = escape(c.candidate_id)
    desc = escape(c.description)
    actionable = c.is_actionable()
    warn = (
        ""
        if actionable
        else '<div class="not-actionable">⚠ 依据或目标项目缺失，暂不可批准写回</div>'
    )
    err = (
        f'<div class="not-actionable">应用出错：{escape(entry.apply_error)}</div>'
        if entry.apply_error
        else ""
    )
    note = escape(entry.note_link)
    route_label = _ROUTE_LABELS[c.route] if c.route else ""
    approve_label = (
        f"✓ 批准 → {escape(route_label)}" if route_label else "✓ 批准（先在「修改」里选落点）"
    )
    approve_disabled = "" if c.route else " disabled"
    return f"""
    <div class="card {cls}" id="c-{cid}">
      <p class="desc">{desc}</p>
      <span class="kind">{escape(c.kind.value)}</span>
      <span class="badge {cls}">{label}</span>
      {warn}{err}
      <div class="meta">目标：{escape(c.target_project if c.target_project and c.target_project != "unresolved" else "未定")} ·
        落点：{escape(_ROUTE_LABELS.get(c.route, "（未定）") if c.route else "（未定）")} ·
        截止：{escape(c.due_date or "—")} · 依据：{escape(c.evidence.anchor if c.evidence and c.evidence.anchor else "—")}</div>
      <div class="meta">来源：{note}</div>
      <div class="row">
        <form method="post" action="/review/decide"><input type="hidden" name="candidate_id" value="{cid}">
          <input type="hidden" name="decision" value="approved"><button class="ok" type="submit"{approve_disabled}>{approve_label}</button></form>
        <form method="post" action="/review/decide"><input type="hidden" name="candidate_id" value="{cid}">
          <input type="hidden" name="decision" value="rejected"><button class="bad" type="submit">✗ 拒绝</button></form>
        <form method="post" action="/review/decide"><input type="hidden" name="candidate_id" value="{cid}">
          <input type="hidden" name="decision" value="pending"><button type="submit">↺ 待确认</button></form>
      </div>
      <details><summary>修改</summary>
        <form method="post" action="/review/edit">
          <input type="hidden" name="candidate_id" value="{cid}">
          <textarea name="description">{desc}</textarea>
          <div class="grid">
            <label>目标项目</label><input name="target_project" value="{escape(c.target_project or "")}">
            <label>route</label><select name="route">{_route_options(c.route)}</select>
            <label>截止日期</label><input name="due_date" value="{escape(c.due_date or "")}" placeholder="YYYY-MM-DD">
          </div>
          <div class="row"><button class="primary" type="submit">保存修改</button></div>
        </form>
      </details>
    </div>"""


def render_review(
    entries: list[ReviewEntry], errors: list[str], *, message: str | None = None
) -> str:
    """渲染审批面板首页。"""
    pending = sum(1 for e in entries if e.candidate.decision is CandidateDecision.PENDING)
    blocks: list[str] = []
    if message:
        blocks.append(f'<div class="msg">{escape(message)}</div>')
    if errors:
        blocks.append(
            '<div class="msg err">审批页解析错误：<br>'
            + "<br>".join(escape(e) for e in errors)
            + "</div>"
        )

    groups: dict[tuple[str, str], list[ReviewEntry]] = {}
    for entry in entries:
        groups.setdefault((entry.meeting_date, entry.meeting_title), []).append(entry)
    if not entries:
        blocks.append(
            '<div class="msg">暂无待确认候选。运行 <code>wb review refresh</code> 生成。</div>'
        )
    for (mdate, title), grouped in sorted(groups.items()):
        blocks.append(f'<div class="meeting">{escape(mdate)} · {escape(title)}</div>')
        blocks.extend(_card(e) for e in grouped)

    body = "\n".join(blocks)
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>会议审批 · SummitWorkbench</title><style>{_STYLE}</style></head><body>
<header><h1>会议审批</h1>{_nav("review")}<span class="badge pending">{pending} 条待确认</span>
<span class="spacer"></span>
<form method="get" action="/review/plan"><button type="submit">预演应用</button></form>
</header><main>{body}</main></body></html>"""


def _nav(active: str) -> str:
    def link(href: str, label: str, key: str) -> str:
        mark = "→ " if key == active else ""
        return f'<a href="{href}">{mark}{label}</a>'

    return "<nav>" + link("/", "看板", "home") + link("/review", "审批", "review") + "</nav>"


def _status_tiles(status: StatusReport) -> str:
    health = "🟡 有积压" if status.backlog.active else "🟢 正常"
    hcls = "warn" if status.backlog.active else "ok"
    cost = f"{status.usage.estimated_cost:.4f} {status.usage.currency}"
    over = status.budget.over_soft_limit
    tiles = [
        ("健康度", health, hcls),
        ("待确认候选", str(status.backlog.count), "warn" if status.backlog.count else ""),
        (f"本月费用（{status.month}）", cost, "bad" if over else ""),
        ("已入第二大脑", str(status.succeeded), ""),
        (
            "失败/不可用",
            f"{status.count(ProcessingState.FAILED)}/{status.count(ProcessingState.UNAVAILABLE)}",
            "bad" if status.count(ProcessingState.FAILED) else "",
        ),
    ]
    cells = "".join(
        f'<div class="tile {cls}"><div class="k">{escape(k)}</div>'
        f'<div class="v">{escape(v)}</div></div>'
        for k, v, cls in tiles
    )
    return f'<div class="tiles">{cells}</div>'


def render_dashboard(
    status: StatusReport,
    day: str,
    brief_md: str | None,
    *,
    ask_question: str = "",
    ask_answer_html: str | None = None,
    message: str | None = None,
) -> str:
    """看板首页：状态速览 + 今日简报 + 一键触发 + 问答。"""
    msg = f'<div class="msg">{escape(message)}</div>' if message else ""
    if brief_md:
        brief_html = f'<div class="brief">{md_to_html(brief_md)}</div>'
    else:
        brief_html = (
            '<div class="msg">今日简报尚未生成。点下方「生成今日简报」或等 08:00 自动生成。</div>'
        )
    answer = f'<div class="answer">{ask_answer_html}</div>' if ask_answer_html else ""
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>看板 · SummitWorkbench</title><style>{_STYLE}</style></head><body>
<header><h1>SummitWorkbench</h1>{_nav("home")}<span class="spacer"></span>
<span class="badge">{escape(day)}</span></header>
<main>
{msg}
{_status_tiles(status)}
<div class="actions">
  <form method="post" action="/run/brief"><button class="primary" type="submit">↻ 生成今日简报</button></form>
  <form method="post" action="/run/weekly"><button type="submit">生成上周复盘</button></form>
</div>
<div class="section-title">今日简报</div>
{brief_html}
<div class="section-title">问第二大脑</div>
<form class="ask" method="post" action="/ask">
  <textarea name="question" placeholder="例如：网课项目最近的决策是什么？">{escape(ask_question)}</textarea>
  <div class="actions"><button class="primary" type="submit">提问</button></div>
</form>
{answer}
</main></body></html>"""


def render_plan(plan_text: str, executed: bool) -> str:
    """渲染 dry-run 计划或已应用结果页。"""
    title = "已应用" if executed else "预演计划（未写入）"
    action = (
        ""
        if executed
        else """
      <form method="post" action="/review/apply">
        <button class="primary" type="submit">确认应用（写回项目/建任务/归档拒绝项）</button></form>"""
    )
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · SummitWorkbench</title><style>{_STYLE}</style></head><body>
<header><h1>{title}</h1><span class="spacer"></span>
<form method="get" action="/review"><button type="submit">← 返回审批</button></form></header>
<main><pre>{escape(plan_text)}</pre>{action}</main></body></html>"""
