"""CLI 行为测试：退出码语义、错误分支与幂等提示。

``test_cli.py`` 只做命令注册与端到端冒烟；这里补齐每天真正会敲到的子命令的
参数校验、失败可见性与退出码契约（0 正常 / 1 需人工处理 / 2 用法或前置条件错误）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from summit_workbench.cli.main import app
from summit_workbench.config.locking import LockBusy

runner = CliRunner()


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """隔离配置与工作区，避免读取开发者本机状态。"""
    work = tmp_path / "work"
    monkeypatch.setenv("WB_CONFIG_FILE", str(tmp_path / "nonexistent.toml"))
    monkeypatch.setenv("WORK_ROOT", str(work))
    return work


# --------------------------------------------------------------------------- retired Git command


def test_sync_command_is_retired() -> None:
    result = runner.invoke(app, ["sync", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


# ------------------------------------------------------------------------- review


def test_review_refresh_reports_busy_workspace_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    def busy(_vault: Any) -> None:
        raise LockBusy("另一任务占用")

    monkeypatch.setattr("summit_workbench.cli.review.refresh_meeting_review", busy)
    result = runner.invoke(app, ["review", "refresh"])
    assert result.exit_code == 1
    assert "工作区忙" in result.stdout


def test_review_refresh_reports_value_error_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    def broken(_vault: Any) -> None:
        raise ValueError("审批页损坏")

    monkeypatch.setattr("summit_workbench.cli.review.refresh_meeting_review", broken)
    result = runner.invoke(app, ["review", "refresh"])
    assert result.exit_code == 1
    assert "审批页刷新失败" in result.stdout


def test_review_refresh_prints_scan_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    report = SimpleNamespace(
        outcome=SimpleNamespace(path="/vault/review/meetings.md", added=2, preserved=1),
        notes_scanned=5,
        candidates_found=3,
    )
    monkeypatch.setattr("summit_workbench.cli.review.refresh_meeting_review", lambda _vault: report)
    result = runner.invoke(app, ["review", "refresh"])
    assert result.exit_code == 0
    assert "/vault/review/meetings.md" in result.stdout
    assert "扫描笔记=5" in result.stdout
    assert "新增=2" in result.stdout
    assert "保留=1" in result.stdout


def test_review_apply_defaults_to_zero_write_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    report = SimpleNamespace(
        dry_run=True, actions=[], applied=0, rejected=0, failed=0, archive_path=None
    )
    monkeypatch.setattr("summit_workbench.cli.review.apply_meeting_review", lambda *a, **k: report)
    result = runner.invoke(app, ["review", "apply"])
    assert result.exit_code == 0
    assert "DRY-RUN（零写入）" in result.stdout
    assert "批准写回=0" in result.stdout


def test_review_apply_failures_exit_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    report = SimpleNamespace(
        dry_run=False,
        actions=[],
        applied=1,
        rejected=1,
        failed=1,
        archive_path="/vault/archive.md",
    )
    monkeypatch.setattr("summit_workbench.cli.review.apply_meeting_review", lambda *a, **k: report)
    result = runner.invoke(app, ["review", "apply", "--apply"])
    assert result.exit_code == 1
    assert "已显式应用" in result.stdout
    assert "失败=1" in result.stdout
    assert "/vault/archive.md" in result.stdout


def test_review_apply_busy_workspace_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    def busy(*_args: Any, **_kwargs: Any) -> None:
        raise LockBusy("占用中")

    monkeypatch.setattr("summit_workbench.cli.review.apply_meeting_review", busy)
    result = runner.invoke(app, ["review", "apply"])
    assert result.exit_code == 1
    assert "工作区忙" in result.stdout


def test_review_apply_injects_only_feishu_task_creator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The only external approval writer is Feishu task creation."""
    from summit_workbench.cli import review as review_cli

    _env(monkeypatch, tmp_path)
    captured: dict[str, Any] = {}

    def fake_apply(
        _vault: Any,
        _work_root: Any,
        *,
        apply: bool,
        task_creator: Any = None,
    ) -> Any:
        captured.update(apply=apply, task_creator=task_creator)
        return SimpleNamespace(
            dry_run=not apply,
            actions=[],
            applied=0,
            rejected=0,
            failed=0,
            archive_path=None,
        )

    monkeypatch.setattr(review_cli, "apply_meeting_review", fake_apply)

    dry = runner.invoke(app, ["review", "apply"])
    assert dry.exit_code == 0
    # 预演不得注入任何写回器（零写入）。
    assert captured["task_creator"] is None

    real = runner.invoke(app, ["review", "apply", "--apply"])
    assert real.exit_code == 0
    assert callable(captured["task_creator"])


def test_review_sweep_rejects_malformed_before_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["review", "sweep", "--before", "2026/09/01"])
    assert result.exit_code == 1
    assert "清扫失败" in result.stdout


def test_review_sweep_dry_run_never_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    report = SimpleNamespace(dry_run=True, notes=[tmp_path / "2026-09-01-test.md"], candidates=4)
    monkeypatch.setattr("summit_workbench.cli.review.sweep_meeting_review", lambda *a, **k: report)
    result = runner.invoke(app, ["review", "sweep"])
    assert result.exit_code == 0
    assert "DRY-RUN（零写入）" in result.stdout
    assert "涉及候选=4" in result.stdout
    assert "确认无误后加 --apply 执行" in result.stdout


# ------------------------------------------------------------------------ meeting


def test_meeting_archive_local_missing_file_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "meeting",
            "archive-local",
            str(tmp_path / "absent.txt"),
            "--title",
            "T",
            "--date",
            "2026-09-01",
        ],
    )
    assert result.exit_code == 2
    assert "文件不存在" in result.stdout


def test_meeting_archive_local_rejects_bad_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    transcript = tmp_path / "t.txt"
    transcript.write_text("说话人：内容\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "meeting",
            "archive-local",
            str(transcript),
            "--title",
            "T",
            "--date",
            "2026-09-99",
        ],
    )
    assert result.exit_code == 2
    assert "日期格式应为 YYYY-MM-DD" in result.stdout


def test_meeting_archive_local_rejects_empty_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    transcript = tmp_path / "empty.txt"
    transcript.write_text("   \n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "meeting",
            "archive-local",
            str(transcript),
            "--title",
            "T",
            "--date",
            "2026-09-01",
        ],
    )
    assert result.exit_code == 2
    assert "逐字稿文件为空" in result.stdout


def test_meeting_process_missing_transcript_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["meeting", "process", str(tmp_path / "absent.md")])
    assert result.exit_code == 2
    assert "逐字稿文件不存在" in result.stdout


def test_meeting_import_missing_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["meeting", "import", str(tmp_path / "absent")])
    assert result.exit_code == 2
    assert "来源不存在" in result.stdout


def test_meeting_import_without_model_config_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """缺少模型配置时必须在扫描/归档之前停下，且不产生任何写入。"""
    work = _env(monkeypatch, tmp_path)
    source = tmp_path / "transcripts"
    source.mkdir()
    (source / "2026-09-01-demo.txt").write_text("说话人：内容\n", encoding="utf-8")

    result = runner.invoke(app, ["meeting", "import", str(source)])

    assert result.exit_code == 2
    assert "导入未启动" in result.stdout
    assert not (work / "_vault").exists()


def test_meeting_import_warns_about_oversized_transcripts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """超限文件必须被跳过**并显式告知**，不能静默少导或静默送模型。"""
    from summit_workbench.workflows.meetings.backfill import MAX_TRANSCRIPT_BYTES

    _env(monkeypatch, tmp_path)
    source = tmp_path / "drop"
    source.mkdir()
    (source / "2026-09-11-正常.txt").write_text("说话人 甲 00:00:01\n内容\n", encoding="utf-8")
    (source / "2026-09-11-超大.txt").write_bytes(b"x" * (MAX_TRANSCRIPT_BYTES + 1))

    result = runner.invoke(app, ["meeting", "import", str(source)])

    # 隔离环境无模型配置 → 退出 2；但警告在这之前就已输出。
    assert result.exit_code == 2
    assert "已跳过 1 个超过 10 MiB 的逐字稿" in result.stdout
    assert "2026-09-11-超大.txt" in result.stdout


def test_meeting_archive_without_feishu_config_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "meeting",
            "archive",
            "--meeting-no",
            "937075886",
            "--since",
            "2026-09-01",
            "--until",
            "2026-09-07",
        ],
    )
    assert result.exit_code == 2
    assert "配置错误" in result.stdout


def test_meeting_process_without_model_config_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    transcript = tmp_path / "archived.md"
    transcript.write_text("# 逐字稿\n说话人：内容\n", encoding="utf-8")
    result = runner.invoke(app, ["meeting", "process", str(transcript)])
    assert result.exit_code == 2
    assert "结构化处理未启动" in result.stdout


def test_meeting_archive_local_writes_evidence_layer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """唯一完全本地的归档入口：不联网也应落盘证据层并成功退出。"""
    work = _env(monkeypatch, tmp_path)
    (work / "_vault").mkdir(parents=True)
    transcript = tmp_path / "2026-09-01-demo.txt"
    transcript.write_text("说话人 甲：讨论内容\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "meeting",
            "archive-local",
            str(transcript),
            "--title",
            "本地兜底会议",
            "--date",
            "2026-09-01",
        ],
    )

    assert result.exit_code == 0
    assert "archived" in result.stdout
    archived = list((work / "_vault").rglob("*2026-09-01*"))
    assert archived, "本地归档必须落盘逐字稿"


# ------------------------------------------------------------------------ backfill


@pytest.mark.parametrize("flag", ["--since", "--until"])
def test_meeting_backfill_rejects_malformed_dates_before_anything_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: str
) -> None:
    """日期校验必须先于来源检查与模型配置，错误信息要点名具体是哪个 flag。"""
    _env(monkeypatch, tmp_path)
    args = [
        "meeting",
        "backfill",
        str(tmp_path / "absent"),
        "--since",
        "2026-09-01",
        "--until",
        "2026-09-07",
    ]
    args[args.index(flag) + 1] = "2026/09/01"

    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert f"{flag} 格式应为 YYYY-MM-DD" in result.stdout


def test_meeting_backfill_missing_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "meeting",
            "backfill",
            str(tmp_path / "absent"),
            "--since",
            "2026-09-01",
            "--until",
            "2026-09-07",
        ],
    )
    assert result.exit_code == 2
    assert "来源不存在" in result.stdout


def test_meeting_backfill_without_model_config_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    source = tmp_path / "transcripts"
    source.mkdir()
    result = runner.invoke(
        app,
        [
            "meeting",
            "backfill",
            str(source),
            "--since",
            "2026-09-01",
            "--until",
            "2026-09-07",
        ],
    )
    assert result.exit_code == 2
    assert "补导未启动" in result.stdout


# -------------------------------------------------------------------------- feishu


def test_feishu_authorize_url_without_config_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["feishu", "authorize-url"])
    assert result.exit_code == 2
    assert "配置错误" in result.stdout


def test_feishu_meetings_without_config_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "feishu",
            "meetings",
            "--meeting-no",
            "937075886",
            "--since",
            "2026-09-01",
            "--until",
            "2026-09-07",
        ],
    )
    assert result.exit_code == 2
    assert "配置错误" in result.stdout


def _with_fake_feishu_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 ``_config()`` 成功但完全不联网：只替换配置与客户端构造。"""
    monkeypatch.setattr(
        "summit_workbench.cli.feishu.load_feishu_config", lambda: SimpleNamespace(scope_param="s")
    )
    monkeypatch.setattr("summit_workbench.cli.feishu._tenant_client", lambda _cfg: object())
    monkeypatch.setattr("summit_workbench.cli.feishu._user_client", lambda _cfg: object())


def test_feishu_note_transcript_prints_retrieved_length(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    _with_fake_feishu_config(monkeypatch)

    class _Source:
        def __init__(self, _client: Any) -> None: ...

        def fetch_transcript(self, note_id: str) -> Any:
            return SimpleNamespace(text="x" * 400, note_id=note_id, doc_token="doc-1")

    monkeypatch.setattr("summit_workbench.cli.feishu.FeishuNoteSource", _Source)
    result = runner.invoke(app, ["feishu", "note-transcript", "--note-id", "n1", "--preview", "10"])

    assert result.exit_code == 0
    assert "400 字符" in result.stdout
    assert "doc-1" in result.stdout


def test_feishu_note_transcript_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from summit_workbench.providers.feishu import FeishuError

    _env(monkeypatch, tmp_path)
    _with_fake_feishu_config(monkeypatch)

    class _Source:
        def __init__(self, _client: Any) -> None: ...

        def fetch_transcript(self, _note_id: str) -> Any:
            raise FeishuError("纪要不可读")

    monkeypatch.setattr("summit_workbench.cli.feishu.FeishuNoteSource", _Source)
    result = runner.invoke(app, ["feishu", "note-transcript", "--note-id", "n1"])

    assert result.exit_code == 1
    assert "拉取逐字稿失败" in result.stdout
    assert "纪要不可读" in result.stdout


def test_feishu_login_failure_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from summit_workbench.providers.feishu import FeishuError

    _env(monkeypatch, tmp_path)
    _with_fake_feishu_config(monkeypatch)

    class _Session:
        def __init__(self, _cfg: Any) -> None: ...

        def complete_authorization(self, _code: str) -> Any:
            raise FeishuError("code 已过期")

    monkeypatch.setattr("summit_workbench.cli.feishu.FeishuSession", _Session)
    result = runner.invoke(app, ["feishu", "login", "--code", "stale"])

    assert result.exit_code == 1
    assert "登录失败" in result.stdout


def test_feishu_calendar_rejects_bad_date_after_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    _with_fake_feishu_config(monkeypatch)
    result = runner.invoke(app, ["feishu", "calendar", "--date", "2026/09/01"])
    assert result.exit_code == 2
    assert "日期格式应为 YYYY-MM-DD" in result.stdout


def test_feishu_calendar_empty_day_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    _with_fake_feishu_config(monkeypatch)
    monkeypatch.setattr(
        "summit_workbench.providers.feishu.calendar.list_events_between", lambda *a, **k: []
    )
    result = runner.invoke(app, ["feishu", "calendar", "--date", "2026-09-01"])
    assert result.exit_code == 0
    assert "主日历无事件" in result.stdout
