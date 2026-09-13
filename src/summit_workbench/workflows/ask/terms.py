"""查询词提取：把自然语言问题变成可用于 FTS5(trigram) 与 BM25 的检索词。

中文没有空格，而本产品**不引入分词依赖**（硬边界：不加第三方库）。这里的做法是：

- 拉丁/数字 token：整词保留（长度 ≥ 2）；
- 中文连续片段（run）：
  - 片段不长（≤ 6 字）时整段作为一个词（例如「商标共识规范」）；
  - 片段很长时（通常是整句），取全部 **3-gram** 滑窗。例如「请告诉我当前我们达成的商标共识规范
    是什么」→「请告诉」「告诉我」…「商标共」「标共识」「共识规」「识规范」…，让「商标共识」这类
    子串仍能命中，同时不依赖任何词典。

3-gram 是 FTS5 `trigram` tokenizer 的最小匹配单位，因此检索词与索引侧的切分口径天然一致。
"""

from __future__ import annotations

import re

_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
RUN_RE = re.compile(rf"[{_CJK}]+|[A-Za-z0-9][A-Za-z0-9._+#-]*")
TRIGRAM = 3
MAX_TERMS = 64
MIN_LATIN = 2


def query_terms(query: str) -> list[str]:
    """返回去重保序（长词在前）的检索词列表；空查询返回空列表。"""
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        key = term.casefold()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)

    for match in RUN_RE.finditer(query):
        token = match.group(0)
        if re.fullmatch(rf"[{_CJK}]+", token):
            if len(token) <= 6:
                add(token)
            else:
                for index in range(len(token) - TRIGRAM + 1):
                    add(token[index : index + TRIGRAM])
        elif len(token) >= MIN_LATIN:
            add(token)

    terms.sort(key=len, reverse=True)
    return terms[:MAX_TERMS]


def fts_query(terms: list[str]) -> str:
    """把检索词拼成 FTS5 MATCH 表达式（短语 + OR）；剔除 trigram 无法匹配的短词。"""
    usable = [t for t in terms if len(t) >= TRIGRAM]
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in usable)


def short_terms(terms: list[str]) -> list[str]:
    """trigram 索引无法匹配、只能靠子串扫描兜底的短词。"""
    return [t for t in terms if len(t) < TRIGRAM]
