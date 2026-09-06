"""P1-07 更新 feed 兼容性和签名正文契约。"""

from __future__ import annotations

from summit_workbench.updates.feed import UpdateFeedError, select_compatible_update, signing_payload


def _artifact(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "version": "0.4.2",
        "build": "107",
        "architecture": "arm64",
        "minimum_macos": "13.0",
        "download_url": "https://updates.example.invalid/SummitWorkbench.dmg",
        "sha256": "a" * 64,
        "size": 123,
        "release_notes": "P1-07 update",
        "signature": "signed-feed-entry",
    }
    value.update(overrides)
    return value


def test_selects_only_new_compatible_https_signed_arm64_update() -> None:
    payload = {
        "schema_version": 1,
        "product_id": "com.summitworkbench.panel",
        "artifacts": [_artifact()],
    }

    selected = select_compatible_update(payload, current_version="0.4.1", current_build="106")

    assert selected is not None
    assert selected["build"] == "107"


def test_rejects_wrong_architecture_minimum_macos_and_unsigned_artifacts() -> None:
    payload = {
        "schema_version": 1,
        "product_id": "com.summitworkbench.panel",
        "artifacts": [
            _artifact(architecture="x86_64"),
            _artifact(build="108", minimum_macos="99.0"),
            _artifact(build="109", signature=""),
        ],
    }

    assert select_compatible_update(payload, current_version="0.4.1", current_build="106") is None


def test_rejects_invalid_feed_schema_and_keeps_signing_payload_stable() -> None:
    try:
        select_compatible_update({}, current_version="0.4.1", current_build="106")
    except UpdateFeedError as exc:
        assert "schema" in str(exc)
    else:
        raise AssertionError("invalid feed must be rejected")

    assert (
        signing_payload(_artifact(), product_id="com.summitworkbench.panel")
        == (
            "com.summitworkbench.panel\n0.4.2\n107\narm64\n13.0\n"
            "https://updates.example.invalid/SummitWorkbench.dmg\n"
            + "a" * 64
            + "\n123\nP1-07 update"
        ).encode()
    )


def test_ignores_malformed_minimum_macos_without_breaking_other_candidates() -> None:
    payload = {
        "schema_version": 1,
        "product_id": "com.summitworkbench.panel",
        "artifacts": [_artifact(build="108", minimum_macos="not-a-version"), _artifact()],
    }

    selected = select_compatible_update(payload, current_version="0.4.1", current_build="106")

    assert selected is not None
    assert selected["build"] == "107"
