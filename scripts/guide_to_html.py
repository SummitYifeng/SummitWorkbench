#!/usr/bin/env python3
"""把 Markdown 使用指南转成自包含 HTML（内联 CSS，无外部依赖，可离线阅读/打印）。

用法：
    python scripts/guide_to_html.py docs/product/WEB_USAGE_GUIDE.md out.html

支持子集：标题(#~####)、无序列表、引用、围栏代码块、分隔线、行内加粗/代码。
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

_CSS = """
:root { color-scheme: light dark; --fg:#1c2024; --muted:#6b7280; --bg:#f6f7f9; --card:#fff;
  --border:#e3e6ea; --accent:#2f6fed; --accent-soft:#e8efff; --code-bg:#eef1f5; }
@media (prefers-color-scheme: dark) { :root { --fg:#e6e8ec; --muted:#9aa1ab; --bg:#131519;
  --card:#1d2026; --border:#2c3038; --accent:#6ea2ff; --accent-soft:#1c2740; --code-bg:#23262e; } }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  margin: 0; background: var(--bg); color: var(--fg); line-height: 1.7; -webkit-font-smoothing: antialiased; }
header { position: sticky; top: 0; background: color-mix(in srgb, var(--card) 90%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--border); padding: 14px 24px;
  display: flex; align-items: center; gap: 12px; }
.logo { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center;
  background: linear-gradient(135deg, var(--accent), #7c5cff); color: #fff; font-weight: 700; font-size: 13px; }
header h1 { font-size: 16px; margin: 0; }
header .sub { font-size: 12px; color: var(--muted); margin: 0; }
main { max-width: 780px; margin: 0 auto; padding: 28px 24px 60px; }
h1 { font-size: 26px; margin: 6px 0 18px; }
h2 { font-size: 19px; margin: 30px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); color: var(--accent); }
h3 { font-size: 16px; margin: 22px 0 8px; }
h4 { font-size: 14px; margin: 18px 0 6px; color: var(--muted); }
p { margin: 10px 0; }
ul { margin: 10px 0; padding-left: 22px; }
li { margin: 6px 0; }
blockquote { border-left: 3px solid var(--accent); margin: 14px 0; padding: 8px 16px;
  background: var(--accent-soft); border-radius: 0 8px 8px 0; color: var(--muted); }
code { background: var(--code-bg); border: 1px solid var(--border); border-radius: 5px;
  padding: 1px 6px; font-size: 0.88em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px;
  overflow-x: auto; margin: 14px 0; }
pre code { background: none; border: none; padding: 0; font-size: 13px; line-height: 1.6; }
strong { color: var(--fg); }
hr { border: none; border-top: 1px solid var(--border); margin: 26px 0; }
footer { max-width: 780px; margin: 0 auto; padding: 0 24px 40px; color: var(--muted); font-size: 12.5px; }
"""

_FENCE = chr(96) * 3


def _inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+?)`", r"<code>\1</code>", t)
    return t


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_list = False
    n = len(lines)
    i = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            close_list()
            i += 1
            continue
        if stripped.startswith(_FENCE):
            close_list()
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith(_FENCE):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue
        if stripped == "---":
            close_list()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("#### "):
            close_list(); out.append(f"<h4>{_inline(stripped[5:])}</h4>"); i += 1; continue
        if stripped.startswith("### "):
            close_list(); out.append(f"<h3>{_inline(stripped[4:])}</h3>"); i += 1; continue
        if stripped.startswith("## "):
            close_list(); out.append(f"<h2>{_inline(stripped[3:])}</h2>"); i += 1; continue
        if stripped.startswith("# "):
            close_list(); out.append(f"<h1>{_inline(stripped[2:])}</h1>"); i += 1; continue
        if stripped.startswith("> "):
            close_list()
            quote: list[str] = []
            while i < n and lines[i].strip().startswith("> "):
                quote.append(_inline(lines[i].strip()[2:]))
                i += 1
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            continue
        if stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + _inline(stripped[2:]) + "</li>")
            i += 1
            continue
        close_list()
        out.append(f"<p>{_inline(stripped)}</p>")
        i += 1
    close_list()
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：guide_to_html.py <input.md> <output.html>", file=sys.stderr)
        return 2
    src = Path(argv[0])
    dst = Path(argv[1])
    if not src.is_file():
        print(f"输入不存在：{src}", file=sys.stderr)
        return 2
    md = src.read_text(encoding="utf-8")
    body = convert(md)
    title = src.stem
    doc = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <span class="logo">SW</span>
  <div><h1>{html.escape(title)}</h1>
  <p class="sub">SummitWorkbench · 本地运行（127.0.0.1）</p></div>
</header>
<main>
{body}
</main>
<footer>自包含 HTML（无外部依赖），可离线阅读或打印 · 仓库维护版：{html.escape(str(src))}</footer>
</body>
</html>
"""
    dst.write_text(doc, encoding="utf-8")
    print(f"OK {dst} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
