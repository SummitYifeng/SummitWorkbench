"""收件箱提升（契约 §10）：解析/移除的纯逻辑 + 三种目标的**落盘级**不变量。

`test_inbox_parsing.py` 式的纯函数断言在这里是必要的但**不够**：缺陷 2 的教训是
"渲染/解析对了，落盘阶段又出问题"。所以本文件的主力是走**真实 router + 临时 git 库**，
断言磁盘上真实发生了什么：

- 目标页内容正确；
- 条目被移出收件箱，且**不留占位行 / 不产生双空行**；
- **工作树干净**（S-1(a)：一次写入之后不留未提交改动）；
- 本次提交包含 inbox 与目标页（目标页确实变了时）。

以及成本约定：**列表渲染（`GET /api/inbox`）绝不调用模型**——这条用"把分类器换成会炸的
替身，读端点仍必须成功"来守。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.repositories.inbox import (
    parse_inbox_entries,
    remove_inbox_entry,
    suggest_promotion,
)
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app

PROJECT = "FinanceOps"


# ───────────────────────── 纯逻辑：解析 / 移除 / 启发式 ─────────────────────────


def _inbox_text(entries: list[tuple[str, list[str]]], *, tail: str = "") -> str:
    """按写入口（`writeback._append_under_heading`）的产出形状拼一份 inbox。"""
    blocks = "".join(
        f"- [ ] {text}\n" + "".join(f"  <!-- {marker} -->\n" for marker in markers) + "\n"
        for text, markers in entries
    )
    return (
        "---\ndate: 2026-09-19\ntype: inbox\nstatus: active\nproject: global\n---\n\n"
        f"# 全局收件箱（inbox）\n\n## 待处理条目\n\n{blocks}{tail}"
    ).rstrip() + "\n"


_TWO_ENTRIES = [
    (
        "把翻译流程定稿 #it-development",
        ["wb-candidate: web-a", "wb-capture-project: it-development"],
    ),
    (
        "给 Coach 发邮件",
        ["wb-candidate: web-b", "wb-capture-kind: task", "wb-capture-due: 2026-09-25"],
    ),
]


def test_parse_reads_body_markers_and_stable_ids() -> None:
    entries = parse_inbox_entries(_inbox_text(_TWO_ENTRIES))
    assert [e.text for e in entries] == [t for t, _ in _TWO_ENTRIES]
    assert [e.id for e in entries] == ["web-a", "web-b"]
    assert entries[0].project == "it-development" and entries[0].due is None
    assert entries[1].kind == "task" and entries[1].due == "2026-09-25"
    # 行区间正好覆盖「复选框行 + 标记行」，供精确移除
    lines = _inbox_text(_TWO_ENTRIES).splitlines()
    assert lines[entries[0].start] == "- [ ] 把翻译流程定稿 #it-development"
    assert lines[entries[0].stop - 1].strip() == "<!-- wb-capture-project: it-development -->"


def test_parse_gives_manual_entries_a_stable_id() -> None:
    """手工写的条目（没有 wb-candidate）也要有稳定标识：同正文同序号 ⇒ 同 id。"""
    text = "## 待处理条目\n\n- [ ] 手工写的一条\n\n- [ ] 手工写的一条\n"
    first = parse_inbox_entries(text)
    again = parse_inbox_entries(text)
    assert [e.id for e in first] == [e.id for e in again]
    assert len({e.id for e in first}) == 2  # 同正文的两条不能撞 id


def test_parse_rejects_duplicate_region() -> None:
    """重复 `## 待处理条目` ⇒ 拒绝解析（与写入口同一纪律：写/删哪一节必须唯一）。"""
    with pytest.raises(ValueError, match="重复区块"):
        parse_inbox_entries("## 待处理条目\n\n- [ ] a\n\n## 待处理条目\n\n- [ ] b\n")


def test_remove_takes_the_entry_and_its_separator_blank() -> None:
    """逐条移除：中间条 / 末条 / 唯一条，都不留占位行、不产生双空行。"""
    text = _inbox_text(_TWO_ENTRIES)
    entries = parse_inbox_entries(text)

    after_first = remove_inbox_entry(text, entries[0])
    assert "把翻译流程定稿" not in after_first
    assert "给 Coach 发邮件" in after_first
    assert "\n\n\n" not in after_first  # 不留双空行

    after_second = remove_inbox_entry(text, entries[1])
    assert "给 Coach 发邮件" not in after_second
    assert "把翻译流程定稿" in after_second
    assert "\n\n\n" not in after_second

    only = _inbox_text([_TWO_ENTRIES[0]])
    stripped = remove_inbox_entry(only, parse_inbox_entries(only)[0])
    assert stripped.endswith("## 待处理条目\n")  # 空收件箱：区块留着，行没了，也没空行
    assert parse_inbox_entries(stripped) == []


def test_remove_keeps_a_following_section_separated() -> None:
    """收件箱区后面还跟着别的 `##` 区块时，分隔空行不能被吞掉。"""
    text = _inbox_text(_TWO_ENTRIES, tail="## 其它\n\n正文\n")
    entries = parse_inbox_entries(text)
    stripped = remove_inbox_entry(text, entries[1])
    assert "## 其它\n\n正文" in stripped
    assert stripped.endswith("\n")


def test_suggest_is_local_and_explains_itself() -> None:
    """本地启发式：有截止 → 待办；有 #项目 → 项目页；其余 → 思考。"""
    due = parse_inbox_entries(_inbox_text(_TWO_ENTRIES))[1]
    project = parse_inbox_entries(_inbox_text(_TWO_ENTRIES))[0]
    plain = parse_inbox_entries(_inbox_text([("随手记一句想法", [])]))[0]
    assert suggest_promotion(due)[0] == "feishu-task"
    assert suggest_promotion(project)[0] == "project"
    assert suggest_promotion(plain)[0] == "thought"
    assert all(suggest_promotion(e)[1] for e in (due, project, plain))  # 每条都给理由


# ───────────────────── 落盘级：真实 router + 临时 git 库 ─────────────────────


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)


def _porcelain(vault: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _commit_files(vault: Path) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(vault), "show", "--pretty=format:", "--name-only", "-z", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # -z：中文路径不被 core.quotepath 转义（否则集合里是 "\350\257\276…"）
    return {name for name in out.split("\0") if name.strip()}


def _client(tmp_path: Path, *, inbox_text: str | None = None) -> tuple[TestClient, Path]:
    """一个**已提交**的 git vault：项目页 + 两条收件箱条目（写入前工作树干净）。"""
    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / f"{PROJECT}.md").write_text(
        f"---\nproject: {PROJECT}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        "---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n\n## 跟进事项\n",
        encoding="utf-8",
    )
    (vault / "inbox.md").write_text(
        inbox_text if inbox_text is not None else _inbox_text(_TWO_ENTRIES), encoding="utf-8"
    )
    # 与真实库一致：`_signals/` 是机器状态、被忽略（否则 outbox 账本会让工作树"变脏"，
    # 那是环境不真实，不是缺陷）。契约 §0 / 闸门 S-1(b)。
    (vault / ".gitignore").write_text("_signals/\n", encoding="utf-8")
    _git(vault, "init", "-q")
    _git(vault, "config", "user.email", "t@t.test")
    _git(vault, "config", "user.name", "Tester")
    _git(vault, "add", "-A")
    _git(vault, "commit", "-q", "-m", "chore: seed")
    ctx = WebContext(vault_dir=vault, work_root=tmp_path, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx, static_dir=tmp_path / "no-static")), vault


def test_read_endpoint_never_calls_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**成本约定**：列表渲染（`GET /api/inbox`）绝不调模型。

    变异靶（成本回归）：把分类/建议挪进读端点，本用例立刻红——把分类器换成会炸的替身，
    读端点必须照常返回条目。
    """
    client, _vault = _client(tmp_path)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("读端点不得调用模型")

    # 路由模块内是 `from … import classify_capture` 的**已绑定名**，必须打在路由模块上
    monkeypatch.setattr("summit_workbench.webapp.routers.inbox.classify_capture", boom)
    monkeypatch.setattr("summit_workbench.webapp.model_config._load_model_config_for_context", boom)

    body = client.get("/api/inbox").json()
    assert body["ok"] is True and body["pending"] == 2
    assert [item["id"] for item in body["items"]] == ["web-a", "web-b"]
    assert body["items"][0]["suggested_target"] == "project"
    assert body["items"][1]["suggested_target"] == "feishu-task"


def test_promote_to_project_next_step(tmp_path: Path) -> None:
    """① 项目页条目：写进 `## 下一步`，条目移出收件箱，一个提交、工作树干净。"""
    client, vault = _client(tmp_path)
    assert _porcelain(vault) == ""

    body = client.post(
        "/api/inbox/promote", json={"id": "web-a", "target": "project", "project": PROJECT}
    ).json()
    assert body["ok"] is True, body

    assert _porcelain(vault) == ""
    assert "把翻译流程定稿" in (vault / "projects" / f"{PROJECT}.md").read_text(encoding="utf-8")
    remaining = (vault / "inbox.md").read_text(encoding="utf-8")
    assert "把翻译流程定稿" not in remaining
    assert "给 Coach 发邮件" in remaining  # 另一条原样不动
    assert parse_inbox_entries(remaining) and len(parse_inbox_entries(remaining)) == 1
    assert "\n\n\n" not in remaining
    files = _commit_files(vault)
    assert {"inbox.md", f"projects/{PROJECT}.md"} <= files


def test_promote_leaves_exactly_one_blank_line_before_the_next_block(tmp_path: Path) -> None:
    """回归守卫：写进项目页的条目与下一个 `## ` 区块之间**只有一个空行**。

    变异靶：`writeback._append_under_heading` 曾把区块尾随空行留在 `lines[end:]` 里，
    于是它自己补的那个空行与原空行叠成两个（2026-09-19 真机：提升到「下一步」后
    与「阻塞」之间多出一个空行）。这条只看"有没有双空行"，不看具体文案。
    """
    client, vault = _client(tmp_path)
    assert (
        client.post(
            "/api/inbox/promote", json={"id": "web-a", "target": "project", "project": PROJECT}
        ).json()["ok"]
        is True
    )
    page = (vault / "projects" / f"{PROJECT}.md").read_text(encoding="utf-8")
    assert "\n\n\n" not in page
    assert "把翻译流程定稿" in page.split("## 下一步")[1].split("## 阻塞")[0]


def test_hand_written_entry_uses_its_project_tag(tmp_path: Path) -> None:
    """手工写进 `inbox.md` 的条目没有机器标记，但正文 `#项目` 仍是路由信号（待办 8 的守卫）。

    `inbox.md` 抬头**邀请**手写 `- [ ] 想法内容 #项目名`；若只看 `wb-capture-project` 标记，
    这种条目会被默认判成「一篇工作思考」，与 `suggest_promotion` 第 2 条规则自相矛盾。
    """
    client, vault = _client(tmp_path, inbox_text=_inbox_text([("把翻译流程定稿 #FinanceOps", [])]))
    item = client.get("/api/inbox").json()["items"][0]
    assert item["project"] is None  # 机器标记确实没有
    assert item["projects"] == [PROJECT]  # 正文标签解析得出来
    assert item["suggested_target"] == "project"

    # 弹层没给项目时，提升也必须落到正文标签指的项目（不能要求使用者再选一次）
    body = client.post("/api/inbox/promote", json={"id": item["id"], "target": "project"}).json()
    assert body["ok"] is True, body
    assert _porcelain(vault) == ""
    assert "把翻译流程定稿" in (vault / "projects" / f"{PROJECT}.md").read_text(encoding="utf-8")
    assert "把翻译流程定稿" not in (vault / "inbox.md").read_text(encoding="utf-8")


def test_promote_reads_the_next_step_without_duplicating_markers(tmp_path: Path) -> None:
    """写进项目页的条目带 `wb-candidate` 标记 ⇒ 重复提升同一条不会写第二份（幂等）。"""
    client, vault = _client(tmp_path)
    page = vault / "projects" / f"{PROJECT}.md"
    payload = {"id": "web-a", "target": "project", "project": PROJECT}
    assert client.post("/api/inbox/promote", json=payload).json()["ok"] is True
    after_first = page.read_text(encoding="utf-8")
    # 条目已移出收件箱 ⇒ 再提升同一条必须明确失败（而不是静默写第二次）
    second = client.post("/api/inbox/promote", json=payload).json()
    assert second["ok"] is False and "已不在收件箱" in second["message"]
    assert page.read_text(encoding="utf-8") == after_first


def test_promote_to_project_followup_block(tmp_path: Path) -> None:
    """① b 项目页条目：`## 跟进事项` 走另一个既有写回实现（他人的行动项）。"""
    client, vault = _client(tmp_path)
    body = client.post(
        "/api/inbox/promote",
        json={"id": "web-b", "target": "project", "project": PROJECT, "block": "followup"},
    ).json()
    assert body["ok"] is True, body
    assert _porcelain(vault) == ""
    page = (vault / "projects" / f"{PROJECT}.md").read_text(encoding="utf-8")
    assert "## 跟进事项" in page and "给 Coach 发邮件" in page
    assert "## 下一步" in page  # 没有误写进下一步
    assert "给 Coach 发邮件" not in (vault / "inbox.md").read_text(encoding="utf-8")


def test_promote_to_thought_writes_thinking_page(tmp_path: Path) -> None:
    """③ 工作思考：复用 `/api/journal/thought` 的落盘（三段式 + 检索就绪），条目移出。"""
    client, vault = _client(tmp_path)
    body = client.post(
        "/api/inbox/promote",
        json={
            "id": "web-a",
            "target": "thought",
            "problem": "课程材料翻译流程为什么总是返工？",
            "thinking": "因为口径没有一次说清，校对阶段才发现术语不一致。",
            "conclusion": "把术语表前置到翻译前，返工率会明显下降。",
        },
    ).json()
    assert body["ok"] is True, body
    assert _porcelain(vault) == ""
    path = Path(body["path"])
    assert path.parent == vault / "thinking"
    note = load_note(path)
    assert note.parse_error is None
    assert note.meta["type"] == "long-form-thought"
    for block in ("## 问题缘起", "## 思考展开", "## 当前结论"):
        assert block in note.body
    assert "把翻译流程定稿" not in (vault / "inbox.md").read_text(encoding="utf-8")
    assert "把翻译流程定稿" not in note.body  # 正文用的是三段表单，不是条目原文
    files = _commit_files(vault)
    assert "inbox.md" in files
    assert Path(body["path"]).relative_to(vault).as_posix() in files


def test_promote_to_thought_requires_the_three_sections(tmp_path: Path) -> None:
    """三段缺一即拒绝，且**不落盘、不动收件箱**。"""
    client, vault = _client(tmp_path)
    before = (vault / "inbox.md").read_text(encoding="utf-8")
    body = client.post(
        "/api/inbox/promote",
        json={
            "id": "web-a",
            "target": "thought",
            "problem": "只有问题",
            "thinking": "",
            "conclusion": "",
        },
    ).json()
    assert body["ok"] is False and "## 思考展开" in body["message"]
    assert not (vault / "thinking").exists()
    assert (vault / "inbox.md").read_text(encoding="utf-8") == before
    assert _porcelain(vault) == ""


def test_promote_to_feishu_task_leaves_no_searchable_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """② 飞书待办：走 outbox（账本）+ `review/archive/` 留痕；库里没有可检索正文。"""
    client, vault = _client(tmp_path)
    created: list[tuple[str, str | None, str]] = []

    def fake_creator(summary: str, due: str | None, candidate_id: str, **_kw: object) -> str:
        created.append((summary, due, candidate_id))
        return "task-guid-1"

    # 路由里是**延迟导入** `_build_task_creator`，所以打在工厂所在的模块上最贴近真实接线。
    monkeypatch.setattr(
        "summit_workbench.webapp.feishu_pool._build_task_creator", lambda *_a, **_k: fake_creator
    )
    body = client.post("/api/inbox/promote", json={"id": "web-b", "target": "feishu-task"}).json()
    assert body["ok"] is True, body
    assert body["external_id"] == "task-guid-1"
    assert created and created[0][2] == "web-b"  # candidate_id 用条目稳定标识 ⇒ 幂等键稳定

    assert _porcelain(vault) == ""
    # 收件箱里那条没了，且**没有**把待办正文写进任何 vault 页面
    assert "给 Coach 发邮件" not in (vault / "inbox.md").read_text(encoding="utf-8")
    archive = Path(body["path"])
    assert archive.parent == vault / "review" / "archive"
    archive_text = archive.read_text(encoding="utf-8")
    assert "type: approval-page" in archive_text
    assert "route：feishu-task" in archive_text
    assert "external_id：task-guid-1" in archive_text
    files = _commit_files(vault)
    assert {"inbox.md", archive.relative_to(vault).as_posix()} <= files


def test_promote_feishu_task_requires_a_due_date(tmp_path: Path) -> None:
    """飞书待办必须有截止日期：条目没带、使用者也没填 ⇒ 明确拒绝、不建任务、不动库。"""
    client, vault = _client(tmp_path)
    before = (vault / "inbox.md").read_text(encoding="utf-8")
    body = client.post("/api/inbox/promote", json={"id": "web-a", "target": "feishu-task"}).json()
    assert body["ok"] is False and "截止日期" in body["message"]
    assert (vault / "inbox.md").read_text(encoding="utf-8") == before
    assert _porcelain(vault) == ""


def test_promote_rejects_unknown_entry_and_project(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    missing = client.post(
        "/api/inbox/promote", json={"id": "web-zzz", "target": "project", "project": PROJECT}
    ).json()
    assert missing["ok"] is False and "已不在收件箱" in missing["message"]
    unregistered = client.post(
        "/api/inbox/promote", json={"id": "web-a", "target": "project", "project": "不存在的项目"}
    ).json()
    assert unregistered["ok"] is False and "未建档" in unregistered["message"]
    assert _porcelain(vault) == ""


def test_suggest_endpoint_reports_local_fallback_when_model_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI 建议按钮：模型不可用时回落到本地启发式，并**明说**这不是 AI 给的。"""
    client, _vault = _client(tmp_path)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise ValueError("model offline")

    monkeypatch.setattr("summit_workbench.webapp.model_config._load_model_config_for_context", boom)
    body = client.post("/api/inbox/suggest", json={"id": "web-b"}).json()
    assert body["ok"] is True
    assert body["model_used"] is False
    assert body["target"] == "feishu-task"
    assert "本地判断" in body["reason"]


def test_read_endpoint_reports_duplicate_region_instead_of_guessing(tmp_path: Path) -> None:
    client, vault = _client(tmp_path)
    (vault / "inbox.md").write_text(
        "## 待处理条目\n\n- [ ] a\n\n## 待处理条目\n\n- [ ] b\n", encoding="utf-8"
    )
    body = client.get("/api/inbox").json()
    assert body["ok"] is False and "重复区块" in body["message"]
    assert body["items"] == [] and body["pending"] == 0
