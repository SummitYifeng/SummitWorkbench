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
        "WB_PACKAGED_APP:",
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
        "actions/upload-artifact@v7",
        "raven-actions/actionlint@v2",
        "environment:",
        "secrets.UPDATE_SIGNING_KEY",
        "vars.UPDATE_FEED_URL",
        "vars.UPDATE_DOWNLOAD_URL",
        'REQUIRE_SIGNED_UPDATE: "true"',
        "OpenSSL 3",
        "--draft",
        "gh release edit",
    ):
        assert required in workflow
    assert "        env:\n        run:" not in workflow


def test_release_scripts_enforce_arm64_metadata_and_publish_test_manifest() -> None:
    build = (ROOT / "scripts/build-macos-app.sh").read_text(encoding="utf-8")
    release = (ROOT / "scripts/release-macos.sh").read_text(encoding="utf-8")
    assert "$(uname -m)" in build
    assert '"architecture": "$ARCH"' in build
    assert "test-manifest.json" in release
    assert "--require-openssl3" in release
    assert "REQUIRE_SIGNED_UPDATE" in release


def test_p107c_has_real_workflow_and_native_behavior_gates() -> None:
    workflow_lint = (ROOT / "scripts/verify-workflows.sh").read_text(encoding="utf-8")
    swift_test = (ROOT / "scripts/test-native-updates.sh").read_text(encoding="utf-8")
    update_source = (ROOT / "native/SummitWorkbench/UpdateCoordinator.swift").read_text(
        encoding="utf-8"
    )
    bridge = (ROOT / "web/src/lifecycle/native-bridge.ts").read_text(encoding="utf-8")
    main = (ROOT / "web/src/legacy-main.ts").read_text(encoding="utf-8")
    assert "actionlint" in workflow_lint
    assert "UpdateNetworking" in update_source
    assert "UpdateFileSystem" in update_source
    assert "UpdateDefaults" in update_source
    assert "UpdateAppOpener" in update_source
    assert "workspaceIsCompatible" in update_source
    assert "updateAutoCheckChanged" in bridge + main
    assert "UpdateCoordinatorTests.swift" in swift_test


def test_local_gate_script_mirrors_the_remote_quality_gate() -> None:
    """本地门禁必须覆盖远端 CI 的检查，否则「本地绿、CI 红」会再次发生。"""
    gate = (ROOT / "scripts/pre-push-gate.sh").read_text(encoding="utf-8")
    refs = (ROOT / "scripts/check-action-refs.sh").read_text(encoding="utf-8")
    installer = (ROOT / "scripts/install-git-hooks.sh").read_text(encoding="utf-8")
    for required in (
        "verify-workflows.sh",
        "check-action-refs.sh",
        'ruff" check .',
        'ruff" format --check .',
        '"$BIN/mypy"',
        "-m pytest",
        "--cov-fail-under=80",
        "test:frontend",
        "git diff --check",
    ):
        assert required in gate
    # action ref 预检必须真的查远端 ref，而不是只做字符串检查。
    assert "contents/action.yml?ref=" in refs
    assert "pre-push" in installer
