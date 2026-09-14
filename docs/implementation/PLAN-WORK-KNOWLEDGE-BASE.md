# 计划 · 工作知识库重建 + 第二大脑/决策层改造 + 双机完全重装

> **本文件是「步骤与验证」的唯一真源**；需求真源是 §1 的 4 轮选择题结论。
> 执行者读不到对齐过程的对话，因此本文件自包含。
> 事实基线见 §2（2026-09-14 实测）。目录命名与字段定义以 §3 为准（架构由 §5 Phase 2 的样例门决定）。
> **文档结构**：§0–§5 是计划；§6–§11 是代码清单 / 交付物 / 验收 / 边界 / 铁律 / 冻结项；
> **§12 是唯一的滚动执行进度——看进度只看 §12**。
> ⚠️ 2026-09-14 之前本文件曾同时存在**两份 §6–§11 与两份 §12**（其中一份是中途快照，
> 会让人误以为 Phase 5/6/7 还没做完）。已合并为一份：两份 Phase 5 的**独有内容都保留**，
> 只去掉逐字重复与事实已被更详细版本覆盖的行。

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

### 3.1 三层模型（项目页数固定 5、不新增 type）

> ⚠️ **2026-09-14 更新（契约级）**：项目层由 **2 个扩至 5 个**——新增 `huoman-community`（活满社群）、
> `huoman-logistics`（活满后勤&行政）、`hr`（公司人事）。已同步改 `_vault/conventions.md`
> §1 / §1.1 / §2 / §3 / §13 与 `index/projects.md`、`README.md`。本节下方数字已就地校正；
> §3.2 的 α / β 对比是**当时**的候选架构记录，保留不动。

```
项目层（Workbench 视角 · 恒定 5）   _vault/projects/{hii-affairs,it-development,huoman-community,huoman-logistics,hr}.md   type: project-main
主题簇层（知识视角 · 可扩展 N）      _vault/<line>/clusters/*.md  +  簇下子页                 type: note, project: <5 个之一>
素材/证据层（只增不改）              _vault/<line>/sources/ · meetings/{notes,transcripts}/ · decisions/
执行层（Workbench 契约不动）         daily/ logs/ reviews/ review/ inbox.md inboxes/ artifacts/ insights/
导航层                               index/{projects,people,decisions,timeline,sop}.md
```

- **不新增 `projects/*.md`（当前固定 5 页）**：新增主题 = 建 `<line>/clusters/<slug>.md` → 在项目主页 `## 主题簇` 加一行 → 在 `index/projects.md` 加一行。增减项目页须**成套改**规范（conventions §13.3）。
- 主题簇页与子页固定区块沿用线索主页六区块：`## 现在在哪`、`## 关键结论`、`## 未决问题`、`## 决策记录`、`## 时间线`、`## 关联`（写进新 conventions §4）；2026-09-14 另加「对象页」（人 / 酒店 / 供应商 / 物料）与「事件页」（活动复盘），见 conventions §4.7–§4.8。
- 会议笔记的 `projects:` 值必须是**真实存在的项目 ID**（当前 5 个）。解析走项目注册表（`repositories/project_registry.py` 动态扫描 `projects/*.md`），**代码里没有硬编码项目名单**；ID 不存在时该条会落全局 inbox。

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

### Phase 1 · 完全重装 Studio —— 已完成（表内每一步 ✓）

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

### Phase 2 · 架构样例对照 —— 已完成（已拍板 β：项目管线优先）

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

> ⚠️ **下表是 `f4c3e97` 当时的形态快照**（历史记录，保留不改）。2026-09-14 起已变化：
> 项目页由 **2 个扩至 5 个**、两个骨架页已删、库内模板由 9 个增至 **14 个**、新增顶层 `logistics/`
> 与 `community/events/`、`hr/people/`。当前形态以 `_vault/conventions.md` 为准，变更经过见 §12。

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

### Phase 5 · 检索与决策层改造 —— 已完成（提交 `2ec6ea8` 起）

**度量口径**：脚本 `scripts/kb_measure.py`（2026-09-14 收进仓库；此前只在 `/tmp/phase5/measure.py`，
重启即失、不受版本控制与门禁保护）——用使用者的 4 个验收问题 × 各自期望的**答案块**，
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

**Phase 5 收尾（全部已完成）**

| 项 | 状态 |
|---|---|
| R1 块级角色加权 | ✓ 结论型 ×2.8 / 支持型 ×0.8 / 引言 ×0.45 / 导航 ×0.4；类型权威校准（index 1.0→0.45、project-main 与 decision →0.95） |
| R2 块边界扩到 `#` | ✓ 且修正「文首 H1＝笔记标题不切块」（否则标题块与内容块抢排名） |
| R3 过滤一致性 | ✓ 双链扩展重复应用 project/workstream 过滤 |
| R4 路由启发式补强（Q2/Q3 落在「无关键词：按长度兜底」） | ✓ 提交 `682eb88`：`_FORM_RULES` 问句形态兜底，只在零关键词命中时生效（不与词表抢路） |
| R5 `decision` 第 7 区块 `## 关联` 写进 app 固定区块表（契约级，含模板/测试/快照） | ✓ 提交 `78fa662`：`domain/vault.py` 固定区块表 + 模板 + 契约测试 |
| R6 `source` 索引策略复核（证据层是否值得整篇入索引） | ✓ 提交 `682eb88`：结论是**保留整篇入索引、改用提问侧加权**——问「要原文/原话」时放开证据层降权（`EVIDENCE_REQUEST_RE`），其余时候照旧 ×0.8 降权 |
| BUG-1「首次发布到远端」修复 + 回归测试 | ✓ 提交 `78fa662`：全新 workspace 首推必失败（真实 vault 走 `credential_scoped_backend` 时没带用户名/凭据，`GitCredentialsUnavailable` 被吞成 `remote_publish_rolled_back`）；修好 + 2 例回归 + 变异验证 |
| Q1 的深层短板：宽泛问题需要「问题点名某主题 → 该主题簇页 `## 关键结论` 优先」 | ✓ 提交 `1ba837d`：主题通道（标题/领域/别名/tag 的 2-gram + 拉丁词命中，`topic_step=0.4`、封顶 2.4）。**已知代价**：Q3 的 `it/clusters/enrollment#关键结论` 由「同篇不同块」变成未召回（净 6→7），见下方「仍存在的不足」 |
| 回答撞输出上限时不再把 `LLMSchemaError` 抛给使用者 | ✓ 提交 `425dff3`：带「收窄材料」提示重试一次，仍截断则回报可操作提示（问得更具体 / 提高 `max_output_tokens`） |
| 新增「知识沉淀」审批落点（第 7 个 `RouteTarget`） | ✓ 提交 `c678b08`：目标显式指定（`sink_target`）、只接受 vault 相对路径（拒穿越）、目标页缺失即拒批、带出处与幂等标记；15 例新测试 + 变异验证 |
| Workbench「决策」页（API + UI + 路由契约快照） | ✓ 提交 `6ba2f60`：`GET /api/decisions`（筛选/分面/关系解析）+ 新「决策」tab（状态分组、关系行、空态、输入防抖）；8 例后端单测 + 1 个前端纯渲染测试；已发布 build 38 并在 app 内验证（15 篇决策 / 2 管线 / 8 主题） |
| **重新打包并重装 app** | ✓ 0.4.9 **build 40** 已构建并安装（build 37 → 38 → 39 → 40 逐轮迭代）（`dist/releases/0.4.9/arm64/`，SHA-256 `54b0b912…`）；GUI 实跑验证：R2 的一级章节锚点已可见（0.4.8 里不存在）、Danny 验收题逐条答出、前端产物含新落点「知识沉淀」 |


**检索质量（真实库，4 个验收问题的期望块；含变异验证的回归测试 12 例）**

| 口径 | 改造前 | 改造后 |
|---|---|---|
| 全部期望块（16 个） | 4/16 = 25% | **7/16 = 44%** |
| **答案层**（12 个非 source 块） | 4/12 = 33% | **7/12 = 58%** |
| 证据层（4 个 source 块） | 0/4 | 0/4（**设计如此**：默认不进上下文，问「原文」时才进——见 R6） |

**Q1 在已安装 app 内的真实验收**：app 回答「根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？」时，
第一条事实就是商标共识清单（登记主体 / HIF→HII 编辑规则 / Commissioned Works / 三种年份 / 品牌分开管理…），
逐条带 `路径#区块` 出处。⚠️ 诚实说明：它引的是 `projects/hii-affairs#关键结论`，
而不是我度量里手写的 `hii/clusters/ip-trademark#关键结论`——两者内容等价（项目主页就是那份清单的入口版），
但「期望块」本身不是唯一正解，这一点不应被读成「又失败了一格」。

**仍存在、已知的不足（未解决，留待下一轮）**

1. Q3 的 `it/clusters/enrollment#关键结论` 在加主题通道后由「同篇但块不同」变成「未召回」——那一项是退步（净效果 6→7）。
2. 同篇多结论块互相竞争（分析笔记有 19 个 `结论N` 块），`max_chunks_per_note=3` 下具体哪 3 个进上下文仍偏字面相关度。
3. 度量本身是 16 项二值指标，个别项会随权重微调翻转；**不要**再用它做单一目标的调参依据（本轮已有两次实证有害的回退）。

#### Phase 5 打包重装 · 两条操作经验（下次发布照做）

1. **升版本号后必须刷新 venv 的 distribution 元数据**：`uv pip install -e . --no-deps`。
   `server_version` 来自 `importlib.metadata`（不是 `pyproject`），不刷新的话打包出的 server
   会在诊断里报旧版本号——本次实测：app 是 0.4.9 而 `/api/version.server_version` 报 0.4.8，
   于是又重建了一次（build 37）。
2. **发布脚本拒绝覆盖已存在的发布目录**：同版本重建要先按仓库既有先例把它移开
   （`dist/releases/0.4.9.superseded-b36`），或在脚本报错处换 `RELEASE_OUTPUT_DIR`。
3. **传凭据给构建脚本不要用 `eval "$(heredoc)"`**：本次那样写会让 shell 解析出错，
   把非机密的 `app_id` 打进了日志（`app_secret` 未泄漏）。改为先写 0600 临时 env 文件、
   `source` 后立即删除。

#### Phase 5 顺带发现的观测（未修，记录在案）

- **飞书授权状态缓存不持久**：`~/Library/Application Support/SummitWorkbench/feishu-auth-state.json`
  是**内存态缓存**（进程内 `_items` 整体覆写），app 重启后变空。真实 refresh token 在 Keychain、
  功能不受影响——本次实测：重启后该文件 `items: {}`，但 `POST /api/run/brief` 返回
  「已生成今日简报（健康度 ok）」。**风险**：若界面授权徽标直接读这个文件，重启后会误显示未授权。
  待确认后决定是否改为启动时从 Keychain 重建缓存。
  → **2026-09-14 已结案：不是 bug。** 徽标读的是 vault 内持久的 `_signals/feishu-auth.json`；
  这个 App Support 文件只是 OAuth `state` 暂存表（`_STATE_TTL = 600s`），重启后为空**是正确行为**。
  详见「收口轮 · 起点复核 + 文档漂移 + 条目 3 结案」第 2 节。**不需要改代码。**

### Phase 6 · SOP 与验收 —— 已完成（2026-09-14）

| 项 | 状态 |
|---|---|
| `_vault` SOP 定稿 | ✓ 提交 `d5f224d`（vault 仓库）：知识沉淀落点写法与安全边界、决策页、提问技巧（主题优先 / 要原文给原文 / 块级引用） |
| 4 个真实问题写成可重复运行用例 | ✓ `scripts/kb_acceptance.py` 的 `CASES`：Q1–Q4 真调模型；R1/R2/D1/V1/S1 零 token 只验路由 + 块级锚点 + 追溯链 |
| 真跑并留证据 | ✓ `docs/acceptance/evidence/kb-acceptance-2026-09-14.txt`（真实库，8 题全过）<br>✓ `docs/acceptance/evidence/kb-acceptance-installed-2026-09-14-build40.txt`（**装好的 build 40**，4 题模型口径全过） |
| 本机门禁全绿 | ✓ `pytest --cov` 1127 passed / 83.72%；`ruff check` + `ruff format --check`；`mypy` 359 文件；`secret_scan`；前端 76 源文件 15 组测试；web build + `verify-build.mjs` |
| vault 自检 | ✓ 53 个内容页；272 条 wikilink + 378 条 `路径#区块` 引用全部可解析；`wb vault check` 53/53 |

**Phase 6 新增/修正的判据（都带变异验证）**

1. **验收清单按职责拆两类**：对外验收题（真调模型）跑真实库；机制回归题零 token 跑。
   `tests/unit/test_ask_regression_questions.py` 的合成 vault **只收它真有材料的题**——不为迁就
   一个小 fixture 去伪造 Danny / 活满 / 主题簇页材料（那样测的是 fixture，不是库）。
   并有测试锁住「所有非模型题都必须被合成库覆盖」，防止两组清单悄悄漂移。
2. **关键证据判据支持「等价入口 any-of」**（`Case.must_recall_any`）：Q1 的商标共识清单同时有
   主题簇页与项目主页入口版，答案落在 `projects/hii-affairs#关键结论` 时不该判红。
   ⚠️ 这不是放水：两个入口都没进上下文时仍然红，且报错会列出全部候选（2 例新测试 + 变异验证：
   去掉 any-of 支持，两条测试立刻失败）。
3. **已装 App 验收脚本**新增 `--only <子串>`（重查单题不必再花 4 次模型调用）与「进入上下文的
   来源」逐条列出（失败时能一眼看出是没召回、还是召回了没引用）。

**Phase 6 暴露并修掉的真实缺陷**：回答撞 `max_output_tokens` 时，`LLMSchemaError` 的原文
（`问答返回非 JSON：Unterminated string…`）会直接抛给使用者。现在改为带「收窄材料」提示重试一次，
仍截断则回报可操作提示（问得更具体 / 提高 `max_output_tokens`）。提交 `425dff3`。

### Phase 7 · Air 接入（备用机器）—— **已接入并完成一次真实双向同步**（2026-09-14）

| 项 | 状态 |
|---|---|
| Studio 作为主设备就绪 | ✓ 0.4.9 **build 43** 已装并实跑；`/api/sync/status = ready`，ahead 0 / behind 0；`automation_primary_device_id` = `0617854a-…`（Studio），generation 1 |
| 远端已是最新库 | ✓ SOP 定稿提交已推送（vault 仓库 `d5f224d`） |
| Air 接入路径**已在本机拿真远端真凭据验过** | ✓ 用 workspace 级钥匙串凭据对真实私有远端做暂存克隆：成功、marker 存在、兼容性 `read-write`、workspace id 一致；**另一设备 id → `secondary`**、Studio 自身 → `automation-primary` |
| **Air 侧：完成向导接入** | ✓ 2026-09-14 使用者实机：build 42 上以**绝对路径**通过首启向导（当时 `~用户名` 会让 build 42 崩，见「首启向导实机故障轮」），随后替换为 **build 43** |
| **Air 侧：写 → 提交 → 推送** | ✓ 在 Air 上用「我想记一件事」写入 `air接入冒烟`，自动提交 `875f56e wb: capture [331ca330-…]` 并**推送成功**——**PAT 的写权限据此确认可用**（克隆只需读，推送需要写，这是此前唯一没验过的风险点）。该测试条目已于同日删除（vault `b4d51bc`，删前确认库内 0 处引用其 candidate id） |
| **Studio 侧：拉取** | ✓ `POST /api/sync/run` → fetch→fast-forward 到 `875f56e`，两端 `ready` **0/0**；录入原文保真（`append_global_inbox` 原样写 `[ ] {description}`） |
| Air 侧：作业单 §3 的四条判据 | ✓ **全部通过**（使用者 2026-09-14 实机回报）：① 本机角色 = **辅助设备（secondary）**、主设备 = `0617854a-…`（Studio）；② 真问题答出条目、出处是**块级**并能点开；③「决策」页 **15 篇**、筛选正常；④ 同步 `ready` 0/0（见上） |

> **Phase 7 至此结案**：Air 作为辅助设备接入完成，**读 / 写 / 推送 / 拉取四向都实测通过**。
> 此前那句「Air 侧未验证」已完全失效，不再保留。
> （唯一未单独确认的是 Air 上的 TCC「文稿」权限弹窗——但接口能用即说明已允许，否则读 vault 会一直转圈。）

两个已知、留待下一轮的不足没有变化（见上文「仍存在、已知的不足」），本轮**没有**再动权重：
Q3 的 `it/clusters/enrollment#关键结论` 仍未召回；度量是 16 项二值指标，不适合当单一调参目标。

### 使用者反馈修复 · 项目档案区块不渲染 Markdown —— 已完成（build 41）

**现象（使用者 2026-09-14 打开「HII 事宜」时发现）**：项目详情里的「当前状态 / 下一步 / 阻塞 /
决策记录」是 Markdown，但前端把每行 `esc()` 后直接塞进 `<li>`——`**粗体**`、`[[目标|显示名]]`、
`| 主线 | 状态 |` 表格全部以源码示人，完全不像给人读的档案。

**根因**：仓库里本来就有共享的子集渲染器（`web/src/md.ts` + 后端 `views.md_to_html`，简报/指南在用），
但项目详情**绕过**了它，自己写了一行一条 `<li>`。

**改法**：先把共用渲染器补成真渲染器，再把项目详情接上去——而不是在项目页另打一个补丁。

| 能力 | 之前 | 现在 |
|---|---|---|
| 段落软换行 | 每个物理行一个 `<p>`/`<li>` | 合成一段（中文之间不缝空格） |
| 有序列表 `1. ` | 当成段落 | `<ol>`，缩进续行并进同一项 |
| 任务清单 `- [ ]` | 原样显示 `[ ]` | `☐ / ☑`（带 done 样式） |
| 嵌套列表 | 不支持 | 嵌套进父项 `<li>` 内部 |
| 管道表格 | 当成段落（一行一条竖线） | 真 `<table>`，含表格的区块横跨整行 |
| `[[目标\|显示名]]` | 连 `\|` 一起显示 | 只显示标签，目标进 `title` |
| `*斜体*` / 代码块 | 不支持 / 不支持 | 支持 |
| 时间线摘要里的行内标记 | 原样 | 行内渲染（孤立 `**` 不会被替换，不会吞掉后文） |

**安全模型不变**：先整体 HTML 转义，再只对明确模式做替换——两条路径（前端 `md.ts`、后端
`views.md_to_html`）都有专门的 XSS 断言，包括「引号逃不出 `title` 属性」。

**顺带修好的同类问题**：App 内「指南」页的 37 处编号列表此前也渲染成独立段落，现在是正确的 `<ol>`。

**测试与验证**
- 新增 `web/scripts/test-md-render.mjs`（10 组形状 + XSS，已接入 `test:frontend`）；
  项目纯渲染测试补 Markdown 断言；后端 `md_to_html` 补「档案区块形状」「绝不注入 HTML」两例。
- 测试抓出并修掉两个真 bug：① 表格会把紧跟其后的 `[[目标|显示名]]` 当成表格行吞掉（wikilink 里也有 `|`）；
  ② 中文软换行在行内标记边界（`…HII**、` 接 `**「活满」…`）缝出空格。变异验证：去掉表格行守卫，用例立刻红。
- **真实数据验证**：把 `hii-affairs`、`it-development` 两页的真实 blocks 喂给真渲染函数，
  输出里残留 Markdown 标记 **0**（表格 1、有序列表 5、粗体 21、wikilink 15）。
- 门禁：`pytest --cov` 1129 passed / 83.72%；ruff / mypy / secret_scan / 前端 16 组全绿；
  0.4.9 **build 41** 已构建并安装（`frontend_build = v2026.09.14-288f13d-4d072dbb`）。

### 收口轮 · 起点复核 + 文档漂移 + 条目 3 结案 —— 已完成（2026-09-14）

本轮**没有改任何产品代码**。起因是按铁律复核起点，顺带把三处「文档写的和机器上实际的不一样」敲实。

#### 1. 起点门禁（工作树干净，HEAD = `053a20e`）

| 门 | 结果 |
|---|---|
| `pytest --cov -q` | ✓ **1129 passed / 1 skipped**，覆盖率 **83.72%** |
| `ruff check` / `ruff format --check` | ✓ All checks passed / 472 files already formatted |
| `mypy` | ✓ 359 源文件无问题 |
| `scripts/secret_scan.py` | ✓ passed |
| `npm --prefix web run test:frontend` | ✓ 16 组（76 源文件） |
| `scripts/kb_acceptance.py`（真实库） | ✓ **9 题全部合格**（Q1–Q4 真调模型 + R1/R2/D1/V1/S1 零 token） |
| `scripts/kb_acceptance_installed.py`（已装 build 41） | ✓ **4 题模型口径全部合格** |

**补上一个真证据缺口**：此前只有 build 40 的已装验收证据，build 41 装完**没留**。本轮新增
`docs/acceptance/evidence/kb-acceptance-installed-2026-09-14-build41.txt`
（`build = 41`、`git_revision = 288f13d`、`frontend_build = v2026.09.14-288f13d-4d072dbb`，4 题全合格）。

索引库在复核前后都完好：53 篇 / 685 块 / `PRAGMA integrity_check = ok`。

> 会话提示词里写的「8 题」实为 **9 题**（脚本自报「9 题检索全部合格」）。以脚本为准。

#### 2. 条目 3（飞书授权缓存）**结案：不是 bug，是文件名引起的误读**

原观测担心「界面授权徽标若读 `feishu-auth-state.json`，重启后会误显示未授权」。**读代码 + 读真数据后否证**：

| 文件 | 谁在读 | 语义 |
|---|---|---|
| `_vault/_signals/feishu-auth.json` | `observability/status.py:155` → `read_auth_state(vault_dir)` | **徽标真正读的**。vault 内、持久（`_signals/` 被 vault 的 `.gitignore` 忽略，属机器本地） |
| `~/Library/Application Support/SummitWorkbench/feishu-auth-state.json` | `settings.py:93` 的 `_AuthorizationStates`（经 `_authorization_state_file`，两处构造点 `:320` / `:489`） | 只是 **OAuth CSRF `state` 的暂存表**，`_STATE_TTL = 600s`；重启后为空是**正确**行为 |

- 前端链路：`web/src/features/settings/render.ts:139,146` 读 `/api/state` 的
  `status.feishu_auth.needs_reauthorize`，`badge()` 据此决定「✓ 已授权 / ⚠ 需重新授权」。
- 真实数据：`_signals/feishu-auth.json` 现为 `needs_reauthorize: false`，写入时间 08:13
  **早于**本次 App 启动 08:58 —— 重启后徽标读到的仍是持久值，**没有**误显示未授权。
- App Support 那个文件实测就是 `{"schema_version":1,"items":{}}`，与「10 分钟 TTL 的待授权 state
  过期清空」完全一致。

⇒ **不需要改代码**。也**不该**按原设想去「启动时从 Keychain 重建缓存」：那等于让一次性 OAuth
待授权 `state` 跨进程存活，反而放松了它的语义。原观测按「已澄清、非 bug」关闭。

#### 3. 修掉两处 build 号漂移（会让人拿错包）

| 文件 | 之前 | 现在 |
|---|---|---|
| `docs/implementation/AIR-MACHINE-HANDOFF.md` §0 | build **40** / `v2026.09.14-425dff3-ceb4aa8a` | build **41** / `v2026.09.14-288f13d-4d072dbb`；§2 补 DMG 的 SHA-256，并写明「文件名不含 build 号，认包要核 SHA 或看设置页 build」 |
| `docs/RELEASING.md`「最近一次产物」 | 标题写 build **38**，却配着 **build 37 的 SHA**（`54b0b912…` 属 b37）；「0.4.9 的验证」段还写 `build=37` | build **41**（`f590c932…`）+ 按各轮 `release-metadata.json` 逐个核出的 build→提交对照表 |

后者是**双重错误**（标题 38 / SHA 取 37），正是这轮复核的价值所在。对照表：

| build | 提交 | 内容 |
|---|---|---|
| 36 / 37 | `f202d3e` | 检索修复 + 知识沉淀落点（37 是刷新 distribution 元数据后的重建） |
| 38 | `6ba2f60` | 「决策」页 |
| 39 | `1ba837d` | Q1 主题通道 |
| 40 | `425dff3` | 回答截断重试 + 指南补齐 |
| 41 | `288f13d` | 项目档案区块渲染真 Markdown |

#### 4. 第 4 条（下一批入库）核实结果：**库里没有，素材也没有**

按要求先核了 HR 线以及「工作日志 / 思考」：

| 工作线 | vault 现状 |
|---|---|
| HR | 只有骨架 `hr/hr-people.md`（`type: index`，页内明写「本轮仅骨架」） |
| 活满社群 | 只有骨架 `community/community-overview.md` |
| 工作日志 | **只有模板** `templates/work-log.template.md`，无实体页 |
| 工作思考 | **只有模板** `templates/long-form-thought.template.md`，`insights/` 为空（仅 `.gitkeep`） |

而 `/Users/yifengstudio/Desktop/当前材料` 里**只有 HII（4 份）+ IT（4 份）**，HR / 活满日志 / 思考
**一份素材都没有**。

⇒ 第 4 条当前**卡在素材**，不是卡在工程。素材进目录后才谈得上开 C-lite 三件套。

#### 5. 会话提示词落盘

新增 `docs/implementation/NEXT-SESSION-PROMPT.md`：把会话启动提示词存成仓库文件，并**按本轮实测发现
改写**（原来的「8 题」、条目 3 的「风险」暗示、Air 作业单的 build 40 都已校正），免得下一轮把已证伪的
说法再固化一遍。

#### 6. 已知不足与未验证项（本轮没有变化）

- Q3 的 `it/clusters/enrollment#关键结论` 仍未召回；同篇多结论块竞争仍在；16 项二值指标仍不适合当调参目标。
- 本轮**未**重新构建/安装 App（没改产品代码），所以不涉及 TCC 弹窗与 ⌘R。
- Air 侧 GUI 点击与系统权限弹窗**仍未验证**（必须在 Air 上做）。

### 真缺陷修复轮 · 逐字保留校验 6/6 误报 + sources/read 空值 500 —— 已完成（build 42）

本轮**改了两处产品代码**，都是「先拿实测证据、再动手」，并且都做了变异验证。

#### 1. `kb_verify_quotes.py --materials-root` 在真库上 6/6 误报（判据缺陷）

**现象**：真库实测 6 条问题，**正好是全部 6 个 `source` 页**，都判「正文未逐字包含原件」。
但逐对核查后，**原件的每一行都连续、逐字在库**（✓ 连续命中），多出来的只有 `## 关联` 区块。

**根因**：`_check_verbatim` 用 `body.split("\n---\n\n## 关联", 1)[0]` 剥页尾区块，而 `conventions`
§4.3 规定的 `## 关联` 在真库里的形状是「空行 + `## 关联`」，**没有 `---` 分隔**，于是页尾区块被当成
「原件之后另加的内容」，被 `require_suffix=True` 判死。

**为什么一直没暴露**（两条都要记住）：
1. 单测 fixture（`test_verify_quotes_passes_on_faithful_archive`）的正文里**根本没有 `## 关联`**，
   那条剥离分支从未被真实页面形状覆盖——正是 Phase 6 已记过一次的「测的是 fixture，不是库」。
2. 这个脚本**不在标准门禁里**，`--materials-root` 那一半从来没人跑。

**改法**：判据改成「原件逐字、连续地出现，且其后只放行约定的页尾 `## 关联` 区块」
（新增 `_contains_original` + `_is_allowed_scaffold_tail`），逐位置扫描而非只认第一处命中。

**强度没有被放松（说清楚为什么）**：旧判据在「有 `---` + `## 关联`」的页面上本来就把 `## 关联`
之后的内容切掉了，所以「原件之后、页尾区块之前插内容」两种判据都抓；旧判据**额外**把
「页尾 `## 关联` 区块本身」当违规——那正是 6/6 误报的来源。⇒ 在有效维度上等价。

| 验证项 | 结果 |
|---|---|
| 真库 | 6 条误报 → **0 条**；覆盖 **8 篇原件比对**（6 `source` + 2 `meeting-transcript`，正好对上 Phase 4 的「8 份原件」） |
| 真库副本变异 | 逐字区改一字母 / 同长度换字 / 删一行 / 原件与页尾之间插 `## 编者按` → **四类全红**；只删页尾 `## 关联`（原件未动）→ **仍绿** |
| 判别力 | 用 `git show HEAD:…` 取旧判据喂同一条真形状 fixture → **旧红新绿**（证明新用例不是「怎么都通过」） |
| 新测试 | 真形状合格、原件与页尾之间插区块必红、原件自带 `## 关联` 小节不得误判（3 例） |

#### 2. `GET /api/sources/read` 空值与「只有 `#区块`」返回 500（真缺陷，`§U.5` 遗留）

**现象（在装着的 build 41 上实测）**：空 `source_id=` → 500，`source_id=#关键结论` → **也 500**；
对照 `../secret.md` → 400、正常路径 → 200。

**根因**：`Path("").with_suffix(".md")` 抛 `ValueError: PosixPath('.') has an empty name`，
而这句排在 `not raw_id ... return 400` 守卫**之前**。

`OPEN-VERIFICATION-ITEMS.md` §U.5 写着「留作下一个提交的第一件事」，一直没做；而且它**只记了
空值这一种**——实测「只有 `#区块`」走同一条根因（前端拼「路径#区块」时路径丢了就会命中）。

**改法**：把空引用 / 「只有区块」的判定提到碰 `Path` 之前，沿用同一段 400 语义。

| 输入 | 修复前（build 41） | 修复后（build 42） |
|---|---|---|
| 空 `source_id` | 500 | **400** |
| `source_id=#关键结论` | 500 | **400** |
| 纯空白 | （同根因） | **400** |
| `../secret.md`（对照） | 400 | 400 |
| 正常路径（对照） | 200 | 200 |

**变异验证**：临时移除空值守卫 → 新测试立刻 `FAILED`；还原 → 通过。

#### 3. 构建链的一处流程坑（本轮实测踩到，已写进 `RELEASING.md`）

`release-metadata.json` 的 `git_commit` 与前端 `frontend_build` 都取自**构建那一刻的 HEAD**。
本轮先把修复写完、**没提交**就构建，产物 stamp 指向 `c8869c1`——一个**不含该修复**的提交。
处置：把那份脏 stamp 产物移开（`dist/releases/0.4.9.superseded-b42-dirtystamp/`），
**先提交代码（`70f6753`）再用同一个 build 号重建**，于是 build 42 的 `git_commit = 70f6753`。

正确定式（已写进 `RELEASING.md`）：**先提交代码 → 再构建 → 最后单独提交文档（写 build 号/SHA）**。
另注：构建会重新生成 `src/summit_workbench/webapp/static/` 里的前端产物（内嵌 `git_revision`），
所以每次构建后这些文件都是脏的，应与当轮文档一起提交。

#### 4. 已安装 App

`/Applications/SummitWorkbench.app` = **0.4.9 build 42**（`git_revision=70f6753`、
`frontend_build=v2026.09.14-70f6753-4d072dbb`），DMG SHA-256 `de7cb309…`。
Air 作业单与 `RELEASING.md` 已同步到 build 42。

证据：`docs/acceptance/evidence/kb-round-2026-09-14-verbatim-and-sources-read.txt`。

#### 5. 本轮发现并处理掉的 CHANGELOG 漂移

- ~~**`CHANGELOG.md` 缺整个 `[0.4.9]`**~~ —— **已补齐**（2026-09-14）：补写了
  `## [0.4.9] - 2026-09-14` 条目，覆盖 build 36→42 的全部**应用侧**改动（检索 R1–R6 + 主题通道、
  知识沉淀落点、决策页、块边界扩到 `#`、BUG-1、回答截断重试、档案渲染、本轮两个修复），
  含 build→提交对照与 DMG SHA；并按「诚实标注已知不足」的惯例，首次在 CHANGELOG 里加了
  **「已知不足（未解决，透明记录）」**小节。
- **`## [Unreleased]` 标题错位 + 块内容跨版本**（一并修掉）：该标题排在 `[0.4.5]` 之后，但下面
  377 行其实是**跨版本的流水**。**先用提交祖先关系逐块定性**（`git merge-base --is-ancestor`
  对每块引用的提交求「最早包含它的 tag」），拿到的是：

  | 子块 | 行数 | 真正归属 |
  |---|---|---|
  | 09-13 的 7 块（build 34 / D1–D6 / D7·D8 / 复原收尾 / D11 / build 32 / D9） | 264 | **`[0.4.8]`** |
  | 09-12「前端拆分收尾与第二台机器接入」 | 48 | `[0.4.5]` |
  | 09-11「远端 CI、前端工具链与交付门禁补强」 | 64 | `[0.4.5]` |

  ⚠️ **原本打算并进 `[0.4.7]`，是错的**：这些提交**都不是 `v0.4.7` 的祖先、而是 `v0.4.8` 的祖先**
  ——产物当时仍标着 `0.4.7`（版本号没来得及抬），但实际随 **0.4.8** 发布。
  最终做法：把 09-13 的 7 块搬进 `[0.4.8]` 末尾，09-11/09-12 两块**留在原地**（它们本来就在
  `[0.4.5]` 正下方，位置是对的，只是被那个标题盖住了），删掉 `## [Unreleased]` 标题。
- **同时修掉 4 处因搬动/删除而断掉或本就反向的引用**（一律改成**按名字**指，不再按位置）：
  `CHANGELOG` 里「见本文件顶部 2026-09-13 build 34 块」→「见上文「2026-09-13 · 交付包 build 34」块」；
  `[0.4.5]` 的「（见下）」→「（见上文 `[0.4.6]` 的「修复」）」（`[0.4.6]` 在它**上面**，原文方向写反了）；
  `[0.4.4]` 的「见 Unreleased」→ 指向 `[0.4.5]` 的 09-11 块；
  `docs/implementation/V0-4-4-UX-UI-HANDOFF.md` 的「CHANGELOG Unreleased」→ 同上。
- **完整性核对**：改动前后逐行取**行多重集**对比，只少 1 个空行 + `## [Unreleased]` 标题、
  外加 3 处改写，**没有任何正文丢失**（962 → 960 行，其中 264 行是移动而非改写）。
- 唯一**故意未动**的：`docs/archive/plans/HANDOFF-NEXT-DELIVERY-AND-CLEANUP.md` 里那句
  「`## [Unreleased]` 下按日期分块」——那是**当时下发的指令的存档**，存档记录不该回改。

#### 6. 已知不足（本轮没有变化 / 新增一条边界）

- Q3 的 `it/clusters/enrollment#关键结论` 仍未召回；同篇多结论块竞争仍在；16 项二值指标仍不适合当调参目标。
- **新增边界**：`kb_verify_quotes.py` 的页尾判据只放行「以 `## 关联` 开头的尾巴」，
  **在 `## 关联` 之后**再追加内容不会被它抓到。这与旧判据在「有 `---` + `## 关联`」页面上的行为
  一致，属**有意不改**的边界（不是这轮放松出来的）。
- Air 侧 GUI 点击与系统权限弹窗**仍未验证**（必须在 Air 上做）。

### 度量工具轮 · 把检索度量收进仓库并加上分档 / 排名 —— 已完成（2026-09-14）

**为什么先做这个**：铁律是「涉及检索权重/词表的改动必须先用真实问题量一遍再决定」，但这条铁律
此前依赖 `/tmp/phase5/measure.py`——**重启即失、不受版本控制、不受门禁保护**，等于无法执行；
而「检索不足」那条自己写明的前置正是「先建更可信的度量」。所以它是那条路的**第 0 步**。

**新增 `scripts/kb_measure.py`**（三层口径，前两层零 token）：

| 层 | 内容 | 与历史的关系 |
|---|---|---|
| 1 二值命中 | 期望块是否进 `limit` 候选；**判据与打印格式都不许改** | 与 Phase 5 的历史数字同口径 |
| 2 分档 | `命中 #k` / `同篇但块不同` / `未召回` + **期望锚点自检** | 本轮新增 |
| 3 召回 → 引用 | `--with-model`：模型有没有**真的引用**期望块 | 本轮新增，花 token |

- **权重实验不用改代码**：`--set key=value` 直接覆盖 `Weights` 字段（未知字段 / 坏数值一律报错，
  **不静默忽略**——拼错的字段名被忽略会让实验「看起来量过了」其实没生效）。
- **退出码有意义**：期望锚点解析不了 → exit 1（**度量坏了比检索坏了更危险**）。

**移植忠实性**：与 `/tmp/phase5/measure.py` 逐字比对，**4 题的题面与 16 个期望锚点全部一致**；
真库实测二值 **7/16 = 44%**，落在 PLAN 记录的 6–7/16 = 38–44% 区间内。

**新基线（真库，2026-09-14）**：二值 `7/16 = 44%`（答案层 7/12、证据层 0/4）｜
分档 **命中 7 / 同篇但块不同 3 / 未召回 6**｜期望锚点自检 **16/16 可解析**｜
命中排名 `#1、#1、#1、#2、#2、#11、#13`（均值 4.4）。

**第一次量出的三个真结论**（全部零 token）：

| 配置 | 二值 | 分档（命中/同篇/未召回） | 命中排名（均值） |
|---|---|---|---|
| 基线 | 7/16 = 44% | 7 / 3 / 6 | #1,#1,#1,#2,#2,#11,#13（4.4） |
| `conclusion_boost=1.0` | 7/16 = 44% | 7 / 3 / 6 | …#11、**#16**（4.9） |
| `conclusion_boost=0.5` | **4/16 = 25%** | 4 / 4 / 8 | #1,#1,#1,#2（1.2） |
| `topic_step=0` | **6/16 = 38%** | 6 / 4 / 6 | …**#15** |
| `topic_step=1.2` | 7/16 = 44% | **7 / 4 / 5** | …**#12、#12**（4.4） |

1. **二值确实看不见东西**：`conclusion_boost=1.0` 档位一项不变，只有排名动（#13 → #16）。
   ⇒ 排名那一行不是装饰；这也正面印证了「16 项二值指标不适合当单一调参目标」。
2. **R1（结论型 ×2.8）是承重的**：把它降到 0.5 就**塌回 25%**（= Phase 5 之前的基线）。
3. **`topic_step=1.2` 是一个可查的改进线索**：它把一项「未召回」变成「同篇但块不同」，
   而二值不变（7/16）、排名不变（均值 4.4）——即**没有代价**。这与下面「Q3 的
   `it/clusters/enrollment#关键结论` 未召回」很可能相关。
   ⚠️ 但**本轮不据此改默认值**：4 题 16 项上的单点变化证据强度不够，
   且 `Weights.topic_step` 的注释写明「不能压过正文相关度」。
   留作下一轮的实验对象，动手前先用本脚本扫一遍并记录配置。

**测试**：`tests/unit/test_kb_measure.py` 22 例，锁住两条最关键的判据——
① 「同篇但块不同」**不算命中**（算了会让 44% 虚高到 10/16）；
② `CASES` 形状（4×4 = 16、证据层 4 / 答案层 12）不变，否则历史数字不可比。
变异验证：把「同篇不同块」放松为命中 → **恰好那一条测试红**，还原即绿。

### 首启向导实机故障轮 · `~用户名` 崩溃 + 真实错误被 WebKit 那句英文盖掉 —— 已完成（build 43）

**这是本项目第一次「使用者在另一台机器上把首启走挂」**，也第一次靠**实机日志**而不是本地复现定位。

#### 现象与证据链

使用者在 Air 上填完「从另一台 Mac 克隆」四项（含**新建的细粒度 PAT**）后，界面只显示一句英文：

> The string did not match the expected pattern.

而 `~/Library/Logs/summitworkbench-server.log` 里的真实原因是：

```
File "summit_workbench/webapp/routers/onboarding.py", line 243, in restricted_remote_stage
File "pathlib.py", line 1406, in expanduser
RuntimeError: Could not determine home directory.
```

#### 根因（三层叠加，缺一层都不会这么难查）

1. **路径解析**：使用者在「目标文件夹」里填的是 **`~用户名`** 形式，而该用户在这台机器上不存在。
   `posixpath.expanduser` 对未知用户**返回原串**，`pathlib` 于是抛 `RuntimeError`。
   实测确认：`Path("~gandalf/x").expanduser()` 抛的正是这条文案，而 `Path.home()` 一切正常
   ——这解释了为什么服务能正常启动、**只有这一步**炸。
2. **受限 app 没有兜底**：首启向导跑的是**受限 app**，它当时**只装 422 处理器** →
   异常一路漏到 uvicorn。
3. **前端盖错误**：向导的 `api()` **无条件 `response.json()`** → 非 JSON 响应 →
   WebKit 抛 `SyntaxError: The string did not match the expected pattern.` → 使用者只看到这一句。

> ⚠️ **诚实记录一次被实测否证的推断**：中途我据「冻结包 `_internal` 里没有 `pwd`」推断
> 「进程没有 HOME 且 CPython 的 passwd 兜底不可用」，并据此提了「打包 `pwd`」的修法。
> 用冻结包实测**否证**了它：`env -u HOME` 下冻结服务仍能启动、也仍能解析出 workspace，
> 说明 `pwd` 是可用的。那条修法**已撤回**，没有写进代码。真正的原因是上面第 1 条的 `~用户名`。

#### 改法（四层一起修，缺一层下次还会踩）

| 层 | 改动 |
|---|---|
| 路径解析 | 新增 `config/paths.py::resolve_user_path()` + `UserPathError`：`~` / `~/…` 按「显式 home > `Path.home()` > `$HOME` > passwd」依次解析；`~用户名` 解析不了就抛**可显示的文案**（点名那个用户 + 教他改用绝对路径）。**绝不**退回「就当它是当前用户」——那会把库建到错的位置 |
| 路由 | `webapp/routers/onboarding.py` 的 **9 处** `Path(...).expanduser()` 全部改用它（`create` / `connect` / `upgrade` / `remote/stage` / `remote/confirm` 都会用到） |
| 异常边界 | `install_validation_handler` 同时装 `UserPathError` → **400**；新增 `install_unexpected_handler()` 并**在受限 app 也安装**（此前完整 app 有兜底、首启向导没有——最需要看懂错误的那一次恰好最看不懂） |
| 前端 | `api()` 先读 `response.text()` 再 `JSON.parse`，非 JSON 时报「HTTP 状态码 + 片段（或空响应）」；`pat` 补 `.trim()`（其它三个字段本来就 trim 了） |
| 凭据 | 新增 `_pat_secret()`：PAT 去空白，**全空白视为「没给」**（从 GitHub 复制 token 常带尾随换行，而它随后要当 git 密码用） |

#### 验证（含真机产物验证）

- **新增 11 条测试**：`test_config_paths.py` 6 条 + `test_webapi_onboarding.py` 5 条。
  其中 `~用户名` 那条是**测试先红**抓出我自己的疏漏：第一版仍在检查前就调了 `expanduser()`。
- **变异验证**：① 去掉 `~用户名` 的 RuntimeError 守卫 → 对应用例红；
  ② 不注册 `UserPathError` → 400 的处理器 → API 用例红（退化成 500）。还原后全绿。
- **真实产物验证**（用隔离 `HOME` 让**已安装的 build 43** 进首启模式，直接打那条接口）：

  | 输入 | 结果 |
  |---|---|
  | `~nosuchuser/Documents/Work/_vault` | **HTTP 400 `invalid_path`**：「解析不了「~nosuchuser」：这台机器上没有这个用户。…请写成 ~/… 或直接用绝对路径」 |
  | `~/Documents/Work/_vault` | **HTTP 409 `target_parent_missing`** —— 说明 `~` **已解析成功**、走到了克隆预检（我的隔离 HOME 里父目录不存在） |

- 全量门禁：pytest --cov **1166 passed / 1 skipped / 83.80%**；ruff check + format（475 文件）；
  mypy 360 文件；secret_scan；前端 16 组。

#### 给 Air 的三条操作要点（已写进作业单）

1. **先建 `~/Documents/Work`（只建父目录），不要建 `_vault`**——`stage_remote_clone` 要求
   `target.parent.is_dir()`，否则报 `target_parent_missing`（本轮实测）。
2. **`~/…` 与绝对路径现在都可以**；build 42 上填 `~用户名` 会崩，build 43 起会给出可读的 400。
3. 已在 Studio 上复现不了的流程（Studio 已完成接入 → 只注册 5 条 onboarding 路由），
   可以用**隔离 HOME** 让打包产物进首启模式来验：`HOME=<临时目录>` + `WB_RUNTIME_RECORD=<临时文件>`。

#### 教训（候选铁律）

1. **使用者输入路径的解析点必须只有一个**，且**不允许把库抛的原始异常漏给界面**。
2. **受限 app 与完整 app 的异常边界不该不一致**。
3. **前端不许无条件 `.json()`**：非 JSON 响应会把任何错误变成一句浏览器方言。
4. **分享到另一台机器时，首启流程必须真机跑一遍**——本轮正是靠使用者实机才暴露。

---

### 种子基线与三线升级轮 · 骨架 → 项目管线 + 素材留存规范 + 既有内容修缮 —— 已完成（2026-09-14）

作业单：`NEXT-SESSION-PROMPT-SEED-INGESTION.md`。使用者把本轮的**最高价值产出**定在
「**素材该怎么留**」的规范与模板（种子基线），而不是「入库一次」；并明确三条新线
（活满社群 / 活满后勤&行政 / HR）的素材**尚未准备**，要求先与他探讨「该准备什么素材」。
⇒ 本轮**不产 source/notes**（无素材），交付结构 + 规范 + 模板 + 既有内容修缮。

#### 起点复核（全绿）

pytest --cov **1166 passed / 1 skipped / 83.80%**；ruff 全过、mypy（360 文件）、secret_scan、
前端 16 组；`wb vault check` 53 篇；`kb_verify_links` 272 双链 / 378 块级引用；`kb_verify_quotes` 30 条 0 问题；
`kb_measure --no-rebuild` 二值 7/16、分档 7/3/6、排名均值 4.4、锚点 16/16（与文档一致）。
已装 App `0.4.9 build 43`（`frontend_build v2026.09.14-73d495a`）、`/api/sync/status = ready 0/0`。
两项调模型的验收按规范未重跑（上一提交 `42ea6d7` 为纯文档、工作树未变）。

#### 交付 1 · 契约级升级：`projects/` 由 2 个扩至 5 个

| 产出 | 内容 |
|---|---|
| 新项目页 | `projects/huoman-community.md`、`projects/huoman-logistics.md`、`projects/hr.md`（`project-main`，四固定区块 + 关键结论/未决/时间线/主题簇/关联，各 10 块） |
| 新目录 | 顶层 `logistics/{vendors,procurement,clusters,notes,sources}`；`community/{events,notes}`；`hr/people`；补齐 `logs/`、`reviews/`、`review/` |
| 骨架收口 | 删 `community/community-overview.md`、`hr/hr-people.md`（内容已迁入项目页），**不留双入口** |
| 规范 | `conventions.md`：§1 目录树、§1.1 归属判定（+6 行）、§2 workstream 加 `logistics`、§3 type 表、**新增 §4.7 对象页 / §4.8 事件页**、§5 命名与模板命名、§8 机器页豁免、§13 扩展规则重写为「固定 5 页 + 成套改清单」、§14 |
| 导航 | `index/projects.md` 重写（5 项目 + 3 个待建簇区）、`README.md`、`index/timeline.md`、`hii-affairs.md` / `it-development.md` 脚注、`index/people.md` 重生成 |
| 仓库文档 | PLAN §3.1 就地校正 + §12 本节；`kb-spine-sample-comparison.md` §6 表述；**新增 `SEED-MATERIAL-SPEC.md`** |

**代码依赖核查**：全库 grep 确认 `src/` **没有任何硬编码项目名单**（项目解析走
`repositories/project_registry.py` 动态扫描 `projects/*.md`），所以「恒定 2 个」只是文档/库层契约，
无代码或测试依赖、无需重建 App。PLAN §3.1 旧文「会议笔记 `projects:` 必须只出现 hii-affairs / it-development」
是**文档漂移**（当时表述），已改正。

#### 交付 2 · 种子基线（最高价值）

- **`docs/implementation/SEED-MATERIAL-SPEC.md`**：唯一判据（能否被切块/寻址/溯源/不被加工污染）、
  最小形态 7 条、反面清单、三条线粒度表、**四个场景的「留什么文件/叫什么名/至少哪几段」**、
  30 秒自检 5 问、入库流程、格式处置（微信/录音标注为未验证）、迭代规则、已知不足。
- **库内模板 9 → 14**：新增 `hr-person` / `event-retro` / `vendor` / `procurement` / `conversation-note`，
  全部通过 §3 词表与 scope 手判、含对应 §4.7/§4.8 固定区块。
- 刻意**不动**仓库 `templates/vault/` 种子（使用者选「库内模板 + 仓库规范文档」，不扩新工作台产物）；
  两者用途不同已在 conventions §13 遗留 6 登记，避免下轮再当漂移重报。

#### 交付 3 · 既有 HII / IT 内容修缮（审计驱动）

用两个只读审计（HII 侧 35 篇 / 库结构侧 25 对象）定位，再机械修复：

- **溯源**：给 6 篇派生物补 `source`（ip-trademark / ip-analysis / 3 篇 decision 用 IP 全景总结；
  royalty 簇页用 Royalty 规则 V2）。`relationships` 簇页对应多份原件 → 单个 source 语义不成立，
  已在 conventions §2.1 明确「多源可省略 source，改为在 `## 关联` 列出来源」。
- **决策页字段顺序**：6 篇把 `decision_status`/`decided_on` 插在 `status` 与 `created` 之间，
  与 §2/§7 冲突；**根因是 `templates/decision.template.md` 本身写错**——已同时修模板 + 6 篇，15 篇键序统一。
- **术语**：原件 146 处全为 Royalty、0 处 Loyalty，而库内 16 处误写「Loyalty」→ 统一为 **Royalty**
  （历史叫法留 `aliases`），涉及 9 个文件。
- **导航**：`index/timeline.md` 12 条缺双链 → 补为 18 条（每条目标页先核实存在）；README 两处反引号改双链。
- **交叉引用**：`index/sop.md`「§4 的入库管线」→ §11、「落点第 7 个」→ 第 6 个。
- **事实性数字**：IT source 页 `## 要点` 声称 38 一级 / 24 二级章节，实测 **35 / 23**（原件自身 H1 不计、
  页面自身 `## 关联` 不计），并合并重复 bullet；受影响的行号偏移说明已标注「随要点长度变化」。
- **§4.4 合规**：6 处 `## 证据` 的逐字引用只写 `#区块` 省略路径 → 补全 `路径#区块`。
- **契约空洞**：补齐 §10 定义的唯一审批入口 `review/meetings.md`（`REVIEW_PATH` 已核实）与 `logs/`、`reviews/`。

#### 验证（全部真跑）

| 门 | 结果 |
|---|---|
| `wb vault check` | ✓ **55 篇**全部通过（53 − 2 骨架 + 3 项目页 + 1 审批页） |
| `kb_verify_links` | ✓ 55 篇 / **312 双链** / **388 块级引用** 全可解析（+6 来自 §4.4 补路径） |
| `kb_verify_quotes --materials-root` | ✓ 30 条比对 0 问题（**逐字原件未被改动**：`it/sources/…roadmap-progress.md` 的 `## 原文` 区与 HEAD 逐段 `diff -q` 一致） |
| `kb_index_people.py --check` | ✓ 与 frontmatter 一致（14 人 / 3 组织）；顺带修好旧的**索引过期**（Kate Mayer、曹木子 缺失） |
| `kb_measure`（重建索引） | 二值 **7/16=44%**（不变）、分档 **7/3/6**（不变）、锚点 16/16；**排名均值 4.4 → 4.9** |
| pytest / ruff / mypy / secret / 前端 | ✓ 1166 passed / 83.80%；ruff 全过；360 文件；passed；16 组 |

#### 度量位移的原因（已定位，不调参）

新增 3 个项目页各含 `## 下一步`，连同 `it-development` 共 4 个 `## 下一步` 占住 Q2 的 #8–#11，
把 `hii/clusters/relationships#关键结论` 从 #13 挤到 **#16**；该问句字面含「下一步谁做什么」，
与块标题「下一步」强匹配。**二值/分档不变**说明它仍在返回窗口（limit=16）内，但已贴边缘——
再加一个项目页可能掉出。附带改善：Q4 现能召回 `projects/huoman-community#未决问题`(#4) 等新入口页。
按铁律**不据薄证据调权重**；完整前后输出已存
`docs/acceptance/evidence/kb-measure-2026-09-14-post-seed-baseline.txt`。

#### 未做 / 遗留（诚实标注）

1. **首批素材未入库**：使用者要先「探讨该准备什么素材」再去准备；三线 source/notes 一律未产。
   因此**三条线各自的「真实问题」度量也未做**——无素材可量（只写了零 token 的路由试算作为管道自检）。
2. `SEED-MATERIAL-SPEC.md` 是**设计稿**，尚未被真实素材检验；微信导出 / 录音转写两条路径本轮无样本。
3. `index/people.md` 的裸双链与「别名=文件名」形态由脚本生成，已在 §8 登记为机器页豁免，未改脚本。
4. 审计给出的「建议不动」项：`daily/`、`inbox.md` 的最小 frontmatter（已豁免）、§13 既有 R1/R2/R3/R5/R6 遗留。

#### 使用者对「该准备什么素材」的四条答复（2026-09-14，同日落地）

| # | 答复 | 落地 |
|---|---|---|
| 1 | **不会有微信聊天记录和录音，将来也不接入** | `SEED-MATERIAL-SPEC.md` §8 删除这两行（**不是「未验证」而是「不适用」**），§10 相应结案；`conventions.md` §14 增「明确不做（含将来）」 |
| 2 | 认可「每条线先交 1 份」 | 建好素材入口目录：`~/Desktop/当前材料/{活满社群,活满后勤行政,HR}/`，每个目录放一份 `README-放这里.md`（写明命名与段落要求）；见 spec §8.1 |
| 3 | **后勤和社群不跨越，是两个独立部门、职能完全不一样** | **落成决策** `decisions/20260914-community-logistics-separate-departments.md`（否决了 Agent 原提的「社群管决策 / 后勤管执行」跨线分工）；`conventions.md` §1.1 增规则；两条线项目页关闭「是否跨社群」未决项并记入 `## 决策记录`；`index/decisions.md` 与 `index/timeline.md` 同步 |
| 4 | 认可「日志挂到对应线的 `logs/`，不单独成线」 | 新增 `logistics/logs/`、`hr/logs/`（`community/logs/` 原已预留）；`conventions.md` §1 目录树 + §3 `work-log` 行改为「各线自己的 `logs/`」；三条线项目页 `## 下一步` 各加一行 |

> ⚠️ 第 3 条是**口头确认、无书面原件**，决策页已如实标注「不得当作逐字证据引用」，
> 并写清真实出现过的两个选项（跨线分工 vs 独立两条线），未事后补编。
> 门禁（56 篇）：`wb vault check` ✓、`kb_verify_links` ✓ 321 双链 / 393 块级引用、`kb_index_people --check` ✓
> （新增决策页改变 HIC 计数 → 已重生成索引）。

#### 首批种子入库 · 三线各 1 批 —— 已完成（2026-09-14）

使用者把 5 份素材放在 `~/Desktop/3份素材/`（**未**遵循上一轮建的线级目录，属可接受的一次性交付），
并按「每条线先 1 份」提交。**这是入库规范 v1 的第一次实战检验。**

| 线 | 产出 | 说明 |
|---|---|---|
| 活满社群 | `community/clusters/activity-playbook.md`（方法页）<br>`community/sources/20260607-huoman-community-gathering-plan.md`（原件）<br>`community/events/20260607-huoman-community-gathering.md`（事件页） | 原件 408 行 / 15KB。**同一文件内含三个版本**（上午场定稿 / 下午场过程稿 / `New Plan 0526`）——结论层只用最终版，过程稿仅留原件 |
| 活满后勤&行政 | `logistics/vendors/hangzhou-1977-hotel.md`（对象页）<br>`logistics/sources/20260914-hangzhou-1977-hotel-progress.md`（原件） | 原件 748 字节、**5 条编号进展、无 `##` 小标题** → 整份退化为**单区块**；可寻址结论改由对象页承载 |
| 公司人事 | `hr/people/liu-yulan.md`（按人页）<br>`hr/sources/20260914-luo-yifeng-liu-yulan-translation-alignment.md`（原稿）<br>`hr/notes/20260914-translation-proofreading-alignment.md`（分析） | 原稿 411 行、`说话人 + MM:SS` 格式。**使用者的人工纪要作为分析笔记底稿保留**，Agent 在其上补结论/未决/关联 |

**使用者现场答复的 6 个选择题**（本轮新增的边界判断，均已落地）：

1. 后勤空文件 → 使用者**当场补了内容**（0 字节 → 748 字节），不是跳过。
2. 社群《精华总结》→ 做成 `community/clusters/activity-playbook.md` **方法页**（不建 source，因其为二手提炼件）；
   两场 2025 活动原件由使用者后续补齐（放 `~/Desktop/当前材料/活满社群/`）。
3. 6/7 方案 → **source 逐字 + events 页**，过程稿只留 source。
4. HR 原稿 → `source`；人工纪要 → 分析笔记底稿。
5. **主题归属 → 只归 HR，不建跨线链**（尽管主题是「翻译校对 / Overleaf 写回」，非传统人事）。
   已在该材料与 `projects/hr.md` 里如实标注分类理由。
6. 模板 → 新增 `event-plan.template.md`（服务「多写活动方案」）+ `conversation-minutes.template.md`（贴合其纪要三段式）。

**规范检验结论（重要）**：§3 的粒度与 §3.1 的场景表**直接成立、未需修正**；
暴露的三条**采集习惯**问题已写进 `SEED-MATERIAL-SPEC.md` §10（原件缺 `##` 小标题、
定稿与过程稿混在一份文件、原稿/纪要并行）。

**验证**：`wb vault check` **64 篇**全过；`kb_verify_links` 371 双链 / 412 块级引用 0 失效；
`kb_verify_quotes` 对**两个素材根**（`当前材料` 与 `3份素材`）各 33 条、**均 0 问题**；
`kb_index_people` 21 人 / 4 组织且与 frontmatter 一致；三份原件在生成时用脚本做**字符级比对**
（其中 1977 酒店原件末尾缺换行，为唯一差异，已在页内如实标注）。

**⚠️ 检索回退（如实记录，未掩盖）**：重建索引后 `kb_measure` 由 **7/16=44% 降到 6/16=38%**，
分档由 7/3/6 变 **6/4/6**——Q2 的 `hii/clusters/relationships#关键结论` 掉出 limit=16 窗口。
**逐题 diff 已定位到具体块**：新增的 `projects/huoman-logistics#阻塞` 冲到 **#3**，因为我在该块写了
「2026-11 签约前必须**收口**」而 Q2 问句正是「还差哪些必须**收口**」——**跨线假阳性**；
另加新决策的 `## 选项`(#10) 与四个项目页的 `## 下一步`(#8/#9/#11/#12/#13) 占据席位。
**未改动任何权重、未放宽判据**；也**没有**为把数字改回 7 而改写自己新页面的措辞
（「收口」是使用者 HII 材料里的既有高频词，为分数改词＝对着测试调参）。
⚠️ 注意排名均值由 4.9 变 2.8 是**假象**（命中项从 7 降到 6，分母变小）——看回退要看二值/分档。
证据：`docs/acceptance/evidence/kb-measure-2026-09-14-post-first-batch.txt`。
这条与本轮上一条「Q2 锚点已贴在窗口边缘 #16」是同一根因，现已被内容增长触发。
**未跑**：三条新线各自的「真实问题」度量——留待内容再厚一些。

#### 追加入库 · 2025 两场社群活动原件 —— 已完成（2026-09-14）

使用者补齐 `/Users/yifengstudio/Desktop/3份素材/2025年社群活动/` 的 3 份文件（杭州聚会其实是 2 份：

详细流程 + Kick Off 总纲）。至此**社群三场活动的原件与事件页全部在库**。

| 产出 | 说明 |
|---|---|
| `community/sources/20250418-hangzhou-gathering-kickoff.md` | Kick Off 总纲（背景 / 三大目标 / 分工 / pre-homework / 附录模板 / 两次筹备例会），8 个 `#` + 9 个 `##` → 块结构良好 |
| `community/sources/20250418-19-hangzhou-gathering-flow.md` | 逐环节 Run of Show（14:00 前搭建 → 20:30 社群公约）。⚠️ 原件小节是 `###`/`####`，**分块器只认 `#`/`##`** → 该页近似单块，可寻址流程放到事件页 |
| `community/sources/20251216-year-end-gathering-overview.md` | 年终聚会筹备总文档（名单 / 两份礼物名单 / 时间轴 / 三个分享模板）。改名加 `-overview` 后缀以避开与事件页同名导致的 wikilink 歧义 |
| `community/events/20250418-hangzhou-gathering.md` | 事件页：三大目标、逐环节时间表、**10 步可复用流程**、可复用文本资产 |
| `community/events/20251216-year-end-gathering.md` | 事件页：两天时间轴、三个分享 / 演绎模板、6 步可复用流程 |

**方法论页因此实质升级**：`activity-playbook` 的 **10 个环节里有 8 个**现在能标出「**验证于哪一场**」
（此前只能含糊说「2025 年两场」）；同时把环节库与设计理念从 `###` **提升为独立 `##` 块**，
使 `activity-playbook#环节库｜A 破冰与连接` 这类定点引用真正可检索。

**顺手修掉的一处自我违约**：`hr/notes/20260914-translation-proofreading-alignment.md` 原来把
`结论一…六` 写成 `###`——而 conventions §11 要求分析笔记「结论按 `##` 分节、每个 `##` 是一个可引用结论」。
已提升为 `##` 块（否则那些引用虽然能过 `kb_verify_links`，检索侧却定位不到块）。

**验证**：`wb vault check` **69 篇**全过；`kb_verify_links` 464 双链 / 426 块级引用 0 失效
（其中 1 处 `#3 2 备注详解` 锚点报红——**门禁真抓到了**：该标题是 `###` 且含转义点号，
已改为引用真正的父块 `#活动流程`）；`kb_verify_quotes` **36 条 0 问题**；
`kb_index_people` 36 人 / 4 组织一致。

**度量**：追加后仍为 **6/16、分档 6/4/6**——**与首批入库后持平，未再挤出任何既有命中**。
⇒ 说明回退是**一次性、可归因**的（首批那几个新块），不是随规模持续恶化的趋势；
这条**支持「先不调权重」**的判断。证据已追加进 `kb-measure-2026-09-14-post-first-batch.txt`。

**仍未做**：三场活动的**一手复盘**（现在最缺的就是它——方法论里的「验证于」只能证明用过，不能证明有效）。

#### 2026-06-07 一手复盘入库 —— 已完成（2026-09-14）

使用者以对话形式给出 6/7 活动复盘（**260 字**）。按规范「口头结论 → 自写记录当原件」的做法，
先落成素材文件 `~/Desktop/3份素材/2026年6月活满社群活动/2026年6月7日社群活动复盘.md`
（sha256 前 16 位 `95645fe778b7eafa`），再建 source 页（`kind: manual`，
**页内明确标注「使用者本人事后判断，非活动当时的逐字记录」**）。

- **方法论页实质升级**：`activity-playbook` 新增 `## 复盘教训（跨场次累积）` 块（**6 条教训**），
  并把设计理念第 4 条（主人翁意识）按复盘修正为「**在明确边界与执行指南之下**赋予主人翁意识」；
  环节库 A/B 的相关条目加注「一手复盘 ✅」。⇒ 该页首次拥有「有效 / 需调整」级别的依据。
- **事件页补齐**：6/7 事件页 `## 复盘：有效与无效` 由「待补」改为实写；
  `## 可复用流程` 由 7 步扩到 **10 步**（新增：场地要求必须写「有空调」、午餐固定 + 外卖、
  下午场压缩游戏把时间给共创、学员主导须配套执行指南）。
- **规范升级（有实测依据）**：`SEED-MATERIAL-SPEC.md` §3.1 场景表**新增「活动办完之后的复盘」一行并标为价值最高**，
  写明实测结论——**260 字的复盘把方法论从「用过」升级为「有效 / 需调整」；行程方案再详细也回答不了「下次该怎么改」**。
  这是本轮最有价值的一条规范修订，因为它把「该留什么」的优先级排出来了。
- **多源处理**：6/7 事件页现有两份原件（方案 + 复盘），故按 conventions §2.1 多源例外**去掉 `source` 字段**，
  改为在 `## 关联` 逐条链到两个来源页。

**验证**：`wb vault check` **70 篇**；`kb_verify_links` 466 双链 / 426 块级引用 0 失效；
复盘原件页逐字一致（260 字符，含末尾换行）。

**仍未做**：2025 两场活动的一手复盘；「学员主导下午场下次是否继续」需使用者明确（复盘给的是条件句）。


#### 素材入口指南轮 · 把「我该传什么」写成可执行规范 —— 已完成（2026-09-14）

背景：使用者强调「**当前归档的所有工作内容都不是完美版本**」，他要的不是回头修旧料，
而是**以后每次进来的素材都合格、并且允许不完美地迭代生长**。故本轮产出的是**前瞻性指南**。

**使用者六项对齐（选择题）**：① 主路径＝**他自己在 Workbench 里操作**（Agent 主导被否）；
② 会议材料＝**有逐字稿（带说话人 + 时间戳）**；③ 手记＝**直接写在 vault 里**；
④ 不完美素材＝**先入、标「待补」、之后迭代**；⑤ 节奏＝**复盘当天/次日、其他攒批**；
⑥ 指南落点＝**库内 `index/sop.md`**，外加**一份交互更友好的 HTML 放桌面**。

**⚠️ 本轮发现并修掉一个此前一直存在的实质缺陷**：`_vault/templates/` 的 **16 个模板全部「插入不安全」**——
frontmatter 里的 `{{…}}` 未加引号，在 YAML 层就是非法映射，**照指南操作会建出过不了 `wb vault check` 的页**。
修法：占位符全部加引号、通用模板的 `project` 绑定改为注释（可选）、`event-plan` 补 frontmatter（原来连 frontmatter 都没有）。
修完**机械验证 16/16「插入即合法」**（只做 Obsidian 的 `{{date}}`/`{{title}}` 替换也不报错）。

**实测到的字段真相（写进指南）**：`validate_note` **只强制 `date` / `type` / `status`**；
把 `id`/`title`/`workstream`/`summary`/`people` 等逐个删掉，校验**仍然通过**（这些是「本库叠加必填」的约定，非机器强制）。

**另一条实测结论**：问答路径里每次都会 `index.build()` 做**增量同步**（按 path/mtime/size/hash 跳过未变文件），
所以使用者**写完手记不需要手动重建索引，下一次提问即可被检索到**。

**交付物**：
1. 库内 `index/sop.md` 新增「**入口指南 · 我该传什么、怎么传**」一章：总则、四条通道表、
   「建页三步」（选模板 → 放哪 → 只改 3 处）、目录对照表、不完美怎么办、节奏、常见错误对照、何时交 Agent、模板清单。
   同时把原来的「第 ① 步 · 上传」改写为「会议与零散捕捉」，与入口指南分工（避免重复）。
2. **交互版 HTML** `docs/product/INTAKE-GUIDE.html`（38KB，单文件、离线可用）：
   ①「我要入什么」10 个材料类型点选器；②**文件名生成器**（选线/类型/日期/短名 → 输出正确路径 + 一键复制）；
   ③**入库前自检 6 问**（实时进度条 + 判定：还不能入 / 快好了 / 可以入库，其中前 3 项为「检索能否用」的关键项）；
   ④四条通道表、建页三步、常见错误正反例、节奏、何时交 Agent、模板清单、打印友好。
   本机桌面副本：`~/Desktop/工作知识库-素材入口指南.html`。

**把这次修复变成常驻守卫**：库内模板在仓库之外，`tests/unit/test_vault_templates.py` 只覆盖仓库自带的种子模板，
**覆盖不到使用者库里的模板**——所以新增 `scripts/kb_check_templates.py`：模拟 Obsidian 的自动替换后逐个
`parse_frontmatter` + `validate_note`，任一不合法即 exit 1 并打印具体字段与原因。已写入通用门禁清单。
**变异验证（按铁律）**：把 `hr-person.template.md` 的 `title` 引号去掉后，守卫**立刻红**并指出
「frontmatter YAML 解析失败…found unhashable key」；还原后 16/16 转绿。

**验证**：HTML 的 `<script>` 用 `node --check` **语法通过**；HTML 标签用 `html.parser` 验**配平通过**；
16 个模板机械验证「插入即合法」（并由新脚本守住）；ruff 全过；`wb vault check` **70 篇**、`kb_verify_links` 全绿。
⚠️ 说明：`scripts/` 不在 mypy 配置范围内（`pyproject.toml` 的 `files = ["src","tests"]`），
新脚本与既有脚本一致（单独跑 `mypy scripts/xxx.py` 会报 `import-untyped`，全量 `mypy` 仍是 360 文件）。

**说明（诚实标注）**：指南里的「插入即合法」「下次提问即可检索」「只强制 3 个字段」都是**实测**结论，不是推测；
但「你自己操作」这条路线的**真实使用体验**尚未经过一轮实跑（下一轮你按指南建第一页时才能验证）。


#### 缺陷修复判据轮 · 把「哪些缺陷必须修」定成规矩 + 用测量否决一个直觉改动 —— 已完成（2026-09-14）

起因：使用者问「**一个一直存在的缺陷需要修复吗**」。这需要一条可复用的判据，而不是逐案拍脑袋。

**定下的判据（已写进 `_vault/conventions.md` §13「缺陷修复判据」）**：按**会不会继续制造新错误**分类——
① 持续制造新错误的 → **必须修 + 补机器守卫**（例：16 个模板插入不安全）；
② 只污染历史的 → 登记即可，**不必回头重做全库**；
③ 文档与实际不一致的 → **优先修**（误导判断，代价比表面大）；
④ 设计取舍 / 已知遗留 → 改动属检索侧，**必须先用 `kb_measure` 量**。
配套两条原则：**不做为了让指标好看的修改，也不做没人会用到的完美主义修复**；修完要留**变异验证**。

**顺带查出并修掉两处「文档与实际不一致」（第 ③ 类）**：
1. `conventions.md` **两处**（§9 检索约定、§13 遗留 1）都写「app 当前按 `##` 切块、等 R2 落地」——
   但 **R2 早已完成**（提交 `303ae49`，`HEADING = ^#{1,2}`，PLAN §12 亦记「已完成」）。
   这条过时声明**当场误导过一次判断**，已改正并注明校正原因。
2. **真正存在的限制反而没写进规范**：`###` 及更深**不算块边界**。已在 §9 写明，并给出可执行规则
   （**想让某节被 `路径#区块` 精确定位，就写到 `##`**），同时补进 `index/sop.md` 与交互版 HTML 的「常见错误」。
3. `conventions.md` §0.7 把「项目 ID 只允许 `[A-Za-z0-9_-]`」列为「**由 `wb vault check` 强制**」——
   实测**不成立**：该校验只在 `wb project new`（`project_registry.py` 的 `_PROJECT_ID_RE`）执行，
   `validate_note` 不查（`project: "{{project}}"` 也能通过）。已改为准确表述，并提示**填错不会报错、只会静默绑错**。

**用测量否决了一个直觉改动（重要）**：`###` 不切块看起来是缺陷，直觉上「把 `###` 也纳入块边界」应能改善
长文档可寻址性（2025 杭州《详细流程》有 19 个 `###`/`####` 却近似单块）。**实测相反**：

| 分块变体 | 二值 | 分档（命中/同篇不同块/未召回） | 排名均值 | 总块数 |
|---|---|---|---|---|
| 现状 `^#{1,2}` | **6/16 = 38%** | 6 / 4 / 6 | **2.7** | 857 |
| `^#{1,3}`（### 也切块） | **5/16 = 31%** ⬇️ | 5 / 6 / 5 | 4.0 ⬇️ | 1093 |

机制：父块（如 `## 关键结论`）的正文被拆进子块后，父块变空/变短，原先「命中父块」退化为
「同篇但块不同」或掉出窗口 ⇒ **上下文丢失的代价大于粒度收益**。与历史上「凭直觉改检索 44%→31% 被回退」同型。
⇒ **不采纳**；该限制改由「写作规则 + 指南」处理。证据：`docs/acceptance/evidence/kb-chunking-variants-2026-09-14.txt`。

⚠️ **测量过程中的自身失误（如实记录）**：第一次替换 `HEADING` 的脚本**静默失败**（正则未匹配却照常跑），
三次变体其实都在测同一个基线；第二次 `^#{1,6}` 变体也因**未从备份还原**而沿用上一变体，未取得有效读数。
教训：**测量脚本必须断言「替换已生效」**，且每个变体都要从干净副本出发——否则会得到"看起来有数据"的假结论。
（因此 `^#{1,6}` 变体目前**无有效数据**，不能据此下结论；已采纳的结论只基于有效的 `^#{1,2}` vs `^#{1,3}` 对比。）

**尚未做（建议项，待使用者决定）**：
1. **给 `project` 绑定加机器守卫**（第 ① 类，会持续制造静默错误）：`wb vault check` 校验
   `project`/`projects` 的格式（并可选校验项目是否存在）。会改代码，且需同步改三个仍带活跃占位符的模板
   （`work-log` / `meeting-note` / `project-main`），**并需重建 App 才在装机版本生效**。
2. **把「自助建页路线」做成可重复验证**（端到端）：模板插入 → 过 `wb vault check` → 建索引 → 问一句能召回。
   目前只有「模板插入即合法」这一环有守卫；整条路线仍是「我验证过一次」，不是机器守住。


#### project 绑定守卫 + 自助入库路线端到端验证 —— 已完成（2026-09-14）

承接上一轮「缺陷修复判据」的第 ① 类（**会持续制造新错误**）：给 `project` 绑定加机器守卫，
并把「模板 → 合法页面 → 可检索」整条自助路线从「我验证过一次」变成**可重复验证**。

**① 判据一度定错层，被两条既有测试当场纠正（重要记录）**
第一版把「项目 ID 只允许 `[A-Za-z0-9_-]`」也加进 `validate_note`，结果
`test_review_candidates.py` 的两条用例立刻变红——**会议提取管线里模型的 `projects:` 允许是自然语言项目名**
（如 `网课系统`），之后才按别名解析成规范 ID、解析不到则落 `unresolved` → 全局收件箱。
即 `meeting-note` / `meeting-transcript` 的 `projects:` 是**线索**而非最终绑定，在 schema 层按字符集判定
会**打断会议导入**。⇒ 判据收窄为「**只拦一定错的**」：**未替换的模板占位符**（`{{…}}`）。
这是「判据写错了要说清原因」的一次实操：**不是为了让测试变绿而放松**，而是原判据本身与产品行为冲突。

**② 交付**：
- `domain/vault.py`：新增 `PROJECT_ID_RE`（唯一真源，`project_registry.py` 改为复用它）+ `_check_project_placeholders`，
  在 `validate_note` 里调用 → `wb vault check` 现在会拒绝 `project` / `projects` 里的 `{{…}}`，
  并给出可执行提示（「请填真实项目 ID」）。
- `tests/unit/test_vault_project_binding.py`（18 条）：占位符必须红；5 个真实 ID 与 `global` 必须绿；
  **并把「会议管线允许自然语言项目名」钉成一条正向用例**（写明这是有意行为，收紧须同时改管线与测试）。
- `tests/unit/test_intake_route.py`（5 条，**端到端**）：① 种子模板集合必须被测试完整覆盖；
  ② 模板**留着占位符也必须能 YAML 解析**（原始缺陷的直接守卫）；③ 渲染成真实页面后必须过 `check_vault`；
  ④ 新写入的页面必须**能被建索引并检索到**（＝「下一次提问就能检索到」）；
  ⑤ 反向对照：`draft` 页面**不该**被检索到。
- **不需要重建 App**（实测确认）：`webapp/` 与 `workflows/` **都不调用** `validate_note`，
  校验只在 CLI / Agent 侧生效 ⇒ 改校验不动装机版本。

**③ 顺带查出并修掉两组同类缺陷（都在「产品侧」，比库内更值钱）**：
- **仓库自带的 13 个种子模板里，4 个也「插入即红」**（`meeting-note` / `meeting-transcript` /
  `project-main` / `work-log`——占位符未加引号 → YAML 非法映射）。每个新工作台都带着它们。
  已加引号修复，并给检查脚本新增 `--placeholders keep|substitute` 两种判据：
  **keep**（占位符照留也必须合法）用于使用者库内模板；**substitute**（替换后再校验）用于参考骨架。
  现状：库内 16/16 keep 绿、仓库种子 13/13 substitute 绿。
- **`note.template.md` 默认 `status: draft` ＝ 不进问答检索**：分析笔记是最高频产出，
  默认不可检索与「先入后改、可检索」直接冲突 ⇒ 改为 `active`。其余三个默认 `draft` 的模板
  （`cluster` / `long-form-thought` / `event-plan`）**是刻意的**（未成熟/未定型不该被当事实引用），
  保留并在两份指南里写明「想被引用就改 active」。
- 库内 3 个仍带活跃占位符的模板（`work-log` / `meeting-note` / `project-main`）改为**真实默认值**
  （`[hr]` / `[it-development]` / `hii-affairs`）+ 醒目提示，既保住「插入即合法」，又不会绑到不存在的项目。

**④ 变异验证（全部真做）**：去掉 `_check_project_placeholders` 调用 → 8 条用例红；
去掉种子模板里的引号 → `test_seed_templates_parse_even_with_placeholders_left` 红。
⚠️ 第一次变异**没有红**——因为 E2E 在写入前就把占位符替换掉了，抓不到"未替换"这一形态；
这条自身弱点由变异验证暴露，随后补了第 ② 组守卫（只做 Obsidian 自动替换、其余占位符原样保留）。

**门禁**：pytest **1189 passed / 1 skipped / 83.84%**（较上轮 +23 条）；ruff（480 文件）；
mypy（362 文件）；secret_scan；`wb vault check` 70 篇；`kb_verify_links` 全绿；
模板守卫双模式全绿。

### 内容质量与「工作 vs 建库」边界轮 · 5 个项目页改写 + `.obsidian` 过滤 —— 已完成（build 44）

作业单：`NEXT-SESSION-PROMPT-CONTENT-QUALITY.md`。使用者原话：「其实本质上是我们入库的东西呈现出
什么样子。我希望的是这个 work 知识库是和我本身工作更相关的知识库沉淀，而不是和编程以及
【建知识库】相关的。」——他要的是**和他工作相关的知识沉淀**，不是**关于建库的说明**。

#### 使用者报的 5 个问题

① 项目详情页 `## 当前状态` 是一大段散文，阅读友好度差；
② `## 下一步` 混进大量「交素材 / 建对象页 / 用哪个 slug / 素材放哪个目录」；
③ 「公司人事」不是 HR 那种人事，而是「和公司每一个人的长期沟通」；
④ App【项目】里出现 `.obsidian`；⑤ 项目页里不该出现建库类内容。

#### 落成什么（6 个已对齐决策全部执行）

1. **内容边界写进规范**：`conventions.md` 新增 **§0.8**（只进库＝工作事实 / 结论 / 决定 / 下一步 /
   阻塞 / 出处；只进仓库侧＝怎么建库、目录、slug、模板、桌面素材目录、入库批次、校验脚本、Agent 步骤）
   与 **§4.9**（`## 当前状态` 分点分层、`## 下一步` 只写工作事项且**不推断**、`## 阻塞` 只写工作阻塞、
   禁止出现的建库类清单 + 自检口诀「这是使用者的**工作**还是 Agent 的**建库**？」）；§4.2 加了指向 §4.9 的指针。
2. **5 个项目页全部改写**：`hii-affairs` / `it-development` / `huoman-community` / `huoman-logistics` / `hr`。
   建库类内容按机器判据 **0 命中**；`## 当前状态` 全部分点分层（`it-development` 的六行表改为分点，
   其余为「结论在前 + 出处」的短点）；`## 下一步` 只留工作事项，缺材料处写「（待补：等材料到位）」，
   **没有为凑字数编造任何下一步**。
3. **「公司人事」重新定位**（决策 3）：`title` → `公司人事（与每个人的沟通）`，`summary` / 正文定位 /
   `aliases` 同步；**目录 `hr/` 与项目 ID `hr` 未动**（避免契约级改动）。`hr/clusters/` 的四个待建主题
   （招聘 / 入职 / 绩效 / 离职与权限清退）删除，`index/projects.md` 与 `_vault/README.md` 目录速览同步。
4. **建库内容不丢**：新建仓库侧 **`docs/implementation/WORKBENCH-MAINTENANCE-TODO.md`**，
   逐条汇总从 5 页移出的素材交付 / 目录指引 / 建页指引 / 入库批次 / Phase 引用，加上素材侧缺口与
   待验证项。库里不出现，但下一窗口能查到。
5. **App 目录过滤统一修**：`Work/.obsidian` 漏进【项目】的根因是
   `project_scan.is_internal_dirname` 只挡下划线前缀，而「哪些目录不算内容」这条判据当时**散在三处**
   （`project_scan` / `vault` / `kb_index`）各写名单。新增 `repositories/ignore.py` 作为唯一真源
   （点开头 + 机器目录名 `templates` + 下划线前缀），三处遍历改取共享判据；Markdown 遍历只判目录部分
   （`parts[:-1]`），文件名不误伤。

#### 验证（真做）

- **变异验证**：① 判据退回「只判下划线」⇒ `test_ignore_dirs.py` **4 条红**；
  ② `MACHINE_DIRNAMES` 去掉 `templates` ⇒ **3 条红**；还原后 5/5 绿。
- **真实数据（真库）**：`Work` 根目录下修复前 `scan_projects` 返回 `['.obsidian']`，修复后 `[]`；
  `scan_all_projects` 正常给出 5 条 vault 档案线程。
- **已装 App 实测（build 44）**：`GET /api/state` 的 `projects` 只有 5 条线程、**`.obsidian` 已不出现**；
  `GET /api/projects/view?name=hr` 的 `## 当前状态` 返回有序列表块，正文无「素材放 / 已示范一次 / 建对象页」。
- **门禁**：pytest **1194 passed / 1 skipped / 83.85%**（+5 条）；ruff（484 文件）、ruff format、
  mypy（364 文件）、secret_scan 全过；`wb vault check` 70 篇全过；`kb_verify_links` 465 双链 /
  427 块级引用全解析；`kb_verify_quotes` 两个素材根各 37 条 **0 问题**；
  `kb_index_people --check` 与 `frontmatter` 一致（36 人 / 4 组织）；模板守卫 keep 16/16、substitute 13/13。
- **顺带修掉一处文档与实际不一致**（§13 缺陷判据第 ③ 类）：`index/projects.md` 写「三场均缺一手复盘」，
  实际 2026-06-07 已有 ⇒ 改为「2025 两场缺」。

#### 已知不足 / 未验证

- **`## 下一步` 变薄是刻意的**：`huoman-community` / `huoman-logistics` / `hr` 各只剩 1–2 条，
  因为原条目大半是建库待办。**没有补编**——等工作侧材料到位再长回来。
- **`ignore.py` 的机器目录名是显式清单**（目前仅 `templates`）：将来新增无前缀机器目录时必须登记。
  点开头目录已由前缀规则自动覆盖（`.obsidian` / `.git` / `.summit-workbench`）。
- **未重跑**：两轮调模型的验收（`kb_acceptance*.py`）与 `kb_measure.py`——本轮只动内容边界与目录过滤，
  未触碰检索权重 / 词表 / 分块，按规范记「未重跑及其理由」。
- **App 首次读 vault 的 TCC 弹窗**：ad-hoc 签名包替换后第一次读文稿文件夹会弹授权，需使用者点允许。
