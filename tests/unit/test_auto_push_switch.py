"""Workspace writes no longer produce Git commits or automatic pushes."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from summit_workbench.repositories.git import GitRepo
from summit_workbench.webapp import mutation_runtime
from summit_workbench.webapp.context import WebContext
from summit_workbench.webapp.mutation_response import _mutation_fields
from summit_workbench.workflows.local_mutation import LocalMutationOutcome, run_local_mutation


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout


def _repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "seed.md").write_text("seed", encoding="utf-8")
    _git(path, "add", "seed.md")
    _git(path, "commit", "-q", "-m", "seed")


def test_local_mutation_leaves_git_head_untouched(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _repo(vault)
    head = _git(vault, "rev-parse", "HEAD").strip()

    def mutate(operation_id: str) -> LocalMutationOutcome[str]:
        path = vault / "inbox.md"
        path.write_text(operation_id, encoding="utf-8")
        return LocalMutationOutcome("saved", (path,))

    result = run_local_mutation(vault, "capture", mutate)
    assert result.commit_result is None
    assert _git(vault, "rev-parse", "HEAD").strip() == head
    assert "inbox.md" in _git(vault, "status", "--porcelain")
    assert "commit" not in _mutation_fields(result)
    assert "push" not in _mutation_fields(result)
    assert "auto_push" not in _mutation_fields(result)


def test_legacy_commit_suffix_is_a_noop(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _repo(vault)
    context = WebContext(vault_dir=vault, work_root=tmp_path, timezone="UTC")
    head = GitRepo(vault).head_revision()
    assert mutation_runtime._commit_suffix(context, [vault / "seed.md"], "test") == ""
    assert GitRepo(vault).head_revision() == head


def test_web_write_runtime_has_no_git_or_push_calls() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "summit_workbench"
    files = [
        source_root / "webapp" / "mutation_runtime.py",
        source_root / "workflows" / "local_mutation.py",
        source_root / "workflows" / "onboarding.py",
        source_root / "workflows" / "automation_worker.py",
        source_root / "cli" / "review.py",
    ]
    forbidden = {"commit_paths", "push_after_commit", "GitRepo"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        calls |= {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not (forbidden & (calls | names)), (path, forbidden & (calls | names))
