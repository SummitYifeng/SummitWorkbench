# ADR 0013 · M1-6 第二大脑问答

- 状态：✅ 实现完成并真机冒烟；⏳ 待 10 个真实问答的显式验收（PRD L44）
- 日期：2026-08-31
- 里程碑：M1-6（`wb ask`）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §6 M1-6；PRD L23

## 决策

- **召回（本地、确定性、可测）**：`workflows/ask/retrieval.py` 扫 vault Markdown，按
  路径 / frontmatter / 全文子串（ripgrep 等价）打分：标题 ×3、frontmatter/路径 ×2、正文 ×1；
  中文单词补 2-gram 改善子串召回。默认排除派生 `qa-insight`（事实检索不吃自己产出）、原始
  `meeting-transcript`（证据层、体量大）与临时 `approval-page`。支持 `--project` 限定与 `--limit`。
- **只引用进入上下文的来源**：每条来源带稳定 `source_id`（vault 相对路径），进入 `<source>` 块。
  模型回答（`domain/qa.py`：`facts` 带 source_id、`suggestions`、`conflicts` 并列、`unanswerable`）
  解析后由 workflow 核验，**剔除引用了未提供 source_id 的事实/冲突**（`dropped_sources` 回显）。
- **事实与建议分区、冲突并列**：schema 强制 `facts` 与 `suggestions` 分离；证据矛盾进
  `conflicts`（每话题 ≥2 立场各带来源），不替用户裁决。
- **无召回不调用模型**：召回为空直接返回 `unanswerable`，不空烧 token。
- **韧性**：模型返回空/非法 JSON 属推理型模型的瞬时问题，按退避重试（复用 M1-3 约定，
  `MAX_RETRIES`）；多次调用用量合并计入账本。
- **默认不保存**：`--save` 才写 `qa-insight`（`insights/`，`project: global`，回链来源与冲突），
  同问题同日幂等不覆盖。

## 上下文预算

复用 `estimate_tokens` 与 `[models.*]` 的 `context_window_tokens × context_safety_ratio`，
扣除 prompt/问题/输出预留后按相关度顺序纳入来源，超预算即停，避免长笔记挤爆上下文。
`qa` 能力缺省回退 `[models.shared]`。

## 验收

- Ruff、mypy strict、pytest **207 项**全绿（+13）：召回打分/排除/项目过滤/limit、schema 与
  越界引用剔除、无召回不调用模型、瞬时空响应重试、qa-insight schema 合规与幂等、CLI 注册。
- 真机冒烟：对真实 `_vault` 运行 `wb ask "网课系统里老师账户怎么注册和分配角色"`，
  正确召回会议笔记与项目主笔记、给出带来源事实与分区建议、`--save` 落 qa-insight 且 vault 校验通过。
  另修复 deepseek-v4-flash 偶发空响应（现按重试恢复）。
- 严格验收（PRD L44「10 个真实问答均有来源」）待显式回归。
