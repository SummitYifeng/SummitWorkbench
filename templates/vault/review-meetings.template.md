---
date: {{date}}
type: approval-page
status: active
project: global
---

# 会议提取待确认

> 会议提取结果影响执行系统前的**唯一审批入口**（PRD 3.1.9 L21）。
> 交互：`- [ ]` 待确认、`- [x]` 批准、`~~条目~~`（可选追加 `#ignore`）拒绝；
> 可在批准前原地修改正文 / `target_project` / 截止日期 / 拟写入位置。
> 勾选后须显式运行一次批量应用命令；仅编辑保存本文件**不会**触发写回。
> 每条候选必须有稳定 ID、类型、目标项目、拟执行动作与来源引用；缺目标或依据者不可勾选。

<!-- 按会议分组追加候选，例如（普通注释中的示例不会被解析器当成真实条目）：

## 2026-08-30 产品周会  [[meetings/notes/2026-08-30-产品周会]]

- [ ] `id: mtg1#action-item-0` [action-item] 周三前给老王第 3 章样章
  - target_project: HIC_SWB_LaTEX
  - route: feishu-task
  - due_date: 2026-09-03
  - evidence: 张三 00:12:30
  - actionable: yes
  - note: [[meetings/notes/2026-08-30-产品周会]]
  - transcript: [[2026-08-30-产品周会-transcript]]
  - error:
-->
