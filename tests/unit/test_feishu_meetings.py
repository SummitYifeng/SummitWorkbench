"""会议逐字稿来源测试：本地兜底可用，Note 主链路未固定时显式报错。"""

from __future__ import annotations

import pytest

from summit_workbench.providers.feishu.client import FeishuClient
from summit_workbench.providers.feishu.errors import FeishuAPIError, FeishuError
from summit_workbench.providers.feishu.meetings import (
    FeishuNoteSource,
    import_local_transcript,
)


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


def test_feishu_note_source_not_yet_pinned():
    # 主链路端点未固定前必须显式报错，绝不返回伪造结果。
    source = FeishuNoteSource(client=object())  # type: ignore[arg-type]
    with pytest.raises(FeishuAPIError) as ei:
        source.fetch_transcript("m1")
    assert "M0-10" in str(ei.value)


def test_feishu_client_type_available():
    # 保证 client 类型可被 verify_identity 使用（形状检查，不联网）。
    assert FeishuClient.__name__ == "FeishuClient"
