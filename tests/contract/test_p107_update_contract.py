from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "native" / "SummitWorkbench"


def _source(name: str) -> str:
    return (NATIVE / name).read_text(encoding="utf-8")


def test_p107_native_update_path_is_signed_and_vault_free() -> None:
    source = _source("UpdateCoordinator.swift")
    models = _source("Models.swift")
    lifecycle = _source("LifecycleCoordinator.swift")
    assert "import CryptoKit" in source
    assert "Curve25519.Signing.PublicKey" in source
    assert "isValidSignature" in source
    assert "checkIfDue" in lifecycle
    assert "check(manual: true)" in lifecycle
    assert "NSWorkspace.shared.open(destination)" in source
    assert "写入 vault" in source
    assert "URLSession.shared.dataTask" in source
    assert "update_feed_url" in models
    assert "update_public_key" in models


def test_p107_native_bridge_and_release_contracts_are_present() -> None:
    bridge = (ROOT / "web/src/lifecycle/native-bridge.ts").read_text(encoding="utf-8")
    main = (ROOT / "web/src/legacy-main.ts").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build-macos-app.sh").read_text(encoding="utf-8")
    release = (ROOT / "scripts/release-macos.sh").read_text(encoding="utf-8")
    assert "checkForUpdates" in bridge
    assert "btn-check-updates" in main
    assert "更新检查仅支持已安装的 macOS App" in main
    assert "UPDATE_PUBLIC_KEY" in build
    assert "generate-update-feed.py" in release
    assert "UPDATE_SIGNING_KEY_PATH" in release
    assert "UPDATE_DOWNLOAD_URL" in release
    assert "未配置独立更新 feed 私钥" in release
