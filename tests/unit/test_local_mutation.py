"""Local mutation lock and no-workspace-Git contract."""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories.local_mutation_journal import (
    list_mutation_records,
    start_mutation_record,
)
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
    MutationInvariantError,
    run_local_mutation,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout


def _git_repo(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    _git(vault, "init", "-q")
    _git(vault, "config", "user.email", "t@t.test")
    _git(vault, "config", "user.name", "Tester")
    (vault / "seed.md").write_text("seed", encoding="utf-8")
    _git(vault, "add", "--", "seed.md")
    _git(vault, "commit", "-q", "-m", "seed")
    return vault


def test_concurrent_mutations_get_distinct_operations_without_git_writes(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)
    head_before = _git(vault, "rev-parse", "HEAD").strip()

    def mutate(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / f"operations-{operation_id}.md"
        path.write_text(operation_id, encoding="utf-8")
        time.sleep(0.03)
        return LocalMutationOutcome(operation_id, (path,))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_local_mutation(vault, "capture", mutate), range(2)))

    assert len({result.operation_id for result in results}) == 2
    assert all(result.commit_result is None for result in results)
    assert _git(vault, "rev-parse", "HEAD").strip() == head_before
    assert (
        len(
            [
                line
                for line in _git(vault, "status", "--porcelain").splitlines()
                if "operations-" in line
            ]
        )
        == 2
    )


def test_failed_mutation_writes_nothing_and_propagates_error(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        raise ValueError("mutation failed")

    with pytest.raises(ValueError, match="mutation failed"):
        run_local_mutation(vault, "capture", mutate)
    assert not any(
        "omitted.md" in line for line in _git(vault, "status", "--porcelain").splitlines()
    )


def test_failed_mutation_does_not_prevent_concurrent_success(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)

    def fail(_operation_id: str) -> LocalMutationOutcome[str]:
        raise ValueError("expected failure")

    def succeed(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "success.md"
        path.write_text(operation_id, encoding="utf-8")
        return LocalMutationOutcome("ok", (path,))

    def run(mutation):
        try:
            return run_local_mutation(vault, "test", mutation)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        failed, succeeded = list(pool.map(run, (fail, succeed)))

    assert failed is None
    assert succeeded is not None
    assert succeeded.commit_result is None
    assert (vault / "success.md").read_text(encoding="utf-8") == succeeded.operation_id


def test_plain_directory_mutation_succeeds_without_git(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    def mutate(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "inbox.md"
        path.write_text(operation_id, encoding="utf-8")
        return LocalMutationOutcome("saved", (path,))

    result = run_local_mutation(vault, "capture", mutate)
    assert result.business_return == "saved"
    assert result.commit_result is None
    assert (vault / "inbox.md").read_text(encoding="utf-8") == result.operation_id


def test_repository_lock_reentry_does_not_deadlock(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        with workspace_lock(vault.parent):
            path = vault / "nested.md"
            path.write_text("nested", encoding="utf-8")
        return LocalMutationOutcome("nested", (path,))

    result = run_local_mutation(vault, "nested", mutate)
    assert result.commit_result is None
    assert (vault / "nested.md").read_text(encoding="utf-8") == "nested"


def test_business_result_and_declared_paths_are_preserved(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)
    path = vault / "result.md"
    result = run_local_mutation(
        vault,
        "capture",
        lambda operation_id: LocalMutationOutcome(
            {"operation_id": operation_id, "ok": True},
            (path,),
        ),
    )
    assert result.business_return == {"operation_id": result.operation_id, "ok": True}
    assert result.changed_paths == (path,)
    assert result.commit_result is None


def test_unreported_file_write_fails_without_committing_anything(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)
    declared = vault / "declared.md"
    omitted = vault / "omitted.md"

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        declared.write_text("declared", encoding="utf-8")
        omitted.write_text("omitted", encoding="utf-8")
        return LocalMutationOutcome("ok", (declared,))

    with pytest.raises(MutationInvariantError, match="omitted.md") as exc_info:
        run_local_mutation(vault, "test", mutate)
    assert exc_info.value.committed is False
    status = _git(vault, "status", "--porcelain").splitlines()
    assert any("declared.md" in line for line in status)
    assert any("omitted.md" in line for line in status)


def test_mutation_cannot_report_a_path_outside_workspace(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)
    outside = tmp_path / "outside.md"

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        outside.write_text("outside", encoding="utf-8")
        return LocalMutationOutcome("ok", (outside,))

    with pytest.raises(MutationInvariantError, match="工作库之外"):
        run_local_mutation(vault, "test", mutate)


def test_interrupted_mutation_is_reported_without_overwriting_files(tmp_path: Path) -> None:
    vault = tmp_path / "workspace"
    vault.mkdir()
    path = vault / "inbox.md"
    path.write_text("before\n", encoding="utf-8")
    before = {"inbox.md": __import__("hashlib").sha256(path.read_bytes()).hexdigest()}
    start_mutation_record(vault, "op-crashed", "capture", before)
    path.write_text("after\n", encoding="utf-8")

    run_local_mutation(
        vault,
        "next-action",
        lambda op: LocalMutationOutcome("ok", (path,)),
    )

    pending = [
        record for record in list_mutation_records(vault) if record["operation_id"] == "op-crashed"
    ]
    assert pending[0]["state"] == "interrupted"
    assert pending[0]["changed_paths"] == ["inbox.md"]
    assert path.read_text(encoding="utf-8") == "after\n"
