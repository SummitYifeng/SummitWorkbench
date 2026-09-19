"""P1-06 CI、覆盖率与发布矩阵契约。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _web_sources() -> str:
    """Every frontend source file, concatenated.

    The workbench is being split from ``legacy-main.ts`` into ``features/*`` (see
    ``docs/implementation/LEGACY-MAIN-SPLIT-PLAN.md``); these guards must not depend on which
    module currently owns a string.
    """
    files = sorted(
        path for path in (ROOT / "web" / "src").rglob("*.ts") if not path.name.endswith(".d.ts")
    )
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


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


def test_daily_ci_is_manual_only() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    trigger_block = ci.split("permissions:", 1)[0]

    assert re.search(r"(?m)^\s+workflow_dispatch:\s*$", trigger_block)
    assert not re.search(r"(?m)^\s+(?:push|pull_request):\s*$", trigger_block)


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
    main = _web_sources()
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
        "uv lock --check",
        'ruff" check .',
        'ruff" format --check .',
        '"$BIN/mypy"',
        "-m pytest",
        "--cov-fail-under=80",
        "tsc --noEmit",
        "test:frontend",
        "scripts/secret_scan.py",
        "scripts/test-native-updates.sh",
        "git diff --check",
    ):
        assert required in gate
    # action ref 预检必须真的查远端 ref，而不是只做字符串检查。
    assert "contents/action.yml?ref=" in refs
    assert "pre-push" in installer


def test_frontend_scripts_only_import_declared_packages() -> None:
    """前端脚本不得依赖未声明的包（幽灵依赖）。

    Vite 8 用 Rolldown 取代 esbuild 后，`web/scripts/*.mjs` 里那 6 处
    ``import { build } from 'esbuild'`` 立刻全线 ERR_MODULE_NOT_FOUND——因为 esbuild
    从未被声明，只是恰好被 Vite 提升。这条测试把「脚本只能引用已声明的包」变成契约。
    """
    import json
    import re

    manifest = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    declared = set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))

    # 只匹配行首的顶层静态 import/export，避免误伤 Buffer.from('...') 这类调用。
    bare_import = re.compile(
        r"""^(?:import|export)\s+(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]""",
        re.MULTILINE,
    )
    undeclared: dict[str, set[str]] = {}
    for script in sorted((ROOT / "web/scripts").glob("*.mjs")):
        for spec in bare_import.findall(script.read_text(encoding="utf-8")):
            if spec.startswith((".", "/", "node:")):
                continue
            name = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
            if name not in declared:
                undeclared.setdefault(script.name, set()).add(name)

    assert not undeclared, f"前端脚本引用了未声明的包（幽灵依赖）：{undeclared}"
