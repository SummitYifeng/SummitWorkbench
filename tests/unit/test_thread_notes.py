"""P1：推进日志（work-log）与 AI 产物（thread-doc）的落盘与 Web 端点。

覆盖：多线程关联、原文必存（AI 不可用兜底）、vault schema 自检、端点回退路径。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from summit_workbench.domain.threaddoc import ArtifactKind, LogTag
from summit_workbench.domain.vault import iter_headings, validate_note
from summit_workbench.repositories.thread_notes import append_work_log, save_thread_artifact
from summit_workbench.repositories.vault import load_note
from summit_workbench.webapp.app import WebContext, create_app


def _mk_project(vault: Path, project: str, aliases: list[str] | None = None) -> None:
    path = vault / "projects" / f"{project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{', '.join(aliases)}]\n" if aliases else ""
    path.write_text(
        f"---\nproject: {project}\ndate: 2026-09-01\ntype: project-main\nstatus: active\n"
        f"{alias_line}---\n\n# P\n\n## 当前状态\n\n## 下一步\n\n## 阻塞\n\n## 决策记录\n"
        "\n## 跟进事项\n",
        encoding="utf-8",
    )


def test_append_work_log_multi_project_and_schema(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    _mk_project(vault, "CoachFinance")
    path = append_work_log(
        vault,
        projects=["FinanceOps", "CoachFinance"],
        text="和木子对齐 Coach 结算，冯老师确认 1500/次，月底前出 V1.1。",
        summary="木子推进 Coach 财务，冯老师确认收费规则，V1.1 月底前交付。",
        involved=["木子", "冯老师"],
        tags=[LogTag.DECISION, LogTag.ACTION],
        next_step="月底前出 Coach Finance Flow V1.1",
        decision="Coach 单次收费 1500 确认",
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    assert path.name == "2026-09-03-001.md"
    assert path.parent == vault / "logs"
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert note.meta["type"] == "work-log"
    assert note.meta["projects"] == ["FinanceOps", "CoachFinance"]
    assert note.meta["status"] == "generated"
    # `area: work` 是工作库约定；缺它会让日志进不了 SK 的「笔记总览」清单
    # （综合类问题按 area 过滤，2026-09-15 实测漏掉了全库唯一那篇日志）。
    assert note.meta["area"] == "work"
    # title 同步落 frontmatter：库规范 §5 要求中文标题进 title，缺它 SK 会回退成文件名。
    assert note.meta["title"] == "推进日志 2026-09-03（FinanceOps 等）"
    assert "和木子对齐 Coach 结算" in note.body  # 原文必存
    # 改进 1：日志正文带 [[projects/<id>]] 实体回链（Obsidian 图谱边）
    assert "## 关联项目" in note.body
    assert "- [[projects/FinanceOps]]" in note.body
    assert "- [[projects/CoachFinance]]" in note.body
    # 同一天第二条递增序号
    path2 = append_work_log(
        vault, projects=["FinanceOps"], text="第二条", now=datetime(2026, 9, 3, 13, tzinfo=UTC)
    )
    assert path2.name == "2026-09-03-002.md"
    assert note.meta["involved"] == ["木子", "冯老师"]


def test_append_work_log_requires_text_and_project(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "P1")
    with pytest.raises(ValueError, match="至少"):
        append_work_log(vault, projects=[], text="x")
    with pytest.raises(ValueError, match="不能为空"):
        append_work_log(vault, projects=["P1"], text="   ")


def test_save_thread_artifact_single_project_schema(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    path = save_thread_artifact(
        vault,
        project="FinanceOps",
        text="# 阶段性总结\n\n（很长）…",
        title="Finance Ops 阶段总结 V2",
        summary="木子 Finance Ops 试任期总结，Coach 试点结论。",
        kind=ArtifactKind.SUMMARY,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    assert path.parent == vault / "artifacts"
    note = load_note(path)
    assert note.parse_error is None
    assert validate_note(note.meta, note.body) == []
    assert note.meta["type"] == "thread-doc"
    assert note.meta["project"] == "FinanceOps"
    assert note.meta["title"] == "Finance Ops 阶段总结 V2"
    assert note.meta["kind"] == "summary"
    # 同 append_work_log：产物也必须带 area，否则进不了 SK 的笔记总览清单。
    assert note.meta["area"] == "work"
    assert note.meta["title"] == "Finance Ops 阶段总结 V2"
    # 改进 1：产物正文带 [[projects/<id>]] 实体回链
    assert "## 关联项目" in note.body
    assert "- [[projects/FinanceOps]]" in note.body


def _client_with_offline_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """模型不可用时（load_model_config 抛错）端点应回退为「只存原文」。"""
    from summit_workbench.providers.llm import LLMError

    def boom(*_args, **_kwargs):
        raise LLMError("model offline")

    monkeypatch.setattr("summit_workbench.providers.llm.load_model_config", boom)
    work = tmp_path / "Work"
    vault = work / "_vault"
    _mk_project(vault, "FinanceOps", aliases=["财务运营"])
    ctx = WebContext(vault_dir=vault, work_root=work, timezone="Asia/Shanghai")
    return TestClient(create_app(ctx))


def test_log_endpoint_falls_back_to_raw_when_model_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _client_with_offline_model(tmp_path, monkeypatch)
    r = c.post(
        "/api/threads/logs",
        json={"projects": ["FinanceOps"], "text": "今天和木子确认了 Coach 时间表。"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["enriched"] is False
    assert body["summary"] == ""
    assert "仅存原文" in body["message"]
    note_path = Path(body["path"])
    note = load_note(note_path)
    assert validate_note(note.meta, note.body) == []
    # 推进日志恒为 `generated`（低权威但可参与事实问答）；`draft` 会被检索契约整体排除，
    # 而「模型不可用只存原文」恰恰是最需要被检索到的证据。摘要有无写在 summary 字段。
    assert note.meta["status"] == "generated"
    assert "summary" not in note.meta


def test_artifact_endpoint_resolves_alias_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _client_with_offline_model(tmp_path, monkeypatch)
    r = c.post(
        "/api/threads/artifacts",
        json={"project": "财务运营", "title": "我的标题", "text": "# 背景包\n\n内容…"},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["title"] == "我的标题"  # 无模型时沿用用户标题
    note = load_note(Path(body["path"]))
    assert note.meta["project"] == "FinanceOps"
    assert validate_note(note.meta, note.body) == []


def test_artifact_endpoint_rejects_unregistered_project(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    vault = work / "_vault"
    vault.mkdir(parents=True)
    ctx = WebContext(vault_dir=vault, work_root=work, timezone="Asia/Shanghai")
    c = TestClient(create_app(ctx))
    r = c.post("/api/threads/artifacts", json={"project": "Ghost", "text": "x"})
    assert r.json()["ok"] is False
    assert "未建档" in r.json()["message"]


# ---- T2：自动产物的确定性结构规范化 ----


def test_append_work_log_keeps_verbatim_text_and_single_related_block(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    text = "第一行含 # 不是标题\n\n第二行含 [[双链]] 与 `code`：1500/次。"
    path = append_work_log(
        vault,
        projects=["FinanceOps"],
        text=text,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    note = load_note(path)
    assert validate_note(note.meta, note.body) == []
    assert text in note.body  # 原文字符逐字保留
    assert "## 原文" in note.body  # 既有读者（project_view 兜底片段）依赖该区块
    assert note.body.count("## 关联项目") == 1  # 不重复生成关联区块


def test_append_work_log_rejects_duplicate_heading_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    with pytest.raises(ValueError, match="规范化"):
        append_work_log(
            vault,
            projects=["FinanceOps"],
            text="## 原文\n\n用户自己又写了一个同名区块。\n",
            now=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
    assert not (vault / "logs").exists()  # 不落半成品


def test_save_thread_artifact_preserves_existing_h2_and_single_h1(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    path = save_thread_artifact(
        vault,
        project="FinanceOps",
        text="# 背景包\n\n## 背景\n\n原文一段。\n\n### 细节\n\n原文二段。\n",
        title="背景包 V2",
        summary="摘要",
        kind=ArtifactKind.SUMMARY,
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    note = load_note(path)
    assert validate_note(note.meta, note.body) == []
    assert [text for level, text in iter_headings(note.body) if level == 1] == ["背景包 V2"]
    assert "## 背景" in note.body  # 已有 H2 不被展平
    assert "### 细节" in note.body  # H3 不被提升
    assert note.body.count("## 关联项目") == 1
    assert "原文一段。" in note.body


def test_save_thread_artifact_rejects_duplicate_heading_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    with pytest.raises(ValueError, match="规范化"):
        save_thread_artifact(
            vault,
            project="FinanceOps",
            text="## 关键结论\n\na\n\n## 关键结论\n\nb\n",
            now=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
    assert not (vault / "artifacts").exists()  # 不落半成品


def test_work_log_without_summary_is_generated_and_fact_eligible(tmp_path: Path) -> None:
    """无摘要的推进日志仍是 `generated`（低权威可检索），不是被排除的 `draft`。"""
    from summit_workbench.domain.retrieval_contract import (
        is_derived_low_authority,
        is_fact_retrieval_eligible,
        validate_retrieval_readiness,
    )

    vault = tmp_path / "vault"
    _mk_project(vault, "FinanceOps")
    path = append_work_log(
        vault,
        projects=["FinanceOps"],
        text="模型不可用，只存原文：和木子确认 Coach 时间表。",
        now=datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    note = load_note(path)
    assert note.meta["status"] == "generated"
    assert "summary" not in note.meta  # 摘要缺失由字段表达，不降级成 draft
    assert is_fact_retrieval_eligible(note.meta) is True
    assert is_derived_low_authority(note.meta) is True  # 但不能单独支撑高置信事实
    assert validate_retrieval_readiness(note.meta, note.body) == []


def test_digest_splits_long_log_instead_of_failing_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    """超长日志必须分段消化并合并，而不是整篇一次调用后回退空摘要。

    2026-09-18 同源问题：digest 过去是「整篇一次调用 + 失败静默回退空摘要」，
    且被硬编码 10 秒超时压住 —— 长文档既超时又看不出原因。
    """
    import json as _json

    import httpx
    from pydantic import SecretStr

    from summit_workbench.prompts import Prompt
    from summit_workbench.providers.llm.config import ModelConfig
    from summit_workbench.workflows.threadnotes import digest_log

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _json.loads(request.content)
        user = payload["messages"][1]["content"]
        seen.append(user)
        index = len(seen)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": _json.dumps(
                                {
                                    "summary": f"第 {index} 段推进",
                                    "involved": [f"人{index}"],
                                    "tags": ["进展"],
                                    "next_step": None,
                                    "decision": None,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    cfg = ModelConfig(
        "digest",
        "m",
        "https://example.test",
        "shared",
        max_output_tokens=200,
        context_window_tokens=400,
        timeout_seconds=120,
    )
    long_text = "\n\n".join(f"段落{i} " + "推进内容" * 20 for i in range(1, 12))
    digest = digest_log(
        cfg,
        SecretStr("secret"),
        Prompt("log-digest", 1, "capture", "json"),
        long_text,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    assert len(seen) > 1, "超长日志必须被拆成多次调用"
    assert digest.summary.startswith("第 1 段推进"), digest.summary
    assert "第 2 段推进" in digest.summary, "多段摘要必须合并进同一份结果"
    assert digest.involved == ["人1", "人2"] or len(digest.involved) > 1


def test_digest_timeout_follows_config_not_hardcoded_cap() -> None:
    """配置里的 timeout_seconds 必须生效；旧实现把它 min() 到 10 秒。"""
    from summit_workbench.providers.llm.config import ModelConfig
    from summit_workbench.workflows.threadnotes import _fast

    cfg = ModelConfig("digest", "m", "https://example.test", "shared", timeout_seconds=120)
    assert _fast(cfg).timeout_seconds == 120

    no_timeout = ModelConfig("digest", "m", "https://example.test", "shared", timeout_seconds=0)
    assert _fast(no_timeout).timeout_seconds == 10.0
