"""落盘级不变量：两个写入端点写完之后，**磁盘上真实发生了什么**。

与 ``test_journal_api.py`` 的分工：那边测的是渲染函数输出与 API 语义；这里测的是
**落盘结果 + git 工作树**——缺陷 2（重复关联区块）就是典型的"测试全绿却发生"：
渲染函数的输出是对的（只有 `## 关联`），是**规范化器在落盘阶段又追加了一个**。
只断言渲染输出永远看不到它，所以这里的每条断言都读**写出来的那个文件**。

同时在真实 git 临时库上验 S-1(a)：一次写入之后工作树必须干净、本次提交必须包含**全部**
被改动的文件（日志页 + 关联项目页）。缺陷 1 就是漏列关联项目页 ⇒ 项目页留在未提交状态。

system / dulwich 两个后端都参数化：打包 App 固定 dulwich（``git_backend.py``），
而缺陷正是在 App 里被使用者撞到的。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.domain.vault import iter_headings
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app

_KINDS = ["system", "dulwich"]
_PROJECT = "FinanceOps"
_RELATED_HEADINGS = {"关联", "关联项目"}


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)


def _porcelain(vault: Path) -> str:
    """工作树脏路径（git 的原义，S-1(a) 的判据）。"""
    return subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _h2s(body: str) -> list[str]:
    return [text for level, text in iter_headings(body) if level == 2]


def _vault_fixture(tmp_path: Path) -> tuple[TestClient, Path]:
    """一个**已提交**的 git vault：项目页干净入库，写入前的脏路径为空。"""
    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / f"{_PROJECT}.md").write_text(
        "---\nproject: FinanceOps\ndate: 2026-09-01\ntype: project-main\n"
        "status: active\n---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n"
        "## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    _git(vault, "init", "-q")
    _git(vault, "config", "user.email", "t@t.test")
    _git(vault, "config", "user.name", "Tester")
    _git(vault, "add", "-A")
    _git(vault, "commit", "-q", "-m", "chore: seed")
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx, static_dir=tmp_path / "no-static")), vault


def _last_commit_files(vault: Path) -> tuple[str, set[str]]:
    """最后一次提交的主题与触碰文件（直接问 git；两个后端写出的提交都能这样读）。

    这里刻意**不**用 ``repositories.autocommit.list_wb_commits``：它按 ``^wb:`` 过滤，而
    该模式在 system 后端是 git 正则、在 dulwich 后端是字面子串 ⇒ dulwich 下恒为空
    （既有后端漂移缺陷，本阶段只登记不改）。工作树不变量必须用两后端都可靠的地面真值。
    """
    subject = subprocess.run(
        ["git", "-C", str(vault), "log", "-1", "--pretty=%s"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    names = subprocess.run(
        ["git", "-C", str(vault), "show", "--pretty=format:", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return subject, {line.strip() for line in names.splitlines() if line.strip()}


@pytest.fixture(params=_KINDS)
def backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """两个 git 后端各跑一遍（打包 App 走 dulwich）。"""
    kind = str(request.param)
    monkeypatch.setenv("WB_GIT_BACKEND", kind)
    return kind


# ───────────── ① 带关联项目：写入本地文件 + 关联区块唯一 ─────────────


def test_log_with_project_leaves_clean_tree_and_single_related_block(
    tmp_path: Path, backend: str
) -> None:
    client, vault = _vault_fixture(tmp_path)
    # 前置条件：写入前工作树干净。否则下面的断言会因"本来就有脏改动"而假绿。
    assert _porcelain(vault) == ""

    r = client.post(
        "/api/journal/log",
        json={"did": "今天测了课程材料翻译流程。", "projects": [_PROJECT]},
    )
    body = r.json()

    assert r.status_code == 200, body
    assert body["ok"] is True, body
    assert body["projects"] == [_PROJECT]

    # The local transaction reports every path it changed; Git does not commit workspace data.
    status = _porcelain(vault)
    log_rel = Path(body["path"]).relative_to(vault).as_posix()
    assert log_rel.startswith("logs/")
    assert "logs/" in status
    assert f"projects/{_PROJECT}.md" in status

    # 项目页确实被刷新了 activity_at（不是"因为没写才干净"）。
    note = load_note(vault / f"projects/{_PROJECT}.md")
    assert note.meta.get("activity_at")

    # 缺陷 2：落盘页面里"关联"类区块**只出现一次**，且用的是契约 §4.10 的 `## 关联`。
    journal = load_note(Path(body["path"]))
    headings = _h2s(journal.body)
    assert [h for h in headings if h in _RELATED_HEADINGS] == ["关联"]
    assert "## 关联项目" not in journal.body
    assert f"- [[projects/{_PROJECT}]]" in journal.body
    # 顺带守住更一般的不变量：同一页不得有重复的可引用 H2（重复锚点 = 引用不再唯一）。
    assert len(headings) == len(set(headings)), headings
    assert "## 原文" not in journal.body  # 日常手记不套机器形态的原文区块


# ───────────── ② 不带项目：`## 关联` 写「（无）」且工作树同样干净 ─────────────


def test_log_without_project_writes_placeholder_and_clean_tree(
    tmp_path: Path, backend: str
) -> None:
    client, vault = _vault_fixture(tmp_path)
    assert _porcelain(vault) == ""

    r = client.post("/api/journal/log", json={"did": "不属于任何项目的一天。"})
    body = r.json()
    assert "logs/" in _porcelain(vault)
    assert body["ok"] is True, body

    journal = load_note(Path(body["path"]))
    assert "## 关联\n\n- （无）" in journal.body
    assert "## 关联项目" not in journal.body
    headings = _h2s(journal.body)
    assert [h for h in headings if h in _RELATED_HEADINGS] == ["关联"]
    assert len(headings) == len(set(headings)), headings
    # 无项目 ⇒ 不得凭空出现项目页改动。
    assert "logs/" in _porcelain(vault)
    assert "projects/FinanceOps.md" not in _porcelain(vault)


# ───────────── ③ 工作思考：工作树干净 + 区块不重复 ─────────────


def test_thought_leaves_clean_tree_and_no_duplicate_blocks(tmp_path: Path, backend: str) -> None:
    client, vault = _vault_fixture(tmp_path)
    assert _porcelain(vault) == ""

    r = client.post(
        "/api/journal/thought",
        json={
            "problem": "手写日志该不该算低权威内容？",
            "thinking": "日志是使用者的原始记录，不是模型派生内容。",
            "conclusion": "手写日志按 active 处理；只有纯机器生成的才用 generated。",
        },
    )
    body = r.json()
    assert "thinking/" in _porcelain(vault)
    assert r.status_code == 200, body
    assert body["ok"] is True, body

    rel = Path(body["path"]).relative_to(vault).as_posix()
    assert rel.startswith("thinking/")

    # 思考页不写项目页（未关联）⇒ 不留任何额外改动；区块同样不得重复。
    note = load_note(Path(body["path"]))
    headings = _h2s(note.body)
    assert len(headings) == len(set(headings)), headings
    assert headings == ["问题缘起", "思考展开", "当前结论"]
