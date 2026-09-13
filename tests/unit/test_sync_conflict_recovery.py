from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import summit_workbench.workflows.sync_conflict_recovery as recovery_module
from summit_workbench.domain.thread_activity import MonotonicULIDGenerator, ThreadActivityEvent
from summit_workbench.repositories.git import GitRepo
from summit_workbench.repositories.git_backend import CommitIdentity
from summit_workbench.workflows.sync_conflict_recovery import (
    RECOVERY_AUDIT_PATH,
    SelectionChoice,
    apply_prepared_recovery,
    inspect_divergence,
    prepare_automatic_recovery,
    prepare_manual_recovery,
    validate_automatic_recovery,
    validate_manual_selections,
)

IDENTITY = CommitIdentity("Recovery test", "recovery@example.com")


def _commit(repo: GitRepo, root: Path, rel: str, content: str, message: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    repo.add([rel])
    repo.commit(message, author=IDENTITY)


def test_inspect_divergence_returns_safe_side_and_event_metadata(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    studio = tmp_path / "studio"
    studio_repo = GitRepo(studio)
    studio_repo.backend.init()
    _commit(studio_repo, studio, "README.md", "base\n", "wb: base")
    studio_repo.backend.add_remote("origin", str(remote))
    studio_repo.push()

    air = tmp_path / "air"
    air_repo = GitRepo(air)
    air_repo.backend.clone(str(remote), air)
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("studio").new(),
        workspace_id="workspace-1",
        device_id="studio",
        occurred_at=datetime(2026, 9, 7, 1, 2, 3, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        studio_repo,
        studio,
        f"_events/studio/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: studio event",
    )
    studio_repo.push()

    _commit(air_repo, air, "notes.md", "air\n", "wb: air note")
    air_repo.fetch()
    details = inspect_divergence(air, paths=None)

    assert details.base_revision == air_repo.merge_base(
        studio_repo.head_revision(), air_repo.head_revision()
    )
    assert details.local.side == "local"
    assert details.remote.side == "remote"
    assert {item.path for item in details.paths} == {
        f"_events/studio/2026/09/{event.event_id}.json",
        "notes.md",
    }
    event_detail = next(item for item in details.paths if item.kind.value == "append-only-event")
    assert event_detail.remote_event is not None
    assert event_detail.remote_event["device_id"] == "studio"
    assert event_detail.remote_event["causation_operation_id"] == "operation-1"
    assert event_detail.local_event is None
    assert all("payload" not in item for item in (event_detail.remote_event or {}))

    note_detail = next(item for item in details.paths if item.path == "notes.md")
    missing = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={},
    )
    assert missing.status == "incomplete"
    assert missing.missing_paths == (note_detail.path,)
    selected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={note_detail.path: SelectionChoice.KEEP_LOCAL},
    )
    assert selected.status == "validated"
    stale = validate_manual_selections(
        details,
        base_revision="0" * 40,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={note_detail.path: SelectionChoice.KEEP_LOCAL},
    )
    assert stale.error_code == "conflict_snapshot_stale"

    event_only = inspect_divergence(air, paths=(event_detail.path,))
    validation = validate_automatic_recovery(
        air,
        event_only,
        workspace_id="workspace-1",
    )
    assert validation.status == "validated"
    assert validation.event_count == 1
    assert validation.aggregate_count == 1
    assert air_repo.head_revision() == event_only.local.revision


def test_inspect_divergence_path_filter_only_changes_selection(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "a.md", "a\n", "wb: a")
    repo.push()
    _commit(other_repo, other, "b.md", "b\n", "wb: b")
    other_repo.fetch()

    details = inspect_divergence(other, paths=("b.md",))
    assert [item.path for item in details.paths] == ["b.md"]
    assert details.paths[0].changed_on == ("local",)


def test_validate_automatic_recovery_stops_before_manual_content(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread.json", "{}\n", "wb: view")
    repo.push()
    _commit(other_repo, other, "notes.md", "manual\n", "wb: note")
    other_repo.fetch()

    details = inspect_divergence(other)
    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "manual-confirmation-required"
    assert validation.error_code == "manual_items"


def test_unknown_generated_view_requires_preserve_both_fallback(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread.json", "{}\n", "wb: view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()

    details = inspect_divergence(other)
    unknown_view = next(item for item in details.paths if item.path == "_views/thread.json")
    assert unknown_view.kind.value == "unknown-generated-view"
    assert unknown_view.automatic is False

    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "manual-confirmation-required"
    assert validation.as_dict()["ok"] is False
    assert validation.error_code == "manual_items"

    rejected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={unknown_view.path: SelectionChoice.KEEP_REMOTE},
    )
    assert rejected.status == "invalid"
    assert rejected.invalid_paths == (unknown_view.path,)

    selected = validate_manual_selections(
        details,
        base_revision=details.base_revision,
        local_revision=details.local.revision,
        remote_revision=details.remote.revision,
        selections={unknown_view.path: SelectionChoice.PRESERVE_BOTH},
    )
    assert selected.status == "validated"
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={unknown_view.path: SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.status == "validated"
        assert prepared.candidate_paths == ("_views/thread.json",)
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "_views/thread.json").read_text() == "{}\n"
        assert not (prepared.staging_dir / "_views/thread.json.remote").exists()
        applied = apply_prepared_recovery(
            other,
            prepared,
            workspace_id="workspace-1",
            confirm=True,
            author=IDENTITY,
        )
        assert applied.status == "committed"
        assert applied.revision is not None
        assert other_repo.commit_parent_count(applied.revision) == 2
        assert (other / "_views/thread.json").read_text() == "{}\n"
        assert not (other / "_views/thread.json.remote").exists()
        audit = json.loads((other / RECOVERY_AUDIT_PATH).read_text().splitlines()[-1])
        assert audit["merge_revision"] == applied.revision
        assert audit["applied_paths"] == ["_views/thread.json"]
    other_repo.push()
    assert other_repo.ahead_behind().ahead == 0
    assert other_repo.ahead_behind().behind == 0


def test_validate_automatic_recovery_rebuilds_defined_view_in_staging(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread-activity.json", "stale\n", "wb: stale view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()

    details = inspect_divergence(other)
    validation = validate_automatic_recovery(other, details, workspace_id="workspace-1")

    assert validation.status == "validated"
    assert validation.generated_view_count == 1
    assert validation.rebuilt_view_count == 1
    assert validation.event_count == 1
    assert validation.aggregate_count == 1
    assert other_repo.head_revision() == details.local.revision

    with prepare_automatic_recovery(other, details, workspace_id="workspace-1") as prepared:
        awaiting_confirmation = apply_prepared_recovery(
            other, prepared, workspace_id="workspace-1", confirm=False
        )
        assert awaiting_confirmation.status == "confirmation-required"
        applied = apply_prepared_recovery(other, prepared, workspace_id="workspace-1", confirm=True)
        assert applied.status == "committed"
        assert applied.revision is not None
        assert other_repo.commit_parent_count(applied.revision) == 2
        assert (other / "_views/thread-activity.json").read_text().find(
            '"projection": "thread-activity"'
        ) >= 0
        audit = json.loads((other / RECOVERY_AUDIT_PATH).read_text().splitlines()[-1])
        assert audit["status"] == "committed"
        assert audit["merge_revision"] == applied.revision
        assert audit["local_revision"] == details.local.revision
        assert "vault" not in json.dumps(audit)
        assert applied.as_dict()["audit"] == {"status": "committed", "error_code": None}
    other_repo.push()
    assert other_repo.ahead_behind().ahead == 0
    assert other_repo.ahead_behind().behind == 0


def test_prepare_automatic_recovery_owns_ephemeral_staging_and_rejects_stale_snapshot(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "_views/thread-activity.json", "stale\n", "wb: stale view")
    repo.push()
    event = ThreadActivityEvent(
        event_id=MonotonicULIDGenerator("device").new(),
        workspace_id="workspace-1",
        device_id="device",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        kind="thread.activity.work-log.created",
        aggregate_id="project-1",
        payload={"source_type": "work-log"},
        causation_operation_id="operation-1",
    )
    _commit(
        other_repo,
        other,
        f"_events/device/2026/09/{event.event_id}.json",
        event.model_dump_json(),
        "wb: event",
    )
    other_repo.fetch()
    details = inspect_divergence(other)

    with prepare_automatic_recovery(other, details, workspace_id="workspace-1") as prepared:
        assert prepared.ready is True
        assert prepared.as_dict()["staging_ready"] is True
        assert prepared.staging_dir is not None
        staging = prepared.staging_dir
        assert not (staging / ".git").exists()
        assert (staging / f"_events/device/2026/09/{event.event_id}.json").is_file()
        rendered = json.loads((staging / "_views/thread-activity.json").read_text())
        assert rendered["projection"] == "thread-activity"
        assert rendered["aggregates"][0]["aggregate_id"] == "project-1"

        before_apply = other_repo.head_revision()
        _commit(repo, root, "remote-later.md", "remote later\n", "wb: remote later")
        repo.push()
        other_repo.fetch()
        stale_apply = apply_prepared_recovery(
            other,
            prepared,
            workspace_id="workspace-1",
            confirm=True,
            author=IDENTITY,
        )
        assert stale_apply.status == "stale"
        assert stale_apply.error_code == "conflict_snapshot_stale"
        assert other_repo.head_revision() == before_apply
        assert not (other / "_views/thread-activity.json").exists()
        assert not (other / RECOVERY_AUDIT_PATH).exists()
    assert not staging.exists()

    _commit(other_repo, other, "after.md", "after\n", "wb: after snapshot")
    stale = prepare_automatic_recovery(other, details, workspace_id="workspace-1")
    assert stale.status == "stale"
    assert stale.error_code == "conflict_snapshot_stale"
    assert stale.staging_dir is None


def test_recovery_commit_remains_committed_when_audit_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "remote.md", "remote\n", "wb: remote")
    repo.push()
    _commit(other_repo, other, "local.md", "local\n", "wb: local")
    other_repo.fetch()
    details = inspect_divergence(other)

    def fail_audit(*_args, **_kwargs) -> None:
        raise OSError("simulated audit storage failure")

    monkeypatch.setattr(recovery_module, "_append_recovery_audit", fail_audit)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={
            "local.md": SelectionChoice.KEEP_LOCAL,
            "remote.md": SelectionChoice.KEEP_REMOTE,
        },
    ) as prepared:
        applied = apply_prepared_recovery(
            other,
            prepared,
            workspace_id="workspace-1",
            confirm=True,
            author=IDENTITY,
        )

    assert applied.status == "committed"
    assert applied.audit_status == "failed"
    assert applied.audit_error_code == "recovery_audit_failed"
    assert applied.as_dict()["audit"] == {
        "status": "failed",
        "error_code": "recovery_audit_failed",
    }
    assert applied.revision is not None
    assert other_repo.commit_parent_count(applied.revision) == 2


def test_prepare_manual_recovery_applies_remote_choice_only_in_staging(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "notes.md", "remote\n", "wb: remote note")
    repo.push()
    _commit(other_repo, other, "notes.md", "local\n", "wb: local note")
    other_repo.fetch()

    details = inspect_divergence(other)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"notes.md": SelectionChoice.KEEP_REMOTE},
    ) as prepared:
        assert prepared.ready is True
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "notes.md").read_text() == "remote\n"
        assert (other / "notes.md").read_text() == "local\n"
        assert other_repo.head_revision() == details.local.revision


def test_prepare_manual_recovery_preserves_remote_copy_deterministically(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "attachment.bin", "remote\n", "wb: remote binary")
    repo.push()
    _commit(other_repo, other, "attachment.bin", "local\n", "wb: local binary")
    other_repo.fetch()

    details = inspect_divergence(other)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"attachment.bin": SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.ready is True
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "attachment.bin").read_text() == "local\n"
        assert (prepared.staging_dir / "attachment.bin.remote").read_text() == "remote\n"


def test_remote_only_preserve_both_keeps_original_path(tmp_path: Path) -> None:
    """A one-sided remote artifact must not grow a ``.remote.remote`` sibling."""
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "attachment.bin", "remote\n", "wb: remote binary")
    repo.push()
    other_repo.fetch()

    details = inspect_divergence(other)
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"attachment.bin": SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.ready is True
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "attachment.bin").read_text() == "remote\n"
        assert not (prepared.staging_dir / "attachment.bin.remote").exists()
        assert prepared.candidate_paths == ("attachment.bin",)


def test_second_preserve_both_uses_a_revision_suffixed_sibling(tmp_path: Path) -> None:
    """D8：上一次恢复留下的 `<path>.remote` 不能让第二次「保留双方副本」必然失败。

    真机复跑实测：第一次演练在同一路径上选过「保留双方副本」，vault 里留下了
    `inbox.md.remote`；第二次再选同一项就被 `preserve_both_path_collision` 直接拒绝，
    而界面只说「恢复准备未完成」，用户完全不知道该怎么办。
    """
    remote = tmp_path / "remote.git"
    GitRepo(remote).backend.init(bare=True)
    root = tmp_path / "root"
    repo = GitRepo(root)
    repo.backend.init()
    _commit(repo, root, "base.md", "base\n", "wb: base")
    # 第一次恢复留下的远端副本：已提交，所以两侧都有，不是本次分叉路径。
    _commit(repo, root, "attachment.bin.remote", "first-pass\n", "wb: previous remote copy")
    repo.backend.add_remote("origin", str(remote))
    repo.push()
    other = tmp_path / "other"
    other_repo = GitRepo(other)
    other_repo.backend.clone(str(remote), other)
    _commit(repo, root, "attachment.bin", "remote\n", "wb: remote binary")
    repo.push()
    _commit(other_repo, other, "attachment.bin", "local\n", "wb: local binary")
    other_repo.fetch()

    details = inspect_divergence(other)
    suffix = details.remote.revision[:7]
    with prepare_manual_recovery(
        other,
        details,
        workspace_id="workspace-1",
        selections={"attachment.bin": SelectionChoice.PRESERVE_BOTH},
    ) as prepared:
        assert prepared.ready is True, prepared.error_code
        assert prepared.staging_dir is not None
        assert (prepared.staging_dir / "attachment.bin").read_text() == "local\n"
        # 上一轮的副本原样保留，新副本用远端 revision 短码区分（确定性、不覆盖、不丢数据）。
        assert (prepared.staging_dir / "attachment.bin.remote").read_text() == "first-pass\n"
        assert (prepared.staging_dir / f"attachment.bin.remote.{suffix}").read_text() == "remote\n"
        assert f"attachment.bin.remote.{suffix}" in prepared.candidate_paths
