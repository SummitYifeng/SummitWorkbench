"""会议提取 schema 校验与 prompt 加载测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from summit_workbench.domain.meeting import MeetingExtraction
from summit_workbench.prompts import load_prompt


def test_valid_extraction_parses():
    payload = """
    {
      "one_minute_summary": "定了第3章样章周三前交付",
      "facts": [{"text": "第2章已完成", "evidence": "李四 00:10:00"}],
      "decisions": [{"description": "采用方案A", "target_project": "HIC_SWB_LaTEX",
                     "evidence": "张三 00:11:00"}],
      "action_items": [
        {"description": "给老王样章", "target_project": "HIC_SWB_LaTEX",
         "due_date": "2026-09-03", "evidence": "张三 00:12:30"}
      ],
      "open_questions": [{"text": "封面字号未定", "evidence": "段落 12"}],
      "ai_suggestions": ["建议下周同步排版进度"]
    }
    """
    ex = MeetingExtraction.model_validate_json(payload)
    assert ex.one_minute_summary.startswith("定了")
    assert ex.action_items[0].target_project == "HIC_SWB_LaTEX"
    assert ex.action_items[0].due_date == "2026-09-03"


def test_missing_summary_fails():
    with pytest.raises(ValidationError):
        MeetingExtraction.model_validate_json('{"facts": []}')


def test_extra_fields_ignored():
    ex = MeetingExtraction.model_validate_json(
        '{"one_minute_summary": "x", "vendor_field": "ignored"}'
    )
    assert ex.one_minute_summary == "x"
    assert ex.facts == []


def test_claim_without_timestamp_or_anchor_fails():
    with pytest.raises(ValidationError):
        MeetingExtraction.model_validate_json(
            '{"one_minute_summary":"x","facts":[{"text":"完成","evidence":"会议里说的"}]}'
        )


def test_invalid_due_date_fails():
    with pytest.raises(ValidationError):
        MeetingExtraction.model_validate_json(
            '{"one_minute_summary":"x","action_items":[{"description":"交付",'
            '"due_date":"2026-02-30","evidence":"张三 00:01"}]}'
        )


def test_load_meeting_processor_prompt():
    # 从仓库 prompts/ 读取真实 prompt 文件（不联网）
    prompt = load_prompt("meeting-processor")
    assert prompt.name == "meeting-processor"
    assert prompt.version >= 1
    assert prompt.capability == "meeting"
    assert "JSON" in prompt.body
    assert prompt.version_label == "meeting-processor@v3"


def test_load_meeting_merger_prompt():
    prompt = load_prompt("meeting-merger")
    assert prompt.name == "meeting-merger"
    assert prompt.capability == "meeting"
