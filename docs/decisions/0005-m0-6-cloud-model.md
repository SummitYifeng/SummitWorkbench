# ADR 0005 · M0-6 云端模型冒烟

- 状态：已执行（适配器 + 冒烟机制），真实长逐字稿冒烟由用户带 api key 运行
- 日期：2026-08-31
- 里程碑：M0-6（云端模型冒烟）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §5 M0-6；PRD §6 M0-11、3.2.1/3.2.2、NFR-8、L41、L36

## 决策

- **供应商无关适配器**：`providers/llm/client.py` 走 OpenAI 兼容 `POST {base_url}/chat/completions`
  （DeepSeek 等均兼容）。这是唯一知道 HTTP 形状的地方；上层只见「给消息、拿结构化文本 + 用量」。
- **四类能力配置位**：`[models.meeting|qa|review|ranking]`，缺项回退 `[models.shared]`（首版共用）。
  每项配 model_id / base_url / credential_account / timeout / max_output_tokens / pricing。
  业务代码、prompt、schema **不写死供应商或模型名称**（3.2.2）。
- **结构化输出**：`domain/meeting.py` 的 `MeetingExtraction`（Pydantic）是供应商无关 schema；
  调用启用 `response_format=json_object`，输出用 schema 严格校验，不符合即 `LLMSchemaError`，不返回半成品。
- **prompt 版本化**：`prompts/meeting-processor.md`（带 frontmatter version），代码不内联 prompt（3.2.1）。
- **用量与费用（NFR-8）**：逐次记录时间、能力、模型 ID、输入/输出 token、重试次数、按当期单价快照
  估算的费用；写入 `_vault/_signals/model-usage/YYYY-MM.jsonl`，可按月汇总。单价随记录落盘，
  变更不改写历史。
- **失败策略（L41/NFR-6）**：超时 / 429 / 5xx 视为瞬时故障，指数退避最多重试 3 次（共 4 次调用）；
  4xx 等非重试错误立即抛出；任何失败都显式可见。
- **超长会议（L36）**：正常整稿单次处理；接近上下文上限时的分段留待 M1-3（本批不做）。

## 交付

- `providers/llm/`：config / errors / client（重试+用量）/ usage（记录+费用）。
- `domain/meeting.py`：会议提取 schema。
- `repositories/usage_ledger.py`：月度 JSONL 账本 + 汇总。
- `workflows/meetings/processor.py`：prompt→模型→schema 校验→用量 的编排。
- `prompts/meeting-processor.md`：版本化 prompt。
- CLI `wb model smoke`。
- 契约/单元测试用 `httpx.MockTransport`（退避 sleep 置空）：成功/重试/耗尽/4xx/超时/密钥不泄漏、
  配置加载、费用估算、账本读写、schema 校验、prompt 加载。**无真实调用、无凭据**。
- `config.example.toml` 增加 `[models.*]` 与 api key 的 Keychain 命令。

## 验收对照（M0-6 / M0-11）

- ✅ 供应商无关适配边界 + 四类能力配置位；schema 不含供应商专属字段。
- ✅ 严格结构化输出（JSON + schema 校验）、token 记录、费用估算、超时、错误可见、重试退避：机制齐备并测试覆盖。
- ⏳ 用真实长逐字稿冒烟：待用户把 api key 存入 Keychain 后运行 `wb model smoke <逐字稿>`，
  记录实际模型 ID、prompt 版本、输入输出 token 与估算费用。

## 尚待用户完成

1. `[models.shared]` 填 model_id / base_url（及单价，若要费用估算）。
2. `security add-generic-password -a "shared" -s summit-workbench-model-api-key -w -U` 存 api key。
3. `wb model smoke <真实逐字稿.md>` 跑冒烟，核对结构化质量与 token/费用记录。
