# ADR 0002 · M0-2 工作目录与项目迁移记录

- 状态：已执行
- 日期：2026-08-30
- 里程碑：M0-2（工作目录与项目迁移）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §5 M0-2；PRD L9 / L10 / NFR-3

## 背景

按 PRD L9，工作项目根目录统一为 `~/Documents/Work/`，与个人项目 `~/Documents/GitHub/`
分离。M0-2 把 4 个指定项目迁入新根目录，并补齐 Agent 项目档案。

## 安全前置检查

- **iCloud 边界（L10 / NFR-3）**：确认 `~/Documents` 未开启 iCloud「桌面与文档」同步
  —— `~/Library/Mobile Documents/com~apple~CloudDocs` 顶层只有 `Downloads`，无 Documents 镜像；
  现有 `.git/objects` 为真实文件而非 dataless 占位符。故 `~/Documents/Work/` 放置 git 仓库安全，
  不触碰「严禁用 iCloud/Dropbox 同步含 `.git` 的目录」红线。
- `~/Documents/Work/` 迁移前为空，无同名冲突。

## 迁移前状态（原路径 `~/Documents/GitHub/<项目>`）

| 项目 | 分支 | HEAD | 远端 | 工作树 |
|---|---|---|---|---|
| HoffmanWebChinaEnrollment | `codex/ripple-of-love-prd` | `aca6e2f` | `git@github.com:yifeng93/HoffmanWebChinaEnrollment.git` | dirty（2 项：`.workbuddy/`、`backend/target/`）|
| HIC_SWB_LaTEX | `main` | `f5b5fc8` | `https://github.com/yifeng93/HIC_SWB_LaTEX.git` | clean |
| HIC_WebClass_Chinese_Final | `main` | `6fcb12c` | `https://github.com/yifeng93/HIC_WebClass_Chinese_Final.git` | clean |
| HIC_Logistics | `main` | `1b8e5b0` | `https://github.com/yifeng93/HIC_Logistics.git` | clean |

## 迁移动作

1. `mkdir -p ~/Documents/Work`。
2. `mv ~/Documents/GitHub/<项目> ~/Documents/Work/<项目>`（同盘移动，保留 `.git/`、分支与未提交内容）。
3. 迁移后逐项对比分支 / HEAD / 远端 / `git status` 指纹：**与迁移前完全一致**（未丢失未提交内容或远端配置）。

## 迁移后补充交付（M0-2 内容改动）

- **HIC_Logistics 过期绝对路径修复**：`README.md`、`AGENTS.md` 中 `cd /Users/yifengair/Documents/GitHub/HIC_Logistics`
  → `cd ~/Documents/Work/HIC_Logistics`（旧机器用户名 `yifengair` + 旧位置；改为可移植形式，符合 NFR-3）。
- **补齐 Agent 项目档案**：为缺失的 3 个项目（Hoffman、SWB、WebClass）新建 `AGENTS.md`；
  4 个项目均新增 `CLAUDE.md`，仅含一行指向 `AGENTS.md` 的引用（PRD 3.2.2，为未来接入 Codex 保留零迁移）。
- **Claude Code 权限**：`~/.claude.json` 无残留旧路径 project 条目，各项目原本无 `.claude/`，无需清理。
  新路径的交互信任由用户首次在各目录运行 `claude` 时确认（属交互动作，不由自动化代按）。

## 尚待用户完成

- 在每个 `~/Documents/Work/<项目>` 首次启动 Claude Code，确认目录信任提示。
- 4 个项目仓库中的上述改动（AGENTS.md / CLAUDE.md / 路径修复）当前为**未提交**状态，
  按各自项目的 git 工作流分别提交（SWB 另受 `docs/project/GIT_WORKFLOW.md` 治理）。

## 验收对照

- ✅ `~/Documents/Work/` 建立，4 个项目迁入。
- ✅ 迁移前后各项目 git 状态逐项一致，无丢失。
- ✅ 过期绝对路径已修复为可移植形式。
- ✅ 4 个项目均具备 `AGENTS.md` + 一行引用式 `CLAUDE.md`。
- ⏳ 新路径下 Claude Code 交互信任待用户首次启动确认。
