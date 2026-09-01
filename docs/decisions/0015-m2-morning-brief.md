# ADR 0015 · M2 晨间简报（手动全链路切片）

- 状态：✅ M2-1~M2-10 全部实现，离线全绿（ruff+mypy strict+pytest 277 项）；日历/任务端点已真机核实；
  ⏳ 用户需重新授权任务细粒度 scope 后 `wb feishu tasks` 才通；⏳ launchd 连续 7 天真机验收待跑
- 日期：2026-09-01
- 里程碑：M2 · 晨间简报与周复盘（环 A）
- 依据：`docs/plans/DEVELOPMENT_PLAN.md` §7；PRD §「M2 晨间简报」、L12/L26/L28/L43、G1/G2、
  「环 A 输出契约」（3.4）

## 本轮范围（用户拍板，2026-09-01）

- **交付边界**：先做手动 `wb brief` 全链路切片（M2-1~M2-6、M2-8、M2-9）+ 离线测试；
  launchd 定时（M2-7）与周复盘（M2-10）下一轮。
- **飞书端点策略**：日历/任务按官方文档预期端点实现 + httpx MockTransport 契约测试，
  提供冒烟子命令，确切端点由用户稍后单独真机核实后固定（沿用 M0-4/M0-10 的「预期端点 → 真机核实」范式）。
- **排序失败降级**：排序模型不可用 / 返回非法 JSON 时，走确定性回退排序（证据等级 + 截止日期 +
  混合配额），简报照常生成并在首行健康度标注「排序降级」（对齐 PRD「失败必须可见」+「即使一条不录入
  简报仍有实质内容」）。

## 硬约束（不可退让）

- **事实区 100% 原文直取**（G1=0）：会议标题/时间、任务名/截止、git 状态、inbox 条目每个字都来自
  飞书原始响应或 git/文件系统，**不经过模型**。
- **模型只做排序**：环 A LLM 输出**必须**是「条目 ID 排序数组 + 分组标签」的严格 JSON，禁止任何
  自然语言正文（PRD 3.4）。模型只能对已收集到的候选排序，不得新增/改写/升级证据等级。
- **行动 ≤ 5 条/天**（G2），默认混合配额：主线推进 2 + 近期承诺 2 + 防止停摆 1，无对应信号动态补位（L12）。
- **证据三级 E1/E2/E3**（L26）：E1 已完成（机器可验证闭合）、E2 正在推进（新 commit/未提交改动/主笔记
  状态更新）、E3 待确认（模型推断，禁入事实区、禁参与完成统计、禁自动升级）。
- **幂等**：同一日期重跑只替换当日笔记的简报区块（`<!-- BRIEF:START -->`~`<!-- BRIEF:END -->` 锚点），
  不重复追加、不重复推送。

## 分层设计

- `domain/brief.py`（纯）：`EvidenceLevel`、`ActionCategory`、`ActionSignal`、`FactBlock`、
  `HealthState`、`Brief` 数据模型；`select_actions()` 配额分配（≤5、动态补位）；`fallback_ranking()`
  确定性回退（证据等级→截止日期→稳定 id）。无 IO、无供应商。
- `providers/feishu/calendar.py`：`list_events(client, start, end)`（预期端点
  `/open-apis/calendar/v4/calendars/primary` + `/calendars/{id}/events`，待真机核实）。
- `providers/feishu/tasks.py`：新增 `list_tasks(client)`（GET `/open-apis/task/v2/tasks`，读未完成 + 截止）。
- `repositories/project_scan.py`：离线扫 `WORK_ROOT` 各 git 仓库（dirty / ahead·behind，纯本地 ref，
  不联网）+ 项目 inbox 待处理数 + 项目主笔记 `## 下一步`。复用 `GitRepo`、`discover_repos`。
- `repositories/signal_snapshot.py`：当日信号快照落 `_vault/_signals/YYYY-MM-DD.json`（北极星指标基线）。
- `repositories/daily_note.py`：锚点区块幂等写入 `_vault/daily/YYYY-MM-DD.md`。
- `observability/notifier.py`：`send_notification()` 经 `osascript` 发 macOS 通知，非 darwin/无
  osascript 时安全空转。
- `workflows/brief/`：`collect.py`（逐源隔离采集，单源失败不阻断）、`ranking.py`（LLM 排序 + 回退）、
  `render.py`（模板渲染：首行健康度 + 事实区 + 提议区 + 最近完成 + ≤5 行动）、`brief.py`（编排）。
- `cli/brief.py`：`wb brief`（`--date` / `--no-push` / `--dry-run` / `--json`）。

## 验收（本轮）

- Ruff + mypy strict + pytest 全绿；新增单元覆盖配额分配、回退排序、健康度、快照往返、
  项目扫描、daily 锚点幂等、渲染快照（固定 fixture 比对，事实区零偏差）；契约覆盖日历/任务响应解析。
- `wb brief --dry-run` 对隔离 vault 生成一份结构完整的简报（事实区/提议区/健康度/最近完成/行动≤5）。
- 飞书日历/任务真机冒烟、launchd 与连续 7 天验收、周复盘留待后续。

## 追加实现（同一里程碑内完成）

- **真机冒烟修正（merge f2fa52c）**：日历改用 `instance_view` 展开循环取当天实例（普通 events 列表返回
  循环主体原始 start_time）；任务需用户态细粒度 `task:task:read/write`（粗粒度 `task:task` 报 99991679），
  DEFAULT_SCOPES 已改，**用户需重新 `wb feishu authorize-url`→`login`**。新增 `wb feishu calendar/tasks` 冒烟命令。
- **M2-7 launchd + 提交（merge 564fe3f）**：`wb brief --commit --push`；`repositories/git.py` 加非破坏性
  `add(指定路径)/commit`（绝不 add -A，只暂存简报文件，尊重 vault 由用户/wb sync 提交的约定）；
  `workflows/brief/publish.py` 幂等提交、落后不推；`deploy/launchd/` 每日 08:00 plist + `scripts/install-launchd.sh`。
- **M2-10 周复盘**：`wb weekly`（`--date/--dry-run/--commit/--push/--json`）复盘上一自然周（周一 07:30 语义，L27）；
  `domain/weekly.py`（ISO 周 math、去重分区、确定性下周建议）、`workflows/weekly/{collect,render,weekly}.py`、
  `repositories/weekly_review.py`（幂等按周覆盖 `reviews/weekly/YYYY-Www.md`）。offline-first 从 git 提交 +
  会议笔记 `## 已形成决策` + inbox + 停滞项目重新汇总去重，事实附来源、下周建议(E3)单列提议区；
  周一 07:30 plist 已加。

## 遗留

- 用户重新授权任务细粒度 scope（日历已真机可用）。
- launchd「连续 7 天简报 + 1 份周报」真机验收待在 Mac Studio 上实跑。
- 健康度「连续 7 天无信号 / 连续 3 天失败」跨日 streak 判定依赖快照历史（当前为单日健康度）。
- L28「周建议自动进入下周简报提议候选池」的读取侧接线（周复盘已产出 `proposal` 项，简报侧读取待接）。
- 周复盘「模型化跨项目综合」（当前下周建议为确定性启发式，不调模型）。
