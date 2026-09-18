---

date: "{{date}}"
type: meeting-note
status: pending-review
meeting_id: "{{meeting_id}}"
note_id: "{{note_id}}"
source: feishu-note
projects: ["{{project}}"]
transcript: "[[{{date}}-{{title}}-transcript]]"
model: "{{model_id}}"
prompt_version: "{{prompt_version}}"
---

# {{title}}

## 一分钟摘要

<!-- 结论、重要变化、最需注意事项；一屏内读完 -->

## 会议信息

<!-- 时间、参会人、来源标识（飞书 meeting_id / note_id） -->

## 事实与进展

## 已形成决策

## 明确行动项

<!-- 只放会议明确形成的行动项；模型推断的内容不入库 -->

## 未决问题

## 关联项目

## 证据索引

<!-- 指向逐字稿中的说话人 + 时间戳或稳定段落锚点 -->
