"""Local writes are isolated from Git and external synchronization state."""

from __future__ import annotations

from pathlib import Path

from summit_workbench.workflows.local_mutation import LocalMutationOutcome, run_local_mutation


def test_local_mutation_works_in_non_git_workspace_and_records_paths(tmp_path: Path) -> None:
    vault = tmp_path / "no-git-library"
    vault.mkdir()
    target = vault / "note.md"

    result = run_local_mutation(
        vault,
        "note/write",
        lambda _operation_id: (
            target.write_text("approved locally\n", encoding="utf-8"),
            LocalMutationOutcome(target, (target,)),
        )[1],
    )

    assert result.operation_id
    assert result.changed_paths == (target,)
    assert target.read_text(encoding="utf-8") == "approved locally\n"
    assert not (vault / ".git").exists()
