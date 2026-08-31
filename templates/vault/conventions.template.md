---
date: {{date}}
type: conventions
status: active
project: global
---

# 工作 vault 约定

> 本 vault 继承 [MyKnowledge 知识库规范](../MyKnowledge/90_System/Standards/knowledge-base-conventions.md)，
> 并叠加 SummitWorkbench 的执行层约定（PRD 3.1.5 / 3.1.7 / 3.1.9）。
> **第一读者是 Agent**：稳定路径、统一 frontmatter、固定区块标题优先于人类排版偏好。

## 1. 目录结构

```
_vault/
├── conventions.md          # 本文件
├── daily/                  # 每日笔记（晨间指挥台，M2）
├── projects/               # 项目主笔记（固定区块）
├── logs/                   # 单次工作记录（环 B 收尾自动生成，M3）
├── meetings/
│   ├── notes/              # 结构化会议笔记（理解与行动层）
│   └── transcripts/        # 完整逐字稿（证据层）
├── review/
│   ├── meetings.md         # 会议提取唯一待确认入口
│   └── archive/            # 已应用/已忽略条目审计
├── reviews/weekly/         # 跨项目周复盘（M2）
├── insights/               # 用户显式保存的问答洞察
├── inbox.md                # 全局收件箱（机器可读）
└── _signals/               # 信号快照、用量账本、错误队列（不进 schema 校验）
```

## 2. 统一 frontmatter

全部笔记必须包含 `date` / `type` / `status`。

- 单项目笔记用 `project: <id>`；跨项目会议用 `projects: [<id>, ...]`；两者不可同时出现。
- 全局系统笔记用 `project: global`。
- `type` 允许值：`project-main`、`work-log`、`meeting-note`、`meeting-transcript`、
  `daily`、`weekly-review`、`qa-insight`、`inbox`、`conventions`、`approval-page`。
- `status` 词表：`active`、`paused`、`archived`、`draft`、`superseded`、
  `pending-review`、`generated`、`applied`、`ignored`。
- `date` 一律 `YYYY-MM-DD`。

校验：`wb vault check` 对全库执行上述规则与固定区块检查。

## 3. 固定区块（标题不得改名，Agent 依赖其定位）

- 项目主笔记：`## 当前状态`、`## 下一步`、`## 阻塞`、`## 决策记录`。
- 结构化会议笔记：`## 一分钟摘要`、`## 会议信息`、`## 事实与进展`、`## 已形成决策`、
  `## 明确行动项`、`## 未决问题`、`## AI 建议`、`## 关联项目`、`## 证据索引`。

会议明确形成的行动项只进 `## 明确行动项`；模型推断只进 `## AI 建议`，禁止混写。

## 4. inbox 机器可读格式（PRD 3.1.7）

- 待处理条目必须以 `- [ ] ` 开头，一行一条，可带 `#项目名` 标签。
- 已处理条目移出「待处理条目」区，**不留占位行**。
- 积压数 = 「待处理条目」区中 `- [ ] ` 开头的行数。

## 5. 分层与证据

事实、待确认推断、AI 建议必须分层保存与展示。会议知识可自动归档；任何改变项目状态、
下一步、阻塞或创建飞书任务的写回，必须经 `review/meetings.md` 一次确认。
