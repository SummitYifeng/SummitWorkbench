"""模型配置加载测试：能力表 + shared 兜底 + 单价 + 凭据引用。"""

from __future__ import annotations

import pytest

from summit_workbench.providers.llm.config import load_model_config
from summit_workbench.providers.llm.errors import LLMConfigError

SHARED = """
[models.shared]
model_id = "some-model"
base_url = "https://api.example.com/v1/"
credential_account = "shared"
timeout_seconds = 30
max_output_tokens = 2048
[models.shared.pricing]
currency = "CNY"
input_per_mtok = 1.0
output_per_mtok = 2.0
"""


def test_load_from_shared(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(SHARED, encoding="utf-8")
    cfg = load_model_config("meeting", f)
    assert cfg.capability == "meeting"
    assert cfg.model_id == "some-model"
    assert cfg.base_url == "https://api.example.com/v1"  # 末尾 / 去除
    assert cfg.max_output_tokens == 2048
    assert cfg.pricing.input_per_mtok == 1.0
    assert cfg.api_key_ref.service == "summit-workbench-model-api-key"
    assert cfg.api_key_ref.account == "shared"


def test_capability_overrides_shared(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(SHARED + '\n[models.review]\nmodel_id = "review-model"\n', encoding="utf-8")
    cfg = load_model_config("review", f)
    assert cfg.model_id == "review-model"  # 能力表覆盖
    assert cfg.base_url == "https://api.example.com/v1"  # 回退 shared


def test_meeting_has_explicit_reliability_overrides(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(
        SHARED
        + '\n[models.meeting]\nmodel_id = "deepseek-flash"\ntimeout_seconds = 300\n'
        + "max_output_tokens = 8192\ncontext_window_tokens = 1000000\n",
        encoding="utf-8",
    )
    cfg = load_model_config("meeting", f)
    assert cfg.model_id == "deepseek-flash"
    assert cfg.timeout_seconds == 300
    assert cfg.max_output_tokens == 8192
    assert cfg.context_window_tokens == 1_000_000


def test_explicit_shared_credential_scope_is_workspace_safe(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(
        SHARED.replace(
            'credential_account = "shared"',
            'credential_account = "shared"\ncredential_capability = "shared"',
        ),
        encoding="utf-8",
    )
    cfg = load_model_config("ranking", f, workspace_id="workspace-a")
    assert cfg.api_key_ref.account == "llm:shared:shared"


def test_cost_estimate():
    from summit_workbench.providers.llm.config import ModelPricing

    p = ModelPricing(input_per_mtok=1.0, output_per_mtok=3.0)
    # 1e6 输入 * 1 + 1e6 输出 * 3 = 4.0
    assert p.estimate(1_000_000, 1_000_000) == 4.0
    assert p.estimate(0, 0) == 0.0


def test_missing_required_raises(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[models.meeting]\nbase_url = "https://x/v1"\n', encoding="utf-8")
    with pytest.raises(LLMConfigError) as ei:
        load_model_config("meeting", f)
    assert "model_id" in str(ei.value)


def test_unknown_capability_raises(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(SHARED, encoding="utf-8")
    with pytest.raises(LLMConfigError):
        load_model_config("nope", f)


def test_retired_qa_capability_config_is_ignored(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(SHARED + '\n[models.qa]\nmodel_id = "legacy-qa-model"\n', encoding="utf-8")

    with pytest.raises(LLMConfigError):
        load_model_config("qa", f)

    assert load_model_config("meeting", f).model_id == "some-model"


def test_no_models_table_raises(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('timezone = "UTC"\n', encoding="utf-8")
    with pytest.raises(LLMConfigError):
        load_model_config("meeting", f)
