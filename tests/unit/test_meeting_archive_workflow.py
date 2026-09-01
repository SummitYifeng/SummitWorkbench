"""会议发现 → 归档编排：幂等、unavailable 分支、取稿失败可重试（M1-2）。"""

from __future__ import annotations

import pytest

from summit_workbench.domain.pipeline import ProcessingState, SourceKind, local_idempotency_key
from summit_workbench.repositories.meeting_state import latest_task
from summit_workbench.workflows.meetings.archive import (
    DiscoveredMeeting,
    archive_meeting,
    archive_meetings,
)

TRANSCRIPT = "张三 00:01 大家好\n李四 00:05 开始"


def _state(tmp_path, key: str) -> ProcessingState:
    task = latest_task(tmp_path, key)
    assert task is not None
    return task.state


def _feishu(**kw) -> DiscoveredMeeting:
    base = dict(
        title="招生进度会",
        date="2026-08-30",
        source=SourceKind.FEISHU_NOTE,
        meeting_id="m1",
        note_id="n1",
    )
    base.update(kw)
    return DiscoveredMeeting(**base)  # type: ignore[arg-type]


def _fetch(_m: DiscoveredMeeting) -> str:
    return TRANSCRIPT


def test_feishu_archive_writes_and_records_state(tmp_path):
    report = archive_meeting(tmp_path, _feishu(), _fetch)
    assert report.action == "archived"
    assert report.state == ProcessingState.ARCHIVED
    assert report.path is not None and report.path.exists()
    assert TRANSCRIPT in report.path.read_text(encoding="utf-8")
    assert _state(tmp_path, "m1:n1") == ProcessingState.ARCHIVED


def test_feishu_archive_idempotent_skips_without_refetch(tmp_path):
    archive_meeting(tmp_path, _feishu(), _fetch)

    calls = {"n": 0}

    def counting_fetch(m: DiscoveredMeeting) -> str:
        calls["n"] += 1
        return TRANSCRIPT

    report = archive_meeting(tmp_path, _feishu(), counting_fetch)
    assert report.action == "skipped-existing"
    assert report.state == ProcessingState.ARCHIVED
    assert calls["n"] == 0  # 已归档：连取稿都不做（L14 第 6 条空转）


def test_feishu_without_note_is_unavailable(tmp_path):
    def never(_m: DiscoveredMeeting) -> str:
        raise AssertionError("无 note_id 的会议不应取稿")

    report = archive_meeting(tmp_path, _feishu(note_id=None), never)
    assert report.action == "unavailable"
    assert report.state == ProcessingState.UNAVAILABLE
    assert report.reason and "note_id" in report.reason
    assert _state(tmp_path, "m1") == ProcessingState.UNAVAILABLE


def test_feishu_requires_meeting_id(tmp_path):
    with pytest.raises(ValueError):
        archive_meeting(tmp_path, _feishu(meeting_id=None), _fetch)


def test_fetch_failure_leaves_discovered_for_retry(tmp_path):
    def boom(_m: DiscoveredMeeting) -> str:
        raise RuntimeError("网络抖动")

    with pytest.raises(RuntimeError):
        archive_meeting(tmp_path, _feishu(), boom)
    # 取稿前已记 discovered，失败不产生 archived，可稍后重试。
    assert _state(tmp_path, "m1:n1") == ProcessingState.DISCOVERED


def test_local_archive_keys_on_content_hash(tmp_path):
    meeting = DiscoveredMeeting(title="本地会议", date="2026-08-30", source=SourceKind.LOCAL_FILE)
    report = archive_meeting(tmp_path, meeting, lambda _m: TRANSCRIPT)
    assert report.action == "archived"
    assert report.idem_key == local_idempotency_key(TRANSCRIPT)
    assert _state(tmp_path, report.idem_key) == ProcessingState.ARCHIVED

    # 同内容再来一次：内容哈希命中，空转。
    again = archive_meeting(tmp_path, meeting, lambda _m: TRANSCRIPT)
    assert again.action == "skipped-existing"


def test_projects_propagate_to_evidence(tmp_path):
    report = archive_meeting(tmp_path, _feishu(), _fetch, projects=["ProjA"])
    assert report.path is not None
    assert "ProjA" in report.path.read_text(encoding="utf-8")


def test_batch_returns_per_meeting_reports(tmp_path):
    meetings = [
        _feishu(meeting_id="m1", note_id="n1", title="会一"),
        _feishu(meeting_id="m2", note_id=None, title="会二"),
    ]
    reports = archive_meetings(tmp_path, meetings, _fetch)
    assert [r.action for r in reports] == ["archived", "unavailable"]
