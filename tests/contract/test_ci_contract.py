"""P1-06 CI、覆盖率与发布矩阵契约。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_has_reproducible_python_node_lock_and_secret_gates() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for required in (
        "uv lock --check",
        "uv run pytest --cov=summit_workbench",
        "--cov-fail-under=80",
        "npm ci --prefix web",
        "npm --prefix web run build",
        "verify-build.mjs",
        "scripts/secret_scan.py",
        "package-lock.json",
    ):
        assert required in ci


def test_release_workflow_validates_tag_and_runs_packaged_integration() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for required in (
        'tags:\n      - "v*"',
        "GITHUB_REF_NAME#v",
        "pyproject.toml",
        "macos-14",
        "ARCH: arm64",
        "WB_PACKAGED_APP:",
        "actions/upload-artifact@v4",
    ):
        assert required in workflow


def test_release_scripts_enforce_arm64_metadata_and_publish_test_manifest() -> None:
    build = (ROOT / "scripts/build-macos-app.sh").read_text(encoding="utf-8")
    release = (ROOT / "scripts/release-macos.sh").read_text(encoding="utf-8")
    assert "$(uname -m)" in build
    assert '"architecture": "$ARCH"' in build
    assert "test-manifest.json" in release
