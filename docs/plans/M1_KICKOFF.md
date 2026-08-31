# M1 开发交接（会议进入第二大脑）

> 面向下一个开发对话。权威规格仍是 `docs/product/PRD.md`（§3.1.9、L13–L44）与
> `docs/plans/DEVELOPMENT_PLAN.md` §6；本文只做「从哪接手、有什么可复用、怎么起步」的交接。

## 现状（截至 2026-08-31）

M0 地基全部完成并**真机验证**。M1 已推进三个切片（决策见 `docs/decisions/` 0008–0010）：

- **M1-1 已完成**：稳定 schema 与状态机（`domain/pipeline.py`、`domain/review.py`）。
- **M1-2 已完成并真机冒烟**：会议发现与原文归档（`repositories/meeting_state.py`、
  `repositories/meeting_archive.py`、`workflows/meetings/archive.py`、CLI `wb meeting archive|archive-local`）。
  飞书主链路完整跑通（发现 → 取稿 → 落 `meetings/transcripts/` → 幂等空转）；无纪要会议记 `unavailable`。
- **M1-3 已完成并真机验收**：`wb meeting process` 读取归档原文，按 token 预算单次或分段处理，
  层级合并并强制证据锚点；成功原子写入 `meetings/notes/`，失败同模型重试后进入错误队列且零半成品。
  真实会议生成 9 个固定区块、10/10 条证据均带时间戳；用量为输入 2796 / 输出 965 token，重跑幂等空转。

质量门全绿：`uv run ruff check . && uv run mypy && uv run pytest`（152 项）。**下一步 M1-4**（集中审批与写回）。

## M1 可直接复用的已建能力

M1 主要是**把已跑通的两条链路串起来并加审批边界**，而非从零造：

| 能力 | 位置 | 说明 |
|---|---|---|
| 会议发现 | `providers/feishu/meetings.py::list_meetings_by_no` | 会议号+时间范围 → 会议 + note_id（真机通过）|
| 逐字稿拉取 | `providers/feishu/meetings.py::FeishuNoteSource.fetch_transcript` | note_id → 逐字稿正文（真机通过）|
| 本地兜底 | `providers/feishu/meetings.py::import_local_transcript` | Note 不可用时导入本地逐字稿 |
| 应用/用户令牌 | `providers/feishu/session.py` | `tenant_access_token()`（读纪要）/ `access_token()`（用户态）|
| 结构化处理 | `workflows/meetings/processor.py::process_transcript` | 逐字稿 → `MeetingExtraction`（严格 JSON），真机通过 |
| 用量费用账本 | `repositories/usage_ledger.py` | 逐次 token/费用落 `_vault/_signals/model-usage/` |
| vault schema | `domain/vault.py` + `repositories/vault.py` + `templates/vault/` | frontmatter/固定区块校验、会议笔记模板已就绪 |
| 重试/失败可见 | `providers/llm/client.py`（退避重试）、各 `errors.py` | L41/NFR-6 已落地 |

## M1 工作包（DEVELOPMENT_PLAN §6，纵向切片推进）

- **M1-1** 稳定 schema 与状态机：会议来源/逐字稿/结构化笔记/证据引用/审批候选/执行动作/处理状态；
  `discovered→fetched→archived→processed→pending-review→applied/ignored` 及 `unavailable/failed`；
  幂等键 `meeting_id + note_id`（本地导入用内容哈希）。**建议从这里起步**（纯领域，可测）。
- **M1-2** 会议发现与原文归档：模型调用前先可靠保存逐字稿证据层。
- **M1-3** 云端结构化处理：完整原文优先单次；接近上下文上限才分段汇总；失败进错误队列不产半成品。**已完成并真机验收。**
- **M1-4** 集中审批与写回：`_vault/review/meetings.md`（勾选/删除线`#ignore`/原地改）+ 批量应用；
  路由「有期限或涉他→飞书任务；明确下一步→项目主笔记；未成熟→项目 inbox；不明→全局 inbox」；审计归档。
- **M1-5** `wb status` + 用量账本 + 月度软预算告警 + 待确认积压分级通知（5 条或最老 >3 天）。
- **M1-6** `wb ask`：路径/frontmatter/ripgrep 召回 + 云端模型带来源回答；默认不保存，`--save` 存 qa-insight。
- **M1-7** 历史补导：显式日期范围、先显示数量/费用预估、中断续跑、默认不生成行动候选（`--include-actions` 才生成）。

## M1 严格验收门槛（PRD L44，全过才进 M2）

3 场真实会议归档+结构化且可追溯无重复；审批的批准/拒绝/修改各至少一次且未确认零写回；10 个真实问答均有来源；
一次可恢复故障 + 一次「初调+3 重试」全失败（进错误队列、零半成品、零自动换模型）；用量账本核对；积压阈值通知只响一次。

## 协作约定（沿用）

- 远端用 **SSH**；只提交 SummitWorkbench 与 `_vault`，**不代提交用户的其他项目仓库**。
- 凭据只进 macOS Keychain（service 名见 ADR 0004/0005/0007），不入 git/日志/模型上下文。
- 每个工作包：开分支 → 实现+测试 → 质量门全绿 → 合并 `main` → 推送；对应 ADR 留档。
- prompt 版本化于 `prompts/`，禁止内联；业务 schema 不写死供应商/模型名。
- 飞书凭据均已在本机 Keychain 就绪；`~/.config/summit_workbench/config.toml` 已配 `[feishu]` 与 `[models.shared]`。

## 起步建议

M1-1、M1-2、M1-3 已完成并真机验收。下一步 M1-4：从结构化笔记生成稳定候选，汇入
`review/meetings.md`，支持批准、拒绝、原地修改与幂等批量写回。继续沿用“先证据后建议、先归档后写回、
逐里程碑封闭验证”。
