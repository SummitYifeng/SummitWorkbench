"""云端模型能力配置（供应商无关）。

四类能力 meeting / qa / review / ranking 分别配置模型 ID、base_url、鉴权引用、超时、
最大输出与单价；首版允许都指向同一模型。业务代码与 schema 禁止写死供应商或模型名称——
这里是唯一知道「具体模型 ID / base_url」的地方，其余层只按能力名取用。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from summit_workbench.config.secrets import CredentialRef
from summit_workbench.config.settings import default_config_file
from summit_workbench.providers.llm.errors import LLMConfigError

CAPABILITIES = ("meeting", "qa", "review", "ranking")

# api key 的 Keychain service 前缀（account 用能力名或 shared）。
API_KEY_SERVICE = "summit-workbench-model-api-key"


@dataclass(frozen=True)
class ModelPricing:
    """按每百万 token 的单价（当期配置快照，用于费用估算；变更不改写历史账目）。"""

    currency: str = "CNY"
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    def estimate(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class ModelConfig:
    capability: str
    model_id: str
    base_url: str
    credential_account: str
    timeout_seconds: float = 60.0
    max_output_tokens: int = 4096
    pricing: ModelPricing = ModelPricing()

    @property
    def api_key_ref(self) -> CredentialRef:
        return CredentialRef(service=API_KEY_SERVICE, account=self.credential_account)


def _model_from_table(
    capability: str, table: dict[str, Any], shared: dict[str, Any]
) -> ModelConfig:
    def pick(key: str, default: Any = None) -> Any:
        return table.get(key, shared.get(key, default))

    model_id = pick("model_id")
    base_url = pick("base_url")
    missing = [k for k, v in {"model_id": model_id, "base_url": base_url}.items() if not v]
    if missing:
        raise LLMConfigError(f"[models.{capability}] 缺少必填项：{', '.join(missing)}")

    price_raw = pick("pricing", {})
    price: dict[str, Any] = price_raw if isinstance(price_raw, dict) else {}
    pricing = ModelPricing(
        currency=str(price.get("currency", "CNY")),
        input_per_mtok=float(price.get("input_per_mtok", 0.0)),
        output_per_mtok=float(price.get("output_per_mtok", 0.0)),
    )
    return ModelConfig(
        capability=capability,
        model_id=str(model_id),
        base_url=str(base_url).rstrip("/"),
        credential_account=str(pick("credential_account", "shared")),
        timeout_seconds=float(pick("timeout_seconds", 60.0)),
        max_output_tokens=int(pick("max_output_tokens", 4096)),
        pricing=pricing,
    )


def load_model_config(capability: str, config_file: Path | None = None) -> ModelConfig:
    """加载某能力的模型配置。

    读取 ``[models.<capability>]``，缺项回退到 ``[models.shared]``（首版四类共用）。
    """
    if capability not in CAPABILITIES:
        raise LLMConfigError(f"未知能力 {capability!r}，允许 {list(CAPABILITIES)}")

    path = config_file or default_config_file()
    if not path.is_file():
        raise LLMConfigError(
            f"配置文件不存在：{path}（需 [models.{capability}] 或 [models.shared]）"
        )

    with path.open("rb") as fh:
        data = tomllib.load(fh)
    models = data.get("models")
    if not isinstance(models, dict):
        raise LLMConfigError(f"配置文件缺少 [models] 表：{path}")

    shared = models.get("shared", {})
    table = models.get(capability, {})
    if not isinstance(table, dict) or not isinstance(shared, dict):
        raise LLMConfigError(f"[models.{capability}] / [models.shared] 必须是表")
    if not table and not shared:
        raise LLMConfigError(f"缺少 [models.{capability}] 且无 [models.shared] 兜底")

    return _model_from_table(capability, table, shared)
