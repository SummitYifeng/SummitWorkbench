"""P0-02 本地 mutation 与自动提交事务边界。"""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from summit_workbench.config.locking import workspace_lock
from summit_workbench.repositories.autocommit import CommitStatus
from summit_workbench.workflows.local_mutation import (
    LocalMutationOutcome,
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


def test_concurrent_mutations_get_distinct_operations_and_commits(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)

    def mutate(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / f"operations-{operation_id}.md"
        path.write_text(operation_id, encoding="utf-8")
        time.sleep(0.03)
        return LocalMutationOutcome(operation_id, (path,))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_local_mutation(vault, "capture", mutate), range(2)))

    operation_ids = {result.operation_id for result in results}
    assert len(operation_ids) == 2
    assert all(result.commit_result.status is CommitStatus.COMMITTED for result in results)
    subjects = _git(vault, "log", "--pretty=%s", "-2").splitlines()
    assert len(subjects) == 2
    assert all(subject.startswith("wb: capture [") for subject in subjects)
    for operation_id in operation_ids:
        assert operation_id in subjects[0] or operation_id in subjects[1]


def test_failed_mutation_does_not_call_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _git_repo(tmp_path)
    called: list[str] = []

    def fake_commit(*_args: object, **_kwargs: object) -> object:
        called.append("commit")
        return object()

    monkeypatch.setattr("summit_workbench.workflows.local_mutation.commit_paths", fake_commit)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        raise ValueError("mutation failed")

    with pytest.raises(ValueError, match="mutation failed"):
        run_local_mutation(vault, "capture", mutate)
    assert called == []


def test_failed_mutation_does_not_prevent_concurrent_success_commit(tmp_path: Path) -> None:
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
    assert succeeded.commit_result.status is CommitStatus.COMMITTED
    assert _git(vault, "log", "--pretty=%s", "-2").splitlines() == [
        f"wb: test [{succeeded.operation_id}]",
        "seed",
    ]


def test_non_git_mutation_succeeds_and_exposes_not_git_status(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    def mutate(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "inbox.md"
        path.write_text(operation_id, encoding="utf-8")
        return LocalMutationOutcome("saved", (path,))

    result = run_local_mutation(vault, "capture", mutate)

    assert result.business_return == "saved"
    assert result.commit_result.status is CommitStatus.NOT_GIT
    assert (vault / "inbox.md").read_text(encoding="utf-8") == result.operation_id


def test_repository_lock_reentry_does_not_deadlock(tmp_path: Path) -> None:
    vault = _git_repo(tmp_path)

    def mutate(_operation_id: str) -> LocalMutationOutcome[str]:
        with workspace_lock(vault.parent):
            path = vault / "nested.md"
            path.write_text("nested", encoding="utf-8")
        return LocalMutationOutcome("nested", (path,))

    result = run_local_mutation(vault, "nested", mutate)

    assert result.commit_result.status is CommitStatus.COMMITTED
    assert (vault / "nested.md").read_text(encoding="utf-8") == "nested"


def test_business_return_and_changed_paths_are_preserved(tmp_path: Path) -> None:
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
    assert result.commit_result.status is CommitStatus.NOTHING_TO_COMMIT
