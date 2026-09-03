"""Phase 0 scaffolding for the panel lifecycle implementation plan.

This module keeps the current committed SPA artifact contract executable while
later phases add version-handshake, draft-preservation, and lifecycle tests.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _PROJECT_ROOT / "src" / "summit_workbench" / "webapp" / "static"
_INDEX_RESOURCE = re.compile(r'(?:src|href)="(?P<path>/static/[^\"]+)"')


def test_committed_spa_index_references_existing_static_assets() -> None:
    """Keep the checked-in index and hashed static resources in sync."""
    index = _STATIC_DIR / "index.html"
    assert index.is_file()

    references = [match.group("path") for match in _INDEX_RESOURCE.finditer(index.read_text())]
    assert references, "index.html should reference the compiled SPA assets"

    missing = [
        reference
        for reference in references
        if not (_STATIC_DIR / reference.removeprefix("/static/")).is_file()
    ]
    assert not missing, f"index.html references missing static assets: {missing}"
