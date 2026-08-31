"""本地逐字稿兜底测试（飞书 Note 主链路的契约测试见 tests/contract/test_feishu_note.py）。"""

from __future__ import annotations

import pytest

from summit_workbench.providers.feishu.errors import FeishuError
from summit_workbench.providers.feishu.meetings import import_local_transcript


def test_import_local_ok(tmp_path):
    f = tmp_path / "t.md"
    f.write_text("张三 00:01 大家好\n李四 00:05 开始吧\n", encoding="utf-8")
    result = import_local_transcript(f, meeting_id="local-1")
    assert result.source == "local-file"
    assert result.meeting_id == "local-1"
    assert "张三" in result.text
    assert result.origin_path == str(f)


def test_import_local_missing_raises(tmp_path):
    with pytest.raises(FeishuError):
        import_local_transcript(tmp_path / "missing.md", meeting_id="x")


def test_import_local_empty_raises(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("   \n", encoding="utf-8")
    with pytest.raises(FeishuError):
        import_local_transcript(f, meeting_id="x")
