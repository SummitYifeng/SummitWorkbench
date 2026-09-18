"""云端模型能力配置（供应商无关）。

四类能力 meeting / review / ranking / capture 分别配置模型 ID、base_url、鉴权引用、超时、
最大输出与单价；首版允许都指向同一模型。业务代码与 schema 禁止写死供应商或模型名称——
这里是唯一知道「具体模型 ID / base_url」的地方，其余层只按能力名取用。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from summit_workbench.config.secrets import (
    CredentialRef,
    workspace_account,
    workspace_credential_ref,
)
from summit_workbench.config.settings import default_config_file
from summit_workbench.providers.llm.errors import LLMConfigError

CAPABILITIES = ("meeting", "review", "ranking", "capture", "digest")

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
    # 输出额度。**注意这是"思考 + 答案"共用的预算**：DeepSeek-V4 系列默认开思考模式时，
    # reasoning_tokens 也从这里扣。2026-09-18 真机：4096 被推理全部吃光、content 为空，
    # 表现成"模型输出不符合会议 schema"（实际一个字都没吐出来）。
    max_output_tokens: int = 16384
    context_window_tokens: int = 65536
    context_safety_ratio: float = 0.85
    # 思考模式策略：``default`` 不动（供应商默认）；``disabled`` 关闭思考（抽取类任务更快更省）；
    # ``low``/``high``/``max`` 显式设 reasoning_effort。DeepSeek 文档：思考默认打开且 effort=high。
    thinking: str = "default"
    pricing: ModelPricing = ModelPricing()
    workspace_id: str | None = None
    # ``shared`` is a capability-level fallback.  Older configs without this
    # field retain their runtime-capability keychain lookup for compatibility.
    credential_capability: str | None = None

    @property
    def api_key_ref(self) -> CredentialRef:
        if self.workspace_id:
            return workspace_credential_ref(
                self.workspace_id,
                workspace_account(
                    "llm",
                    self.credential_capability or self.capability,
                    self.credential_account,
                ),
            )
        return CredentialRef(service=API_KEY_SERVICE, account=self.credential_account)


def _model_from_table(
    capability: str,
    table: dict[str, Any],
    shared: dict[str, Any],
    workspace_id: str | None = None,
    credential_capability: str | None = None,
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
    context_window_tokens = int(pick("context_window_tokens", 65536))
    context_safety_ratio = float(pick("context_safety_ratio", 0.85))
    if context_window_tokens <= 0:
        raise LLMConfigError("context_window_tokens 必须大于 0")
    if not 0.5 <= context_safety_ratio < 1.0:
        raise LLMConfigError("context_safety_ratio 必须在 [0.5, 1.0) 内")

    configured_credential_capability = pick("credential_capability", credential_capability)
    return ModelConfig(
        capability=capability,
        model_id=str(model_id),
        base_url=str(base_url).rstrip("/"),
        credential_account=str(pick("credential_account", "shared")),
        timeout_seconds=float(pick("timeout_seconds", 60.0)),
        max_output_tokens=int(pick("max_output_tokens", 16384)),
        context_window_tokens=context_window_tokens,
        context_safety_ratio=context_safety_ratio,
        thinking=str(pick("thinking", "default")),
        pricing=pricing,
        workspace_id=workspace_id,
        credential_capability=(
            str(configured_credential_capability)
            if configured_credential_capability is not None
            else None
        ),
    )


def load_model_config(
    capability: str,
    config_file: Path | None = None,
    *,
    workspace_id: str | None = None,
) -> ModelConfig:
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

    return _model_from_table(
        capability,
        table,
        shared,
        workspace_id,
        credential_capability=capability if table else None,
    )
