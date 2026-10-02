from __future__ import annotations

import json
from pathlib import Path

import pytest

from summit_workbench.domain.approval import (
    approval_digest,
    approval_record,
    has_valid_approval,
    normalize_approved_body,
    retrieval_eligible,
)
from summit_workbench.domain.workspace_contract import (
    WorkspaceContractError,
    WorkspaceContractManifest,
    check_workspace_compatibility,
)
from summit_workbench.repositories import workspace_contract
from summit_workbench.repositories.vault import parse_frontmatter
from summit_workbench.repositories.workspace_contract import (
    connect_workspace,
    initialize_workspace,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "workspace-v1"


def _manifest(
    workspace_id: str = "00000000-0000-4000-8000-000000000001",
) -> WorkspaceContractManifest:
    return WorkspaceContractManifest(
        workspace_id=workspace_id,
        contract_version=1,
        min_reader_version=1,
        min_writer_version=1,
    )


def test_shared_approval_vectors_and_qualification() -> None:
    data = json.loads((FIXTURE / "vectors.json").read_text(encoding="utf-8"))
    for vector in data["approval_vectors"]:
        assert approval_digest(vector["metadata"], vector["body"]) == vector["content_sha256"]
        metadata = dict(vector["metadata"])
        recorded = vector.get("approval_content_sha256", vector["content_sha256"])
        metadata["approval"] = {
            "version": 1,
            "content_sha256": recorded,
            "approved_at": "2026-10-02T12:00:00Z",
            "operation_id": "op_0123456789abcdef0123456789abcdef",
        }
        assert retrieval_eligible(metadata, vector["body"]) is vector["eligible"]
    qualification = json.loads((FIXTURE / "qualification.json").read_text(encoding="utf-8"))
    for case in qualification["cases"]:
        text = (FIXTURE / case["fixture"]).read_text(encoding="utf-8")
        metadata, body, error = parse_frontmatter(text)
        assert error is None
        assert retrieval_eligible(metadata, body) is case["eligible"]


def test_approval_digest_normalizes_line_endings_but_binds_semantic_metadata() -> None:
    assert normalize_approved_body("# Note\r\n\r\nText  \r\n\r\n") == "# Note\n\nText\n"
    assert approval_digest({"title": "A"}, "text\n") != approval_digest({"title": "B"}, "text\n")
    assert approval_digest({"title": "A"}, "text\r\n") == approval_digest({"title": "A"}, "text\n")


def test_project_archive_lifecycle_keeps_approval_valid() -> None:
    metadata = {"type": "project-main", "status": "active", "title": "Project"}
    body = "Approved project content."
    metadata["approval"] = approval_record(metadata, body, operation_id="confirm-1")
    archived = {**metadata, "status": "archived"}
    assert has_valid_approval(archived, body)
    assert approval_digest(archived, body) == approval_digest(metadata, body)
    assert not has_valid_approval({**metadata, "status": "paused"}, body)


def test_nonsemantic_activity_metadata_does_not_change_approval() -> None:
    original = {"type": "note", "status": "active", "title": "A", "activity_at": "2026-10-01"}
    digest = approval_digest(original, "body")
    original["approval"] = {
        "version": 1,
        "content_sha256": digest,
        "approved_at": "now",
        "operation_id": "op",
    }
    original["activity_at"] = "2026-10-02"
    assert has_valid_approval(original, "body")


def test_manifest_hard_rejects_invalid_or_incompatible_workspace() -> None:
    with pytest.raises(ValueError):
        _manifest("not-a-uuid")
    future = WorkspaceContractManifest(
        workspace_id="00000000-0000-4000-8000-000000000001",
        contract_version=2,
        min_reader_version=1,
        min_writer_version=1,
    )
    with pytest.raises(WorkspaceContractError):
        check_workspace_compatibility(future)


def test_initialize_only_empty_folder_and_connect_preserves_identity(tmp_path: Path) -> None:
    root = tmp_path / "library with spaces"
    manifest = initialize_workspace(root)
    assert (root / "conventions.md").is_file()
    assert not (root / ".git").exists()
    assert connect_workspace(root).workspace_id == manifest.workspace_id
    with pytest.raises(WorkspaceContractError, match="已有内容"):
        initialize_workspace(root)
    before = (root / ".summit-workbench" / "manifest.json").read_bytes()
    connect_workspace(root)
    assert (root / ".summit-workbench" / "manifest.json").read_bytes() == before


def test_workspace_template_lookup_supports_resources_layout(monkeypatch, tmp_path: Path) -> None:
    resources = tmp_path / "SummitWorkbench.app" / "Contents" / "Resources"
    module_path = (
        resources
        / "server"
        / "_internal"
        / "summit_workbench"
        / "repositories"
        / "workspace_contract.py"
    )
    template = resources / "templates" / "workspace" / "conventions.md"
    template.parent.mkdir(parents=True)
    template.write_text("# Packaged workspace contract\n", encoding="utf-8")
    monkeypatch.setattr(workspace_contract, "__file__", str(module_path))
    root = tmp_path / "workspace"
    root.mkdir()

    initialize_workspace(root)

    assert (root / "conventions.md").read_text(encoding="utf-8") == template.read_text(
        encoding="utf-8"
    )
