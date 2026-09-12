# 收尾提示词 v7：只剩 1 项（C4，需要飞书授权）

> **v7 变更**：**R09、R05、B4 全部通过**。`OPEN-VERIFICATION-ITEMS.md` 中的 UI 层开放项
> **已清零**——除本项外只剩 A6（需第二台机器）与 F1（明确超出交付范围）。
>
> 本文件现在只描述 **C4：「新建会议（个人日程）」落点**。它是唯一需要账号所有者介入的一项。

---

## 复制区（从这里开始）

你要验证一项会**在真实飞书日历创建事件**的功能。

### 铁律

1. 这一项**必须在真实飞书上做**，因此**开始前必须先向账号所有者取得明确授权**。
   没有授权就回报「未验证：无飞书授权」并停止，**不要**自行尝试。
2. **开始前确认屏幕上没有钥匙串弹窗**：飞书令牌是从**登录钥匙串**读的
   （`com.summitworkbench.credentials.<workspace_id>` / `feishu:<app_id>:refresh_token`）。
   模态弹窗会让读取阻塞，产出一个**与产品无关的失败**。
3. **只创建一个事件，回读校验后立即删除，不留残留。**
4. 每个断言都要有原始证据（event id、回读字段、删除结果、界面文案）。

### 环境

用**临时环境**，不要碰真实工作区：

```bash
ISO=$(mktemp -d /tmp/swb-c4-XXXXXX)
mkdir -p "$ISO/home" "$ISO/work"
export HOME="$ISO/home" WORK_ROOT="$ISO/work"
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/wb web --host 127.0.0.1 --port 18931 &
```

按向导新建工作区。**模型可以选「跳过」**；**飞书必须真的授权**（这是本项的前提）。
授权完成后回报设置页 / 授权页显示的状态原文。

### 夹具

在 `_vault/review/meetings.md` 造一条落点为**新建日历会议**的候选：

```markdown
---
date: '2026-09-12'
type: approval-page
status: active
project: global
---

# 会议提取待确认

## 2026-09-12 合成会议  [[meetings/notes/2026-09-12-synthetic]]

- [ ] `id: local:fixture#action-item-c4` [action-item] 合成：与飞书日历联调（验证后删除）
  - target_project: unresolved
  - route: feishu-meeting
  - due_date:
  - start_at: 2026-09-15T10:00
  - end_at: 2026-09-15T11:00
  - evidence: 说话人 甲 00:00:01
  - actionable: yes
  - historical: no
  - note: [[meetings/notes/2026-09-12-synthetic]]
  - transcript: [[meetings/transcripts/2026-09-12-synthetic]]
  - error:
  <!-- wb-original: <base64url(JSON: description,target_project,route,due_date)> -->
```

- `route: feishu-meeting` 是**新建日历会议**落点；它**不需要**已解析项目
  （`is_actionable()` 对 `global-inbox` 与 `feishu-meeting` 豁免目标项目检查），
  所以 `target_project: unresolved` 也应可勾选——**这本身就是一条要验的资格逻辑**。
- `start_at` / `end_at` 是**本地 naive** `YYYY-MM-DDTHH:MM`，请用**未来时间**。
- `wb-original` 的编码：`base64url(json.dumps({"description":…,"target_project":…,"route":…,"due_date":…}, ensure_ascii=False, separators=(",",":")))`。

### 步骤与通过标准

1. **资格**：打开审批页，确认这条 `feishu-meeting` 候选**可选中、可批准**，
   且「批准」按钮**未被禁用**。回报界面文案原文。
   （可选对照：把 `evidence` 清空后应变为不可批准、title 说明原因。）
2. **预演**：点「检查并写回」→ 确认是 **DRY-RUN、零写入**（此时日历里**不应**出现新事件）。
   回报预演输出原文。
3. **写回**：点「确认应用（写回）」→ 只创建**一个**事件。
4. **回读校验**：确认日历里确实出现了该事件，且标题 / 开始 / 结束与候选一致。
   **回报事件的 `event_id` 与回读到的字段**。
5. **删除**：删除该事件，确认删除成功，并再次回读确认**查不到**它。
6. **不留残留**：确认没有多余事件被创建（只此一个）；临时工作区可随后删除。

**通过标准**：候选可批准 → 预演零写入 → 写回恰好创建一个事件 → 回读字段一致 → 删除后查不到。

### 回报格式

```
任务：C4 新建会议（个人日程）落点
环境：临时 HOME/WORK_ROOT；端口；frontend_build；飞书授权状态
结论：通过 / 失败 / 未验证
证据：候选可批准的界面文案；预演输出原文；event_id；回读字段；删除结果
```

## 复制区结束

---

## 附：当前开放项全貌

| 项 | 状态 | 说明 |
|---|---|---|
| C4 新建会议落点 | **待授权** | 本文件；唯一需要账号所有者介入的项 |
| A6 真实双设备冲突恢复 | 待第二台机器 | 代码路径已有端到端自动化 + 变异测试覆盖，缺的只是现场复跑 |
| F1 Developer ID / 公证 / Intel / Windows | **非缺陷** | 明确超出 `INTERNAL-DEV` 交付范围 |

**已关闭**：A1–A5、B1–B4、C1–C3、D1–D3、E1–E5、F2，以及 R01–R14 全部。
