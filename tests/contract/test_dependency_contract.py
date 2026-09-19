"""Runtime dependency contracts for the packaged Git backend."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dulwich_is_pinned_to_the_migrated_api_range() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = config["project"]["dependencies"]

    assert "dulwich>=1.2.15,<1.3" in dependencies

    overrides = config.get("tool", {}).get("mypy", {}).get("overrides", [])
    assert all(
        item.get("module") != "summit_workbench.repositories.dulwich_git" for item in overrides
    )
