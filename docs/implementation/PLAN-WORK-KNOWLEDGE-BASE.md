# 计划 · 工作知识库重建 + 第二大脑/决策层改造 + 双机完全重装

> **本文件是「步骤与验证」的唯一真源**；需求真源是 §1 的 4 轮选择题结论。
> 执行者读不到对齐过程的对话，因此本文件自包含。
> 事实基线见 §2（2026-09-14 实测）。目录命名与字段定义以 §3 为准（架构由 §5 Phase 2 的样例门决定）。

---

## §0 一句话

先把两台机器**完全重装成新身份**（新 workspace_id、新远端、空库），再把**工作知识库按「两条项目管线 + 主题簇」从零重建**，
让桌面上 8 份梳理材料以 C-lite 粒度入库、决策重新提炼；最后把 **Workbench 的第二大脑补成「能检索 + 能决策 + 能沉淀」**：
新增「知识沉淀」审批落点、决策台账页、库内 SOP 与界面使用指南，并用 4 个真实问题真跑验收。

---

## §1 已对齐的需求（4 轮选择题结论 · 真源 · 不得擅自更改）

### 1.1 知识与架构

| # | 议题 | 结论 |
|---|---|---|
| 1 | 架构主线 | **先看样例再定**：用 HII IP 全景总结真落两套到库外，命令行做检索对比后由使用者选 |
| 2 | Workbench 项目口径 | **收敛为 2 个**：`hii-affairs`（title「HII 事宜」）/ `it-development`（title「IT 开发与进度」）；其余一切细分降级为主题簇页 |
| 3 | 【IT开发与进度】细分 | **5 个主题页**：报名与课程生命周期 / 门户 CMS 权限 / 本地 AI 与企业知识库 / 手机端 / 业务电子化 |
| 4 | 【HII事宜】细分 | **3 个主题簇**：Loyalty / 商标 IP / 日常人员往来；**簇下允许子页**（来华接待 SOP、当前来华个案作为子页挂在「日常人员往来」簇下） |
| 5 | 主题簇页的 type | **复用 `type: note`**，不新增 type（零契约风险） |
| 6 | 旧库处置 | **全删重建**；已提炼的决策**由我从桌面材料重新提炼**；**彻底不看旧库**（不作参考） |
| 7 | 规范与模板 | **连 conventions 也从零写**，只保留 app 硬约束（固定区块标题、type 词表、`inbox.md` 格式、必填 frontmatter、`project`/`projects` 互斥） |
| 8 | 空库起步 | **先骨架再入库**（README + 新 conventions + templates + index + 目录 + 2 个项目主页，`wb vault check` 先跑绿） |
| 9 | 社区 / 人事 | **顺手建库骨架，只建空骨架**（主页 + 簇目录 + notes/sources），内容待材料到位；**不作为 Workbench 项目** |

### 1.2 入库与双链

| # | 议题 | 结论 |
|---|---|---|
| 10 | 入库粒度 | **C-lite**：1 篇 `source`（逐字原文，不可变）+ 1 篇分析笔记（结论按 `##` 分节）+ 决策单独成篇 |
| 11 | 双链 | 候选清单机制**废弃**（上一轮就是它挂死的）；**直接写回正文**，事后在 Obsidian 审阅增删；每篇 1–3 条强关联 + 一句关系理由 |
| 12 | 入库确认 | 无二次确认清单；引用粒度统一 `路径#区块` |

### 1.3 检索与工作流

| # | 议题 | 结论 |
|---|---|---|
| 13 | 检索范围 | **纯文本做深（不引入向量库/嵌入/RAG）+ 新增决策台账层**；不做跨会话长期记忆 |
| 14 | 决策层形态 | 库内决策卡（状态/依据/影响/复核/互链）+ **Workbench 新增「决策」页**（按管线/主题/状态筛选，可看演进与被推翻关系） |
| 15 | 知识沉淀落点 | **要补**：审批管线新增第 7 个落点「知识沉淀」；落法 = **明确目标（管线 + 主题页 + 落点区块）+ 使用者确认后写回**，每条带 `路径#区块` 出处 |
| 16 | 会议纪要入口 | **先用现有入口**（今日页「＋导入会议纪要」拖逐字稿 + 捕捉行 AI 分类），不新开发 |
| 17 | SOP 交付 | ① 库内一页《工作知识库使用 SOP》；② Workbench 内使用指南页（更新既有 `web/src/guide.md`） |
| 18 | 明确不做 | 定期回顾产物、重双机验收、微信/邮件/Office 接入（均未选） |

### 1.4 重装与验收

| # | 议题 | 结论 |
|---|---|---|
| 19 | 执行次序 | **重装提到最前**：先在最终身份上立库，避免二次绑定与 Air 双重克隆 |
| 20 | 重装范围 | **完全重装**：卸载 app + 清 `~/Library/Application Support/SummitWorkbench` + 重走 onboarding（飞书 + DeepSeek + 主备声明） |
| 21 | 身份与远端 | **换新 workspace_id + 删除旧远端**（`yifeng93/WorkKnowledge`，删除后**同名新建空私有仓库**；不 archive） |
| 22 | 安全网 | **不留任何备份，彻底删干净**（不可逆；执行前设最终 GO 检查点，见 §4） |
| 23 | Air | 最后一步接入（全新克隆新库，角色自动 `secondary`；Studio 为 `automation_primary`） |
| 24 | 验收问题 | 4 条（§8.1）；写成可重复运行用例并真跑留证 |
| 25 | 提交 / CI | 提交带 `[skip ci]`，**不跑远端 CI**；本机全部门禁必须绿 |

---

## §2 事实基线（2026-09-14 实测）

| 资产 | 事实 |
|---|---|
| App | `/Applications/SummitWorkbench.app` = **0.4.8**；主设备声明 `automation-primary.json` = Studio（`51885d3d-…`，generation 3） |
| workspace | `_vault/.summit-workbench/workspace.json`：`workspace_id = bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f`，`display_name = _vault` |
| 索引 | `~/Library/Application Support/SummitWorkbench/kb-index.sqlite`（2.7 MB），**在 vault 之外**（符合规范） |
| 工作库 | `~/Documents/Work/_vault`：56 篇 md；8 篇 `decisions/`、5 个 `projects/*.md`（**正是界面里的「好多拆分」**）、4 篇 HII 分析 + 1 篇 IT 分析、3 篇会议笔记、2 篇逐字稿、6 个 index 页 |
| git | 工作库 5 个提交；远端 **`https://github.com/yifeng93/WorkKnowledge.git`**（仓库名是 `WorkKnowledge`；本次删除后**可复用同名新建**） |
| 运行态 | app **正在运行**（pid 95832；bundle server pid 95835 / port 59514）；**没有 SummitWorkbench 的 launchd job**（无需卸载 launchd） |
| 重装源 | `dist/releases/0.4.8/arm64/SummitWorkbench.app`（已签名并公证；同目录另有 `SummitWorkbench-0.4.8-arm64-INTERNAL-DEV.dmg`、`SHA256SUMS`、`release-metadata.json`） |
| 凭据落点 | Keychain service = `com.summitworkbench.credentials.<workspace_id>`（**换新 workspace_id 后旧凭据即失效，需显式清理才算重装干净**）；`Application Support/secrets-backup/feishu-defaults.json`；`profiles/<ws>/config.toml` 只存 `credential_account` 等引用，**不存密钥值** |
| 必须人工重填 | **DeepSeek API Key**（旧 Keychain 项属旧 workspace）、**飞书 OAuth 授权**；`git_username` = `yifeng93`、`user.email` = `77276503+yifeng93@users.noreply.github.com`；`gh` CLI 已登录（`repo` scope，可建/删仓库） |
| 工作库根 | `~/Documents/Work/`：`.obsidian/`（**保留**）、`_vault/`（本次清空重建）、`.wb.lock`（0 字节，2026-09-02 遗留）、`.DS_Store` |
| 失效资产 | `review/kb-intake.md` 与 `review/_intake/hii-royalty-visits.md` 共 **111 / 108 条死链**（指向已被 C-lite 收编删除的 C 粒度原子笔记）；双链候选至今未确认 |
| 审批落点 | `RouteTarget` = `feishu-task` / `feishu-meeting` / `project-main` / `project-followup` / `project-inbox` / `global-inbox`；**无「知识沉淀」** |
| 检索现状 | **已实现**：`repositories/kb_index.py`（FTS5+trigram，库外）、`workflows/ask/{router,fusion,chunking,retrieval}.py`（查询路由、多信号融合、`路径#区块` 引用、双链 1 跳、别名解析）、`TYPE_AUTHORITY` 已含 `decision: 0.9` / `index` 与线索主页 `1.4` |
| 检索缺口 | 决策**台账语义**（状态/被推翻/复核日期）与决策**页面**缺失；项目/主题过滤未针对性扩展；权威加权对「项目主页 + 主题簇页」未校准 |
| 使用指南页 | **已存在**：`web/src/guide.md`（359 行）+ `web/src/features/guide/`（渲染/目录/搜索）→ 本轮只更新内容 |
| 硬约束（来自代码，不可违反） | 项目 = `_vault/projects/*.md` 中 `type: project-main`；项目 ID 只允许 `[A-Za-z0-9_-]`（中文只能进 `title`/`aliases`）；`project-main` 的 scope=`single`；`project` / `projects` 互斥；`project-main` 固定区块 `## 当前状态/## 下一步/## 阻塞/## 决策记录`；`type` 词表只做加法；`inbox.md` 待办行 `- [ ] ` 开头；检索的项目过滤同时认 frontmatter `project` 与路径前缀 `projects/<id>` |
| 桌面材料 | `~/Desktop/当前材料/` 共 8 份：HII 4（IP 全景 1038 行 / Royalty 1162 行 / 来华手册 869 行 / 当前来华 568 行）+ IT 4（开发计划 1217 行 / IT 对齐纪要 58 行 / 视频会议 (1) 69 行 / (2) 144 行）。**交接文档提到的 (3).txt 不存在**（当前材料里没有该文件） |

---

## §3 目标形态

### 3.1 三层模型（不新增项目、不新增 type）

```
项目层（Workbench 视角 · 恒定 2）   _vault/projects/hii-affairs.md · it-development.md        type: project-main
主题簇层（知识视角 · 可扩展 N）      _vault/<line>/clusters/*.md  +  簇下子页                 type: note, project: <2 个之一>
素材/证据层（只增不改）              _vault/<line>/sources/ · meetings/{notes,transcripts}/ · decisions/
执行层（Workbench 契约不动）         daily/ logs/ review/ inbox.md inboxes/ artifacts/ insights/
导航层                               index/{workstreams,projects,people,decisions,timeline}.md
```

- **永不新增 `projects/*.md`**：新增主题 = 建 `<line>/clusters/<slug>.md` → 在项目主页 `## 主题簇` 加一行 → 在 `index/projects.md` 加一行。
- 主题簇页与子页固定区块沿用线索主页六区块：`## 现在在哪`、`## 关键结论`、`## 未决问题`、`## 决策记录`、`## 时间线`、`## 关联`（写进新 conventions §4）。
- 会议笔记的 `projects:` 值**必须**只出现 `hii-affairs` / `it-development`，否则审批路由解析不到项目、会落全局 inbox。

### 3.2 两套候选架构（Phase 2 样例的对比对象）

**变体 α · 工作线优先（改造版）**——保留 `type: workstream` 主页，多加一层主题簇：

```
_vault/
├── README.md  conventions.md  sop.md
├── index/{workstreams,projects,people,decisions,timeline}.md
├── projects/{hii-affairs,it-development}.md        # Workbench 只看这两个
├── hii/
│   ├── hii-loyalty.md                              # type: workstream（线索主页）
│   ├── clusters/{royalty,ip-trademark,relationships}.md
│   ├── visits/{china-visit-sop,danny-kim-2026-09,nita-crystal-2026-12}.md
│   ├── notes/  sources/
├── it/
│   ├── it-roadmap.md                               # type: workstream
│   ├── clusters/{enrollment,portal-cms,local-ai,mobile-app,digitization}.md
│   ├── notes/  sources/
├── community/  hr/                                 # 空骨架
├── decisions/  meetings/{notes,transcripts}/  templates/
├── daily/ logs/ review/ inbox.md inboxes/ artifacts/ insights/
└── _signals/ .summit-workbench/
```

**变体 β · 项目管线优先**——`projects/` 的两个管线页**即**管线首页（承载原 workstream 六区块），不再有独立线索主页：

```
_vault/
├── README.md  conventions.md  sop.md
├── index/{projects,people,decisions,timeline}.md
├── projects/{hii-affairs,it-development}.md        # 唯一入口页，含「现在在哪/关键结论/未决/决策/时间线/主题簇」
├── hii/{clusters,visits,notes,sources}/            # 纯知识/素材目录，无 workstream 主页
├── it/{clusters,notes,sources}/
├── community/  hr/
├── decisions/  meetings/  templates/  daily/ logs/ review/ inbox.md inboxes/ artifacts/ insights/
└── _signals/ .summit-workbench/
```

**两套的实质差别**：α 有「线索主页 + 项目主页」两页都可能被当成首页（漂移风险，但保留了工作线视角）；
β 只有一页（单一入口，界面与库完全一致，但丢掉 `workstream` 维度）。样例里会给出同一份材料的两种落法 + 召回差异。

### 3.3 frontmatter（新规范自定，字段序固定）

```yaml
id: 2026-09-14-a1b2          # 稳定 ID，改名不变
title: 中文自然语言标题
area: work
workstream: hii              # hii | it | community | hr | company | cross（用于按线聚合与检索过滤）
project: hii-affairs         # 唯一项目绑定；跨项目用 projects: [...]（二者不可同时出现，app 强校验）
type: note                   # app 词表内取值，只做加法
domain: royalty              # 主题簇标识（cluster slug）
status: active               # app 词表：active|paused|archived|draft|superseded|pending-review|generated|applied|ignored
created: 2026-09-14
updated: 2026-09-14
date: 2026-09-14             # app 必填（事件日期）
summary: 一句话说明这篇解决什么问题
tags: []
aliases: [中文别名, 旧文件名]
source:                      # 溯源，C-lite 的幂等键
  kind: doc                  # transcript|meeting|doc|chat|feishu|email|manual
  ref: hii/sources/20260912-hii-hic-ip-overview.md
  date: 2026-09-12
  hash: <sha256 前 16 位>
people: []
org: [HIC, HII]
confidential: false
```

- **决策卡追加字段**（只用于 `type: decision`，全部可选 → 不破 app 契约）：
  `decision_status: effective | superseded | under-review`、`decided_on: YYYY-MM-DD`、`review_on: YYYY-MM-DD`、
  `supersedes: [<id>]`、`superseded_by: [<id>]`。
- `draft` 不进检索；`superseded` 保留在原处供追溯（沿用既有语义）。

### 3.4 双链规则

- 目标用**稳定文件名**，附中文别名：`[[ip-trademark|商标 IP]]`；块级用 `[[ip-trademark#关键结论|商标 IP·关键结论]]`。
- 每条链接后写**一句关系理由**；同一关系只写在最能解释它的那一篇。
- 机器目录（`_signals/`、`.summit-workbench/`、`templates/`）不参与双链。

---

## §4 不可逆步骤与检查点

| 步骤 | 不可逆性 | 处置 |
|---|---|---|
| 删除旧 `_vault` 内容与 git 历史 | 高 | 与下两条合并为 **Phase 1 第 2 步的同一个 GO**；使用者已明确选「不留备份」，此处只确认清单一次，不再劝 |
| 删除旧远端 `yifeng93/WorkKnowledge` | **最高**（云端不可恢复） | 同上；GO 之后连续执行，中途不夹其它动作 |
| 清空 `~/Library/Application Support/SummitWorkbench` + 旧 workspace 的 Keychain 凭据 | 中（可重建；代价是重填 DeepSeek Key + 重新飞书授权） | 同上；先确认 app 已退出。**保留** `git:github.com` 等 CLI 共用凭据 |
| 换新 workspace_id | 低（代价是两台机器都要重走 onboarding） | 已选，接受 |
| app 契约级改动（`RouteTarget` 新增值、索引 schema） | 低（有快照与测试护栏） | 同步更新 `docs/contracts/web-route-contract.json` 与测试 |

**执行顺序铁律**：Phase 1 的重装 → 空库 → 绑定新远端全部完成并冒烟通过后，才进入 Phase 2。中途失败就停下报告，不做「先删着、以后再修」。

---

## §5 阶段计划

### Phase 0 · 基线快照（只读，5 分钟）

1. `defaults read /Applications/SummitWorkbench.app/Contents/Info.plist CFBundleShortVersionString`
2. `cat _vault/.summit-workbench/workspace.json` 与 `automation-primary.json`；`git -C _vault remote -v`、`git -C _vault log --oneline`
3. 记录本文件 §2 的数字（56 篇 md / 5 提交 / 5 个 projects）作为重建前的对照基线
4. **产出**：基线写进本文件 §2（若复测有变化）

### Phase 1 · 完全重装 Studio（最终身份 + 空库）

> **本阶段是唯一一次不可逆操作**，GO 之后连续执行到底，中途不夹其它动作；失败就停下报告。

1. **停应用 + 打印清单**：退出 `/Applications/SummitWorkbench.app`（当前 pid 95832 + server 95835），确认 `pgrep -f SummitWorkbench` 为空；
   无 SummitWorkbench 的 launchd job，不需要 `launchctl` 卸载。随后**打印下面第 3–5 步将删除的确切路径与仓库名**。
2. **最终 GO 检查点**（唯一一次确认；使用者已选定「不留备份」，此处不再劝，只确认清单）→ GO 之后从第 3 步连续执行到底，中途不夹其它动作。
3. **卸载 app**：删除 `/Applications/SummitWorkbench.app`。
4. **清机器状态**：删除 `~/Library/Application Support/SummitWorkbench/` 整目录
   （`device.json` / `registry.json` / `profiles/bf22c8d2-…/` / `kb-index.sqlite` / `kb-intake-samples/` /
   `locks/` / `backup/` / `feishu-auth-state.json` / `runtime.json` / `secrets-backup/`）；
   再按 service `com.summitworkbench.credentials.bf22c8d2-ef62-4bd3-9917-e76fdd3f7f0f` 逐项删除旧 Keychain 凭据
   （先枚举 account 再删；**不动** `git:github.com` 这类 CLI 共用凭据，否则 `git`/`gh` 会失效）。
5. **清旧资产（不可逆）**：
   - 清空 `~/Documents/Work/_vault/` 全部内容与 `.git/`（**保留** `~/Documents/Work/.obsidian/` 与库根；顺手删 `.wb.lock`）
   - `gh repo delete yifeng93/WorkKnowledge --yes`（⚑ 云端不可恢复）
   - 确认：`ls -A _vault` 为空、`gh repo view yifeng93/WorkKnowledge` 报 404
6. **重装 0.4.8**：`bash scripts/install-macos-app.sh dist/releases/0.4.8/arm64/SummitWorkbench.app --replace-running`
   → **以 `runtime.json` 与接口探针为准**；`install-macos-app.sh` 的 readiness 报错常是假失败（仓库既有铁律 #5）。
7. **onboarding**（`POST /api/onboarding/{preflight,create}`，或 GUI 连接向导）：
   新建 vault（`~/Documents/Work/_vault`）→ 得到**新 workspace_id** → 声明 **Studio 为主设备**（`automation_primary`）→
   **配置飞书**（重新 OAuth 授权；`app_id`/`scopes` 用内置默认）→ **配置 DeepSeek**（base_url + model_id + **重新填入 API Key**）
8. **新建空私有远端**：`gh repo create yifeng93/WorkKnowledge --private`（**不勾 README**）→ 再用「首次发布到远端」绑定：
   `POST /api/settings/git/remote/publish`（`workflows/remote_publish.py`）
9. **冒烟**：`/api/sync/status` = `ready`；空库能提交并推送；`.venv/bin/wb kb index` 空库通过；`.venv/bin/wb vault check` 通过
10. **验收**：Studio `automation_primary_device_id` = Studio；`_vault/.summit-workbench/workspace.json` 的 `workspace_id` **≠** `bf22c8d2-…`；
    新库远端已绑定；飞书与模型配置可用（问答能返回）

**本阶段需要你动手的地方**：第 2 步的 GO、第 7 步的飞书 OAuth 点击与 DeepSeek API Key 输入。



### Phase 2 · 样例与架构选型（库外，不改正式库）

1. 在 `/tmp/kb-spine-sample/{alpha,beta}/` 按 §3.2 两套结构**真落盘**同一份材料
   （`HII-HIC_IP关系与沟通全景总结_V2.1_2026-09-12.md`：它同时含决策、时间线、人物、多主题，最能暴露结构差异）：
   每套都含 `projects/hii-affairs.md`、簇页、分析笔记、决策页、source 页、`index/decisions.md`，yaml 与双链**真写**
2. **命令行检索对比**（不影响 GUI 绑定）：
   `wb kb index /tmp/kb-spine-sample/alpha --index-file /tmp/kb-spine-sample/alpha.sqlite`
   `wb kb index /tmp/kb-spine-sample/beta  --index-file /tmp/kb-spine-sample/beta.sqlite`
   `wb kb route "<问题>"`；如需完整作答，写一份临时 config 指向样例库后 `wb ask --config-file …`
3. **交付给使用者**：两套目录树 + yaml + 正文片段 + 双链 + 「同一问题的召回块差异」对照表
4. **门**：使用者选定 α / β（或混合）→ 冻结架构，写回本文件 §3.2
5. **产出**：`docs/implementation/kb-spine-sample-comparison.md`（对照记录，含结论）

### Phase 3 · 库骨架（先骨架再入库）

1. 按选定架构建目录骨架 + `README.md`（库入口：怎么用、去哪找）
2. **从零写 `conventions.md`**（只保留 app 硬约束）：§0 边界与硬约束 / §1 目录结构 / §2 frontmatter（含决策卡字段）/ §3 type 词表与 scope / §4 固定区块（含**主题簇页六区块**）/ §5 命名 / §6 附件 / §7 双链 / §8 决策记录 / §9 索引层 / §10 检索约定（`路径#区块`、事实/推断/建议分层、draft 不入索引）/ §11 `inbox.md` 与 `review/meetings.md` 契约 / §12 入库管线（C-lite）/ §13 审批落点（含新增「知识沉淀」）/ §14 本轮范围与将来扩展
3. `templates/`：`project-main` / `cluster`（主题簇）/ `note` / `decision` / `source` / `meeting-note` / `work-log` / `long-form-thought` / `index`
4. `index/`：`projects.md`（2 行）+ `decisions.md`（空台账）+ `people.md` + `timeline.md`（+ 变体 α 的 `workstreams.md`）
5. `projects/hii-affairs.md` + `projects/it-development.md`（四固定区块 + `## 主题簇`；title/aliases 按 §1 表 #2）
6. `community/` + `hr/` 空骨架（主页 + `clusters/` + `notes/` + `sources/`，正文写一行「待材料到位」）
7. `sop.md`（占位，Phase 6 定稿）
8. **验证**：`wb vault check` 绿；`wb kb index` 绿；`git status` 干净可提交

### Phase 4 · 首批入库（C-lite，桌面 8 份 = 唯一来源）

| 材料 | 落盘产物 |
|---|---|
| IP 全景总结（1038 行） | `hii/sources/20260912-hii-hic-ip-overview.md`（逐字）+ `hii/notes/20260912-hii-hic-ip-analysis.md`（结论按 `##`）+ `hii/clusters/ip-trademark.md` |
| Royalty 规则与历程（1162 行） | `hii/sources/20260911-hic-hii-royalty-rules.md` + `hii/notes/20260911-hic-hii-royalty-analysis.md` + `hii/clusters/royalty.md` |
| 来华接待手册（869 行） | `hii/sources/20260913-hic-hii-china-visit-manual.md` + **子页** `hii/visits/china-visit-sop.md` |
| 当前来华事项（568 行） | `hii/sources/20260913-hic-hii-current-visits.md` + **子页** `hii/visits/danny-kim-2026-09.md`、`hii/visits/nita-crystal-2026-12.md` + `hii/clusters/relationships.md` |
| IT 开发计划与进度（1217 行） | `it/sources/20260912-hic-it-roadmap-progress.md` + `it/notes/20260912-hic-it-roadmap-analysis.md` + 5 个 `it/clusters/*.md` |
| 智能纪要 IT 对齐 2026-08-03 | `meetings/notes/20260803-it-alignment.md`（九区块）+ `it/sources/20260803-it-alignment-intelligent-minutes.md` |
| 视频会议 (1)（2026-08-24） | `meetings/transcripts/2026-08-24-luo-yifeng-video-meeting-1-transcript.md` + 会议笔记 |
| 视频会议 (2)（2026-09-07） | `meetings/transcripts/2026-09-07-luo-yifeng-video-meeting-2-transcript.md` + 会议笔记 |

执行细则：

1. **source / transcript 逐字入库**，不改写原文；`## 来源` 写「原件路径 + 收到日期 + sha256」；幂等键 = `source.ref` + `source.hash`（重复入库不产生新笔记；同 ref 不同内容**报冲突退出**，不覆盖）
2. **决策重新提炼**（目标 10–15 篇 `decisions/`，六区块 + `## 证据` 逐条 `路径#区块` + 逐字引用），候选清单：
   - HII：登记主体=HII / filing 先于 License 执行 / 「活满」与「和夫曼之旅」分开管理 / Scholarship=Discount 不产生 Royalty / 酒店成本按 Gross（含 VAT）/ 第三期首次付款费率人数从第一档重新起算 / 来华接待三阶段 SOP / 来华启动时点规则 / Danny 案例「工作段保障 + 私人段独立支持」
   - IT：报名系统重定义为课程生命周期系统 / 权限模型 Level 1–5 / 9 月 P0 权限清理与账户治理 / 业务电子化「财务先行、不预设第二部门」/ 手机端 V1 服务对象=学员 / 本地 AI 两个方向（内部 AI Chat + 企业知识库）
3. **双链直接写回**（不做候选清单）：每篇 1–3 条强关联 + 关系理由；source 页 `## 关联` 至少 1 条回链分析页
4. **index 回填**：`projects.md`（2 个 + 主题簇说明）、`decisions.md`（倒序 + 一行摘要 + 状态）、`people.md`（按 frontmatter 聚合，可脚本再生成）、`timeline.md`（跨线转折点）
5. **块级锚点自检**：所有 `[[页#区块]]` 与 `路径#区块` 引用必须命中真实 `##` 标题（上一轮踩过「原件 H2 降级后锚点失效」的坑）
6. **验证**：`wb vault check` 全绿；逐字比对（source ↔ 原件正文 0 差异）；双链 0 broken；幂等三模式（重复 / 冲突 / 去重）真跑

### Phase 5 · 检索与决策层改造（代码）

1. **决策台账层（库侧）**
   - `scripts/kb_index_decisions.py`（新增，仿 `scripts/kb_index_people.py`）：按 frontmatter 聚合生成/校验 `index/decisions.md`
   - 决策卡字段写进 `templates/decision.template.md` 与新 conventions
2. **索取与过滤（检索侧）**：`workflows/ask/retrieval.py` 增加 `decision_status` / `domain`（主题簇）过滤；`fusion.py` 校准权威加权（项目主页 + `## 主题簇` 块 > 主题簇页 > 散记），权重可配可测
3. **索引（如需）**：`kb_index.py` 的 `notes` 表已存 `meta_json` → **优先不扩列**（决策字段从 `meta_json` 解析，零 schema 风险）；若确需列，则 bump schema 版本并依赖既有「不匹配即删表重建」机制
4. **决策页（Workbench）**：新增 `/api/decisions`（读索引 + meta_json）+ `web/src/features/decisions/`（按管线/主题/状态筛选、看演进与 `supersedes` 关系）→ **必须**同步 `docs/contracts/web-route-contract.json`（`scripts/update-web-route-contract.py`）
5. **知识沉淀落点（审批管线第 7 个落点）**
   - `domain/review.py`：`RouteTarget` 新增 `KNOWLEDGE_NOTE = "knowledge-note"`；`route_candidate` 增加规则：**明确的内部结论/知识、且项目已解析** → `knowledge-note`
   - 审批页呈现：`webapp/review_view.py` + `web/src/features/review/`（显示目标管线 + 主题页 + 落点区块）
   - 写回实现：新增 knowledge sink writer（写入目标主题页的 `## 关键结论` / `## 未决问题`，或写入 `decisions/`），每条带 `路径#区块` 出处；走既有 mutation runtime（`wb:` 留痕 + 双机同步）
   - 落法按 §1 表 #15：**明确目标 + 使用者确认后写回**
6. **使用指南页**：更新 `web/src/guide.md`（两条管线 / 主题簇 / 怎么审批 / 第二大脑怎么问），复用既有 `features/guide`
7. **修 BUG-1（首次发布）**：`publish_workspace_to_remote` 把本次凭据透传给真 vault 的 backend；暴露被吞掉的真因；补「全新 workspace → publish」回归测试
8. **测试**：索引（增量 + 全量）/ 路由 / 融合排序 / `路径#区块` 引用 / 去重 / 别名解析 / 幂等各一例；新增落点与决策过滤做**变异验证**
9. **门禁**（逐条必须绿）：
   ```
   web/node_modules/.bin/tsc --noEmit -p web/tsconfig.json
   npm --prefix web run test:frontend
   npm --prefix web run build && node web/scripts/verify-build.mjs src/summit_workbench/webapp/static
   .venv/bin/python -m pytest --cov -q
   .venv/bin/ruff check && .venv/bin/ruff format --check
   .venv/bin/mypy
   .venv/bin/python scripts/secret_scan.py
   WB_PACKAGED_APP=/Applications/SummitWorkbench.app .venv/bin/python -m pytest tests/integration/test_packaged_app.py -q
   ```

### Phase 5 追加 · Phase 2 实测暴露的检索质量修复（必做，按优先级）

| # | 修复 | 落点 | 判据 |
|---|---|---|---|
| R1 | **权威加权校准**：结论型块（`## 关键结论`、`## 决定`、`结论N｜…`）正向加权；压掉 `README#怎么用`、`index/*` 这类导航块的过度影响 | `workflows/ask/fusion.py`（`weights`/`TYPE_AUTHORITY`/块级加权） | Q1 的 `clusters#关键结论`、`notes#结论二`、`decisions#决定` 必须进 top-5（现在是 0 命中） |
| R2 | **块边界扩到 `#`**：chunking 同时以 `#` 与 `##` 为边界，锚点取最近的块标题 | `workflows/ask/chunking.py` + `kb_index.py` | 原件 20 个 H1 章节可被 `路径#区块` 引用；样例的 `# 十、…`、`# 十三、…` 可定点 |
| R3 | **过滤一致性**：双链扩展（`fusion.py:243-295`）应用与初始召回相同的 `project`/`workstream` 过滤，或明确「豁免 global 导航页」的策略并写进 conventions | `fusion.py` | 按 `project=hii-affairs` 过滤后，结果不再混入 `project: global` 页（除非显式豁免并在轨迹里说明） |
| R4 | **路由启发式补强**：补「是不是/为什么/当时/选项/依据」等问句形态与 decision 触发词 | `workflows/ask/router.py` | Q2/Q3 不再落到「无关键词：按长度兜底」 |
| R5 | **decision 第 7 区块 `## 关联`**（契约级）：`domain/vault.py` 固定区块表 + 模板 + 测试 + 快照 | 见 §11 冻结项 | 决策页有合规的双链落点 |
| R6 | **source 索引策略**：保持整篇可检索（证据层必须可查），但确认 `source_penalty` + `max_chunks_per_note` 不会让原件块永远进不了 top-10；必要时对 `## 要点` 之外的块做白名单 | `fusion.py` / `kb_index.py` | 与 Q1 的 `source#6.1` 召回判据一起验 |

> 每项都要有**可判定的失败模式**（变异验证），并补进 `scripts/kb_acceptance.py` 的回归清单。

### Phase 6 · SOP 与验收

1. `_vault/sop.md` 定稿：《工作知识库使用 SOP》——上传会议纪要 → AI 分类 → 审批 → 沉淀/写回飞书 → 提问；人可读、Agent 可执行（一页）
2. 4 个真实问题写成**可重复运行**的用例（脚本或 pytest），真跑并把输出留到 `docs/acceptance/evidence/`
3. 本机全部门禁绿；`wb vault check` 绿；`wb kb status` 记录笔记数/块数/FTS5 可用性
4. 提交（**`[skip ci]`**，不跑远端 CI）

### Phase 7 · Air 接入（备用机器）

1. Air：退出 app → 卸载 → 清 `Application Support` → 重装 0.4.8
2. 走「从另一台 Mac 克隆」接新库；角色自动 `secondary`；Studio 的 `automation_primary_device_id` = Studio
3. 冒烟：两机 `/api/sync/status` = `ready` / `0/0`；一次真实提交在 Air 拉取可见；Air 上第二大脑能问答
4. 若角色显示不自洽：在另一台点一次「降级为备用设备」（既有已知行为）

---

## §6 代码改造清单（文件级，仅 Phase 5）

| 文件 | 改动 |
|---|---|
| `src/summit_workbench/domain/review.py` | `RouteTarget` 新增 `knowledge-note`；`route_candidate` 增加路由规则与优先级 |
| `src/summit_workbench/webapp/review_view.py` | 审批页透出「目标管线 + 主题页 + 落点区块」 |
| `src/summit_workbench/workflows/`（review 写回侧） | 新增 knowledge sink writer（带 `路径#区块` 出处 + `wb:` 留痕） |
| `src/summit_workbench/webapp/routers/decisions.py`（新增） | `/api/decisions`（筛选 + 演进关系） |
| `src/summit_workbench/webapp/app_factory.py` | 注册新路由 |
| `src/summit_workbench/workflows/ask/retrieval.py`、`fusion.py`、`router.py` | 决策状态/主题簇过滤；权威加权校准 |
| `src/summit_workbench/repositories/kb_index.py` | 仅在必要时扩列（优先用 `meta_json`） |
| `scripts/kb_index_decisions.py`（新增） | 决策台账聚合/校验 |
| `web/src/features/decisions/*`（新增） | 决策页 UI |
| `web/src/features/review/*` | 新落点呈现 |
| `web/src/guide.md` | 使用指南内容更新 |
| `docs/contracts/web-route-contract.json` | 快照同步（改路由后必跑脚本） |
| `tests/**`、`web/src/**/*.test.ts` | 新增/更新测试（含变异验证） |

**硬约束**：不改公开模块名、不为整洁合并模块、绝不 `force/reset/rebase/stash`、机器日志不写进 vault、索引库不放 vault 内。

---

## §7 交付物清单

**知识资产**
- 新 `_vault`：新 conventions / README / sop.md / templates / index / 2 个项目主页 / 3 个 HII 主题簇 + 子页 / 5 个 IT 主题簇 / 10–15 篇决策 / 8 篇 source 或逐字稿 / 会议笔记 / 社区与人事空骨架
- 新 `workspace_id` + 新空私有远端 + Studio 主设备声明

**代码资产**
- 「知识沉淀」审批落点（含写回与留痕）
- 决策页（API + UI）+ 决策台账聚合脚本
- 检索过滤与权威加权校准 + 测试
- 更新后的使用指南页

**文档资产**
- `docs/implementation/PLAN-WORK-KNOWLEDGE-BASE.md`（本文件）
- `docs/implementation/kb-spine-sample-comparison.md`（样例对照与选型结论）
- `docs/acceptance/evidence/`（4 个真实问题的真跑输出）

---

## §8 验收

### 8.1 四个真实问题（使用者选定 · 必须逐字保留为用例）

1. 「根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？」
2. 「Danny 来华目前还差哪些必须收口？下一步谁做什么？」
3. 「IT 当前的开发进度是什么，下一个阶段该怎么做？」
4. 「『活满』与『和夫曼之旅』为什么分开管理？当时还有哪些选项？」

要求：在 Workbench「第二大脑」问答完成；答案逐条带 `路径#区块` 出处；能在 Obsidian 核对到同一批笔记；
答不出时如实说明缺什么（数据缺失 / 索引缺失 / 排序融合缺失），不得用模型自身知识填空冒充通过。

### 8.2 质量门

| 门 | 判据 |
|---|---|
| `wb vault check` | 全绿（新库全部笔记） |
| source 逐字 | 与桌面原件正文 0 差异（机械校验） |
| 双链 | 0 broken；每条有中文别名与关系理由 |
| 幂等 | 重复入库不增生；同 ref 不同内容报冲突退出 |
| 索引 | `wb kb index` 增量 + 全量均可；`wb kb status` 记录笔记数/块数/FTS5 |
| 检索 | 4 个用例真跑通过并留证 |
| 代码 | §5 Phase 5 的全部门禁命令绿 |
| 双机 | Studio/Air `/api/sync/status` = `ready` / `0/0`（Air 在 Phase 7 后） |

---

## §9 明确不做（Non-goals）

- 不引入向量库 / 嵌入 / RAG（第一阶段不破硬边界）；不新增第三方依赖
- 不做跨会话长期记忆（`user_memory` 式）
- 不做定期回顾产物（周/月回顾页）——本轮未选，留待下一轮
- 不做重型双机验收编排（Air 接入是任务 1 的一部分，但不做多轮真机验收矩阵）
- 不接微信 / 邮件 / Office 附件 / 内部平台
- 不改飞书链路、双机同步语义、审批与 mutation runtime 的既有安全约束
- 不动 `_signals/`、`.summit-workbench/` 的机器语义
- 不把工作内容并入个人库 `MyKnowledge`，不改它与它的规范
- 不新增 `type`（主题簇页复用 `note`）；不新增 `projects/*.md`

---

## §10 风险与铁律

1. **不可逆**：删旧库 + 删旧远端 + 不留备份 + 换新 workspace_id。执行前一次 GO，之后连续执行。
2. **顺序**：重装在最前；Air 在最末；中间不夹其它破坏性动作。
3. **契约不能悄悄改**：固定区块标题、`inbox.md` 格式、路由/payload 字段、`RouteTarget` 取值 —— 改动必须同步快照与测试。
4. **写测试与文档要避开 `scripts/secret_scan.py` 的凭据形状**（URL 内嵌凭据、私钥 PEM 头、`password: "…"` 赋值）。
5. **`install-macos-app.sh` 的 readiness 报错常是假失败**：以 `runtime.json` 与接口探针为准。
6. **块级锚点是高危区**：source 入库时标题层级变化会让 `路径#区块` 失效（上一轮已踩），入库后必须机械自检。
7. **`[skip ci]`**：提交带跳过 CI，但本机门禁必须全绿。
8. **改动前先 grep 确认无引用**；删/移文件后跑全部门禁。

---

## §11 开放项（我已按你的选择设默认值，若不认可请指出）

| 项 | 默认 |
|---|---|
| 主题簇页文件名 | `hii/clusters/{royalty,ip-trademark,relationships}.md`；`it/clusters/{enrollment,portal-cms,local-ai,mobile-app,digitization}.md` |
| 来华子页命名 | `hii/visits/china-visit-sop.md`、`hii/visits/danny-kim-2026-09.md`、`hii/visits/nita-crystal-2026-12.md` |
| 决策篇数 | 10–15 篇（以「有明确决定 + 理由 + 影响」为准，凑数的一律不建） |
| 新远端仓库名 | `yifeng93/WorkKnowledge`（**删除旧仓库后同名新建**空私有仓库，不勾 README） |
| 社区 / 人事骨架深度 | 主页 + `clusters/` + `notes/` + `sources/`，正文一行「待材料到位」 |
| 变体 α 是否保留 `type: workstream` | 由 Phase 2 样例选型决定（β 则不用该 type；工作线只保留为 frontmatter `workstream` 字段 + 索引页） |
| 库内 SOP 位置 | `_vault/index/sop.md`（`type: index`、`project: global`），**不放库根**——根目录文件必须带 frontmatter |
| `README.md` | 库根，`type: index`、`project: global`（否则 `wb vault check` 必红） |
| `source.ref` 语义 | **冻结为「原件来源标识」**（本机绝对路径 / 飞书或邮件标识），**不自指本页**；幂等键 = `source.ref` + `source.hash`（原件 sha256），换机器后路径失效不影响去重 |
| 待建主题簇的写法 | **只写纯文本，不写双链**（写了会立刻死链）；簇页建立后再补 `[[…]]` |
| decision 的第 7 区块 | 新增 `## 关联`（**契约级改动**：`domain/vault.py` 的 decision 固定区块表 + 模板 + 测试 + 快照） |

---

## §12 执行进度（滚动更新）
### Phase 0 · 基线快照 ✓ 2026-09-14

- app 0.4.8 于 `/Applications`；运行 pid 95832 / server 95835 / port 59514
- 旧身份：`workspace_id = bf22c8d2-…`、`device_id = 51885d3d-…`（m3-studio）、generation 3
- 旧远端：`github.com/yifeng93/WorkKnowledge`（private、224 KB、5 个提交、最后推送 2026-09-13）
- 旧库：85 个文件 / 1.6 MB；`review/` 两个候选清单共 111 + 108 条死链

### Phase 1 · 完全重装 Studio —— 进行中

| 步 | 状态 | 结果 |
|---|---|---|
| 1 停应用 | ✓ | `pgrep -f SummitWorkbench` 已空 |
| 2 最终 GO | ✓ | 用户确认（不留备份） |
| 3 卸载 app | ✓ | 删除 `/Applications/SummitWorkbench.app`（71 MB） |
| 4 清机器状态 + 旧 Keychain | ✓ | 删 `Application Support/SummitWorkbench/`（6.2 MB）；删旧 workspace 凭据 3 项（`llm:shared:shared`、`git:github.com:Yifeng93`、`feishu:cli_aa1e751a357b9bd4:refresh_token`）；**保留** CLI 共用的 git 凭据与 `gh` 登录 |
| 5 清旧资产 | ✓ | 已清空 `_vault`（85 文件 + 5 提交 + `.git`）与 `.wb.lock`，**保留** `~/Documents/Work/.obsidian`；旧远端 `yifeng93/WorkKnowledge` 已删除并**同名重建为空私有仓库** |
| 6 重装 0.4.8 | ✓ | `install-macos-app.sh dist/releases/0.4.8/arm64/SummitWorkbench.app --replace-running` |
| 7a 新 workspace | ✓ | **新 `workspace_id = fb9494a4-a080-40dd-a5c3-fcc12d7dc2dd`**；新 `device_id = 0617854a-e193-4b3e-bb6d-fb5bb738937d`；`device_role = automation-primary`（Studio 主设备）；种子提交 `efe34be wb: onboarding create` |
| 7b 飞书授权 | ✓ | `feishu-auth-state.json`：本 workspace `status: connected` |
| 7c DeepSeek Key | ✓ | `[models.shared]`（base_url / model_id）已写；Keychain `llm:shared:shared` 已写入；真问答已返回 |
| 8 新远端 + 绑定 | ✓ | 远端 main = `efe34be`；profile `git_username=yifeng93` + `git_remote_url` 已写；Keychain 新作用域凭据 `git:github.com:yifeng93` 已写；upstream 已设（**绕过了 0.4.8 的 publish bug，见下**） |
| 9a 冒烟（本地） | ✓ | `wb vault check` → 2 篇通过；`wb kb index` → 2 笔记 / 18 块，FTS5 可用；`/api/onboarding/status` = `active` |
| 9b 冒烟（同步） | ✓ | `/api/sync/status`：`state=ready`、`ahead=0`、`behind=0`、`pending_commits=0`、`branch=main`、`automation_primary_device_id = 0617854a…`（= Studio） |
| 10 验收 | ✓ | 身份 / 远端 / 同步 / 飞书 / 模型 五项全过；`.venv/bin/wb ask "工作知识库的文件命名规则是什么？"` 真跑返回，事实带出处、事实与建议分层、含检索轨迹 |

> **Phase 1 是否收尾的判据（全部满足）**：`workspace_id ≠ bf22c8d2`、`automation_primary_device_id = 0617854a…`（Studio）、
> `/api/sync/status = ready`、飞书 `connected`、模型凭据在 Keychain、真问答能返回。
> **Air 不在本阶段**——按 §1.4 #23，Air 要到 Phase 7 才接入。

### Phase 1 已验证「不是缺口」的疑点（免得重复查）

- `wb ask` 的引用可能显示成笔记级 `[[conventions]]`，看着像没到块级。实测：`kb_index.Hit.anchor`
  在块有标题时返回 `路径#区块`（例如 `conventions#0. 边界与硬约束`），**只有第一个 `##` 之前的正文前言块**才返回裸路径。
  该次提问恰好命中前言块，故显示裸路径——**符合契约，不是 bug**。

### Phase 2 · 架构样例对照 —— 已完成，**待你选型**

对照记录：`docs/implementation/kb-spine-sample-comparison.md`（248 行，含目录树 / frontmatter / 双链清单 / 召回差异 / 逐项差异）。
样例库：`/tmp/kb-spine-sample/{alpha,beta}`（α 15 篇 136 块；β 13 篇 131 块）。

**我复核过的硬事实**：`wb vault check <路径>` 两套均 exit 0（**CLI 支持指定库外路径**）；`verify.py` 0 死链 0 失效锚点；
`wb kb index <vault> --index-file <库外>` 两套成功；`type`/`project`↔`projects`/固定区块/`id` 格式/`inbox` 契约全部合规。

**检索对比结论（`use_model=False`，3 问 × 全库 / 项目过滤）**

| 场景 | α 工作线优先 | β 项目管线优先 |
|---|---|---|
| 全库检索 | top-1 = `hii/hii-loyalty#关键结论`（`type: workstream` 权威 0.95） | top-1 = `projects/hii-affairs#关键结论`（`project-main` 权威 0.85） |
| **加 `project=hii-affairs` 过滤** | **`hii/hii-loyalty` 整页被丢弃**（`workstream` 强制 `project: global`），Q1 top-1 退化成 `notes#未决与待确认` | `projects/hii-affairs#关键结论` 始终在场，稳定 |
| 双链扩展 | 过滤后仍混入 `project: global` 页（`fusion.py:243-295` 未重复过滤） | 同样混入 `README` |

**结构性判断**：α 的「全库略优」只是权威分 0.95 vs 0.85 的产物，**校准权重后 β 同样拿到**；
而 β 在项目过滤下的稳定是**结构性的**（不可通过调权重补上）。⇒ 待你拍板（§11）。

### Phase 2 实测暴露的问题（已并入 Phase 5 修复清单与 §11 冻结项）

1. **H1 没有锚点**：原件 20 个 H1 章节（含 17 个正文节 + 附录）无法被 `路径#区块` 引用，
   其正文被并入相邻二级块；可引用的只有 49 个 H2。这是 §10 铁律 6 的同类坑、更隐蔽。
2. **过滤与双链扩展不一致**：过滤在 `fusion.py:174-179`，扩展在 `:243-295` 无重复过滤 → 按项目过滤得不到纯净视图。
3. **权威加权未校准（现场证据）**：Q1 真正逐条的规范块（`clusters#关键结论`、`notes#结论二`、`decisions#决定`、`source#6.1`）
   **全部未进 top-10**，被 `README#怎么用`（第 2 名）、`index/*`、`clusters#现在在哪` 挤掉。
4. **路由缺口**：Q2 判成 `synthesis`、Q3 判成 `point`（都是「无关键词：按长度兜底」），`decisions/*#决定` 拿不到路由优先权重。
5. **decision 没有放双链的区块**：六区块里无 `## 关联`，样例只能塞进 `## 影响` 末尾（4 篇），语义不符。
6. **根目录 `README.md` / `sop.md` 必须带 frontmatter**，否则 `parse_frontmatter` 直接判「缺少 frontmatter」→ `wb vault check` 必红。
7. **待建的主题簇不能写双链**（会立刻产生死链）。
8. **`source.ref` 语义冲突**：自指本页 vs 指向原件，不能同时成立。
9. **长 source 单篇贡献 54 块**：靠 `source_penalty` 与 `max_chunks_per_note` 兜住；`source` 的块从未进过任何一题 top-10。

### Phase 3 · 库骨架（β 主线）—— 已完成

**选型结论**：**β 项目管线优先**（用户 2026-09-14 拍板）；**H1 锚点策略选 A**＝扩块边界到 `#`（见 R2）。

**落盘**（`_vault`，提交 `f4c3e97`，已推送远端）：

| 产出 | 内容 |
|---|---|
| `conventions.md` | 从零重写（14 节）：β 主线、目录、frontmatter 与 **`source.ref` 语义冻结**、type 与 scope、固定区块（含**主题簇六区块**与 **decision 第 7 区块 `## 关联`**）、命名、双链、决策、索引、检索约定（**块边界＝`#` 与 `##`**）、C-lite、附件、扩展规则、**已知遗留 5 条**、来源范围 |
| `README.md` | 库入口（`type: index`） |
| `index/` | `projects`（2 项目 + 8 主题簇）、`decisions`（台账）、`people`、`timeline`、**`sop`**（《使用 SOP》：上传→审批→五类落点→沉淀→提问+每周维护清单） |
| `projects/` | `hii-affairs.md`、`it-development.md`（**恒定 2 个**；四固定区块 + 关键结论/未决/时间线/主题簇/关联） |
| 主题簇 | HII 3 个（`ip-trademark`/`royalty`/`relationships`）+ IT 5 个（`enrollment`/`portal-cms`/`local-ai`/`mobile-app`/`digitization`），均 `status: draft`（**入库前不进检索**） |
| 骨架 | `community/community-overview.md`、`hr/hr-people.md`（`type: index`） |
| `templates/` | 9 个：project-main / cluster / note / decision / source / meeting-note / work-log / long-form-thought / index |
| `.gitignore` | 忽略 `_signals/`（含飞书会话等机器状态）与超大附件；**明确不忽略 `.summit-workbench/`**（workspace 身份必须随库同步） |

**验证（全部真跑）**

| 门 | 结果 |
|---|---|
| `wb vault check` | ✓ 20 篇全部通过 |
| `wb kb index` → `wb kb status` | ✓ 12 篇 / 78 块，FTS5 可用（8 个 `draft` 簇页按设计不进索引） |
| **新增** `scripts/kb_verify_links.py` | ✓ 20 篇 / 51 条双链 / 0 失效锚点；**并通过变异验证**（注入死链 + 坏锚点 + 坏 `路径#区块`，3 个全部被捕获，exit 1） |
| 双机同步 | ✓ 提交已推送，远端 `main = f4c3e97`，`/api/sync/status = ready`（ahead 0 / behind 0） |

**执行顺序调整（重要）**：**R2（块边界扩到 `#`）要在 Phase 4 入库之前落地**——否则 Phase 4 写入的
`#` 级锚点在 Workbench 检索侧解析不到，锚点自检与验收都会红。R1/R3/R4/R5/R6 仍在 Phase 5。

### R2 · 块边界扩到 `#` 与 `##` —— 已完成（Phase 4 前置）

**改动**：`workflows/ask/chunking.py` 的 `HEADING` 由 `^##\s` 改为 `^#{1,2}\s`；`###` 及更深仍留在父块内；
「首个标题**之前**的正文＝前言块（锚点＝笔记本身）」语义不变。提交 `303ae49`。

**为什么值得改**：原始材料常用 `#` 分大章（HII IP 原件有 20 个 H1），只切 `##` 会让这些章节的正文
并进相邻块、无法定点引用；而 Obsidian 的 `[[文件#标题]]` 本来就不区分标题级别。

**验证（真跑）**

| 门 | 结果 |
|---|---|
| 决定性实测 | 1038 行原件的 **17 个一级章节 + 2 个附录全部成为可定点锚点**（此前 0 个）；样例库块数 131 → 151 |
| 真实库索引 | 全量重建 ✓ 12 篇 / 78 块；`conventions#工作知识库规范`、`projects/hii-affairs#HII 事宜`、`index/sop#工作知识库使用 SOP` 等 H1 锚点已生效 |
| 单测 | 新增「一级标题是块边界」「首个标题前是前言块」两例；`test_kb_index` 的 FTS5 断言按新语义更新（H1 命中锚点：裸路径 → `笔记#一级标题`） |
| `pytest --cov -q` | ✓ **1089 passed / 1 skipped**，覆盖率 **83.55%**（≥80） |
| `ruff check` / `ruff format --check` / `mypy` / `secret_scan` | ✓ 全绿（顺带修掉上一提交漏跑的 3 处 E501） |
| 打包 app 门禁 | ✓ `WB_PACKAGED_APP=… test_packaged_app.py` 1 passed |

> ⚠️ **已安装的 0.4.8 bundle 落后于源码**：R2 只进了源码（CLI/venv 生效），`/Applications` 里的 app
> 仍按旧规则切块。**GUI 侧要看到 `#` 锚点效果，必须在 Phase 5/6 重新打包并重装**（已加入 Phase 5 交付项）。

### Phase 4 · 首批入库 —— 已完成（5 个执行者并行 + 主控收尾）

**并行分工（文件集互不重叠，避免写冲突；共享文件由主控统一回填）**

| 执行者 | 素材 | 产出 | id 号段 |
|---|---|---|---|
| A | HII IP 全景总结（1038 行） | 1 source + 1 分析笔记 + `ip-trademark` 簇回填 + 3 篇决策 | `a1xx` |
| B | HII Royalty 规则与历程（1162 行） | 1 source + 1 分析笔记 + `royalty` 簇回填 + 3 篇决策 | `a2xx` |
| C | 来华手册（869 行）+ 当前来华（568 行） | 2 source + 来华 SOP 子页 + 2 个在办个案页 + `relationships` 簇回填 + 3 篇决策 | `a3xx` |
| D | IT 开发计划与进度（1217 行） | 1 source + 1 分析笔记 + 5 个 IT 簇回填 + 4–6 篇决策 | `a4xx` |
| E | 智能纪要 + 2 份逐字稿 | 1 source + 3 篇会议笔记 + 2 份逐字稿 | `a5xx` |

- **共享契约**：`/tmp/phase4/CONTRACT.md`（铁律、frontmatter、四类页面的写法、自检命令、汇报格式）。
- **主控独占的文件**（执行者不得触碰）：`conventions.md`、`README.md`、`inbox.md`、`templates/`、
  全部 `index/*.md`、`projects/*.md` —— 这些由主控在**执行者全部回收后**统一回填，避免并发写坏。
- **执行者必须真跑**：逐字比对（source ↔ 原件，差异必须为 0）、单文件 schema 校验、
  `scripts/kb_verify_links.py`（只修自己文件的问题）。
- **主控收尾（Phase 4 后半）**：`index/{projects,decisions,people,timeline}.md` 回填、
  两个 `projects/*.md` 的关键结论/未决/时间线/决策记录回填、跨执行者的双链补全、
  幂等检查（`source.ref` + `hash` 去重）、全库锚点与逐字终检、git 提交与推送。
- **关键纪律**：执行者不得使用先验知识补全事实；原文没写的必须写「原文未明确」；
  决策只在原件确有「明确决定」时建页，`## 选项` 不得事后补编。

**结果（全部真跑，vault 提交 `12c2e5e`，已推送远端）**

| 项 | 结果 |
|---|---|
| 素材 | 8 份原件逐字入库（HII 4 + IT 4，含 2 份逐字稿）；**8 份逐行 diff 全部 = 0** |
| 知识层 | 4 篇分析笔记 + 3 篇会议笔记 + 8 个主题簇页（全部 `draft→active`）+ 3 个来华子页（SOP + 2 个在办个案） |
| 决策 | **15 篇**（HII 9 + IT 6），`## 证据` 逐条 `路径#区块`；`## 选项` 只写原件真实候选，无候选则明写「原件未记录候选方案」 |
| 入口页 | `projects/{hii-affairs,it-development}` 回填当前状态 / 下一步 / 阻塞 / 决策记录 / 关键结论 / 未决 / 时间线 |
| 索引层 | `index/{projects,decisions,people,timeline}` 回填；`decisions` 与 `people` 由脚本重生成 |
| `wb vault check` | ✓ 52 篇全部通过 |
| 双链与锚点 | ✓ **269 条双链 + 377 条 `路径#区块` 全部可解析**（`scripts/kb_verify_links.py`） |
| 索引 | ✓ 全量重建：52 篇 / **679 块**，FTS5 可用 |
| id 唯一性 | ✓ 0 重复 |
| 幂等 | ✓ 8 份原件 → 8 个 `source`/`transcript` 页，0 重复 |

**本阶段的两个额外收获（已回写规范）**

1. **`kb_index_people.py` 会抹掉新规范 frontmatter**：它 `render()` 自带一份最小 frontmatter
   （只有 date/type/status/project/updated/title/aliases），写入时把页面已有的
   `id` / `area` / `workstream` / `summary` **整段覆盖掉**。已修为「保留既有 frontmatter、只替换正文」，
   并补回归测试（旧测试一条未改 → 行为兼容）。
2. **幂等键的判定范围被澄清**：派生产物（分析笔记 / 决策 / 簇页 / 个案页）**沿用**同一 `ref`+`hash`
   以保持溯源一致，**不算冲突**；幂等只看 `source` / `meeting-transcript` 页。
   第一次终检把派生笔记也算进去，报了 8 组「冲突」——**是我检查口径写错，不是库里真有问题**，已修正并把该口径写进 conventions §11。

### Phase 1 发现的问题（必须进 Phase 5 的代码修复清单）

**BUG-1 · 0.4.8「首次发布到远端」（G2）在全新 workspace 上必然失败**

- 现象：`POST /api/settings/git/remote/publish` 返回 `remote_publish_rolled_back`，本地回滚到「无 origin」，
  **但远端已被预检那次推送留下 `main`**（预检是真推，见 `remote_publish.py:156`）。
- 根因：`_checked_publish_target()` 构造 `GitRepo(vault_dir, backend_kind=…, workspace_id=…)` **没有传 `username`/凭据回调**；
  随后 `repo.push()`（`remote_publish.py:234`）走 dulwich 后端，而 `dulwich_git.py:560-562` 在 `not self._username` 时
  直接抛 `GitCredentialsUnavailable` → 被 `remote_publish.py:244` 的兜底 `except Exception` 吞成
  `remote_publish_rolled_back`，**真因完全不可见**。
- 影响：`create-new` 新装的用户**永远无法用官方流程绑定远端**；预检却已经把提交推到真远端，留下半成品状态。
- 本次处置：用 app 自己的模块（`store_git_credentials` + `credential_scoped_backend` + `GitRepo.set_upstream` + `save_profile`）
  在空仓库上按官方语义补齐绑定，最终状态与官方流程一致（已用 `/api/sync/status = ready` 验证）。
- **Phase 5 必做**：修 `_checked_publish_target`/`publish_workspace_to_remote` 把本次凭据透传给真 vault 的 backend；
  并把被吞掉的真因暴露为可诊断的错误码；补一条「全新 workspace → publish」的回归测试（含"预检已推送、主推送失败"的变异验证）。

> 注：`_vault/conventions.md` 与 `inbox.md` 是 app 内置的 v2 种子（`wb: onboarding create` 提交），**Phase 3 会从零重写 conventions**；
> `inbox.md` 契约不动。新库旧身份对照：`bf22c8d2-…`（旧）→ `fb9494a4-…`（新）。

### Phase 5 · 检索与决策层改造 —— 进行中（提交 `2ec6ea8`）

**度量口径**：脚本 `/tmp/phase5/measure.py`——用使用者的 4 个验收问题 × 各自期望的**答案块**，
对真实库跑 `retrieve_via_index`（不调模型），统计「期望块是否进入模型实际会看到的候选（plan.limit）」。

| 时点 | 块级命中 |
|---|---|
| 改造前基线 | **4/16 = 25%** |
| R2 修正 + 召回补足 + R1/R3 + 双链两 bug 修复后 | **6–7/16 = 38–44%** |

**修掉的三个真 bug（都有回归测试 + 变异验证）**

1. **双链扩展重复累加**：同一邻居被多个种子各加成一次（实测把正文相关度 0.29 的块顶到 41.05），
   链接信号彻底盖过正文相关度 → 改为「只取最强种子、只应用一次」。
2. **双链扩展覆盖邻居自身分**：旧实现把分整体替换成 `promoted`（只由种子分决定），
   不同邻居被抹成完全相同分数、顺序退化为任意（Q1 排名 2–10 全是 25.03）→ 改为**乘性加成**。
3. **候选池被 FTS 饿死**：BM25 只在 FTS 完全无结果时才用；Q3 在 FTS 层只命中 10 个块。
   → 新增 `_supplement_with_bm25`（两路按各自最高分归一后并集），Q3 候选 10 → **321**。

**已落地**：R1（块级角色加权：结论型 ×2.8 / 支持型 ×0.8 / 引言 ×0.45 / 导航 ×0.4；
类型权威 index 1.0→0.45、project-main 与 decision →0.95）、R3（扩展重复应用 project/workstream 过滤）、
R2 修正（文首 H1＝笔记标题，不切块）、`kb_index_people.py` 保留既有 frontmatter。

**数据驱动的两次回退**：BM25 `b=0.35` 与 CJK 2-gram 补词都**实测有害**（44%→31%），已撤回。
教训记在这里：权重/词表这类改动必须先用真实问题量一遍，不能凭直觉。

**仍未做（Phase 5 剩余）**

| 项 | 状态 |
|---|---|
| R4 路由启发式补强（Q2/Q3 落在「无关键词：按长度兜底」） | ☐ |
| R5 `decision` 第 7 区块 `## 关联` 写进 app 固定区块表（契约级，含模板/测试/快照） | ☐ |
| R6 `source` 索引策略复核（证据层是否值得整篇入索引） | ☐ |
| BUG-1「首次发布到远端」修复 + 回归测试 | ☐ |
| 新增「知识沉淀」审批落点（第 7 个 `RouteTarget`） | ☐ |
| Workbench「决策」页（API + UI + 路由契约快照） | ☐ |
| **重新打包并重装 app**（R2/R1 只在源码生效，GUI 仍是旧切块与旧权重） | ☐ |
| Q1 的深层短板：宽泛问题（「当前达成的商标共识规范是什么」）需要「**问题点名某主题 → 该主题簇页的 `## 关键结论` 优先**」这条路，当前只靠词项匹配还排不上来 | ☐ |
