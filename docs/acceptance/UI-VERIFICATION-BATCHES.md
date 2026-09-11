# 剩余 UI 层验收 · 分批执行清单（交给 Codex / computer use）

> 覆盖 `OPEN-VERIFICATION-ITEMS.md` 中除 **A6**（需第二台机器）与 **F1**（超出交付范围）之外的
> 11 项开放项。逐条断言的**长文原文**在 `BROWSER-VERIFICATION-PROMPTS.md`（提示词 A–G）；
> 本文件负责**夹具、分组与顺序**——按"需要什么数据"分组，而不是按编号，因为造夹具才是真正的成本。

## 0. 通用前提（每批都适用）

- **隔离环境**：临时 `HOME`、临时 `WORK_ROOT`、临时 vault；**不要**用产品所有者的真实工作区。
- **不连接任何外部服务**：下列 8 批中除**批次 7**外，**全部不需要真实模型或飞书**——
  它们验证的是界面机制，用合成夹具即可，且必须做到**零外部副作用**。
- **判定规则**：只写「通过 / 失败 / 未验证」；**没有实际观察到的一律写未验证**，
  不要用"源码里是这样"或"看起来正常"代替观察。
- **证据**：每条断言都要有截图，或 Console/Network 的原始输出（按 `BROWSER-VERIFICATION-PROMPTS.md` §11 格式回报）。
- **优先用 `document.activeElement` 等可判定量**，而不是"看着对不对"——上一轮场景 C 就是栽在这上面。

## 1. 批次总览与依赖

| 批次 | 覆盖 | 关键夹具 | 需要外部服务 | 依赖 |
|---|---|---|---|---|
| 0 | 环境基线 | 临时 HOME/WORK_ROOT/vault、本地服务 | 否 | — |
| 1 | C1 / C2 / C4（+R08） | **N 条待确认候选（0/1/100/101）** | 否 | 0 |
| 2 | D2 / D3（+R13 / R14） | **特定尺寸/异常路径的来源文件** | 否 | 0 |
| 3 | E1 / E2（+R06） | **合成 git 分叉** | 否 | 0 |
| 4 | E3（+R01） | **高到可滚动的项目详情页** | 否 | 0 |
| 5 | E4（+R07） | **两个 loopback 端口 + 一条未保存草稿** | 否 | 0 |
| 6 | R03 / R04 / R05 / R09 / R10 / R11 | 长文本、隐藏页计时、网络拦截 | 否 | 0 |
| 7 | B4 | **已安装的打包 App** | 否 | 0 |

**推荐顺序：0 → 1 → 2 → 3 → 4 → 5 → 6 → 7。** 批次之间互不依赖（只因夹具不同而拆分），
所以也**可以并行**；只有批次 0 是所有批次的前置。

## 1.1 执行结果与**剩余待跑项**（截至第三轮）

已跑过三轮（`frontend_build=v2026.09.11-6ff10a6-6e6e0c91`）。**不要重复已通过的项**。

| 批次 | 已通过（不必重跑） | 剩余待跑 | 关键原因 |
|---|---|---|---|
| 0 | 全部 | — | — |
| 1 | C1、C2、R08、C4 部分 | **C4 的「新建会议」落点** | C1 已于第二轮按网络计数关闭；新建会议**确实需要飞书授权** |
| 2 | D3、非 UTF-8（415，第一轮缺陷已确认真实修复）、413、路径穿越、软链越界、非知识目录、缺失文件 | **D2 的面板界面文案**；**第二 workspace 隔离** | HTTP 矩阵第三轮已全部拿到，只剩界面文案与跨 workspace 一项 |
| 3 | E1、E2、R06（**全通过**） | — | — |
| 4 | **E3、R01（第三轮全通过）** | — | 夹具自证可滚动后一次通过；R01 靠 v2 自愈脚本跑通 |
| 5 | E4（已取得实测结果） | **R07**（**判据已更正**） | 第一轮缺口令计数；第二轮前置条件写错；**第三轮被判失败实为误判**——`0/10` 是分键存储的正常结果，正确判据见提示词 v3 任务 1 |
| 6 | R03、R10、R11 | **R04 / R05 / R09** | **R04 与 R09 都不需要真实凭据**（假密钥 / 本地造 outbox 行），见提示词 v3 任务 2、3 |
| 7 | — | **B4 全部**（按 §9 的临时 `HOME` 隔离配方） | 第一轮因绑定真实工作区而停止 |

> **下一轮请直接用 [`UI-VERIFICATION-FINAL-PROMPT.md`](UI-VERIFICATION-FINAL-PROMPT.md)**
> （现为 v3）：自包含、只含剩余 6 项，带两个**已实测通过**的脚本与逐项夹具。
> 本文件的夹具配方作为背景保留。

---

## 2. 批次 0 · 环境基线（必须先做）

```
1. 建临时环境：HOME、WORK_ROOT、vault 各一份，互相隔离。
2. 在该 workspace 里跑本地服务（`wb web`），按向导新建工作区；模型与飞书都选「跳过」。
3. 确认：六个页签可达、Console 无异常、`document.body.scrollWidth <= innerWidth`。
4. 记录基线：服务端口、`frontend_build`（取自 static/build-meta.json 或页面版本显示）、
   临时目录路径。后续每批回报都要带上这些。
```

**通过标准**：批次 0 不通过就不要往下做——否则后面无法判断失败是夹具问题还是产品问题。

---

## 3. 批次 1 · 审批边界（C1 / C2 / C4，顺带复验 R08）

### 夹具（关键：不要用真实模型造 100 条）

不要用真实会议/模型去攒 100 条候选——那是 100 次模型调用。待确认页是纯 Markdown
（`_vault/review/meetings.md`），**直接按解析器要求的格式生成 N 条**：零模型调用、完全确定性。

解析器（`repositories/review_page.py`）的**硬性要求**，漏一条整页就报错或读不出候选：

1. **必须有 frontmatter，且 `type: approval-page`**——否则整页被判「不是 approval-page」，
   零候选（这是最容易漏的一条）。
2. **候选必须挂在 `## 日期 标题  [[笔记]]` 分组标题下**——没有标题时 `meeting_date` 为空。
3. 首行必须是 `` - [ ] `id: ...` [kind] 正文 ``（`- [x]` = 批准；`~~...~~ #ignore` = 拒绝）。
4. 字段行缩进**恰好两个空格** + `- `。
5. `wb-original` 注释行**必须以两个空格开头**且以 ` -->` 结尾，否则会被当成普通 HTML 注释整段跳过；
   它决定「撤销」能否恢复 AI 原值（缺省时回退为当前正文，于是撤销无变化、R03 测不出来）。

可直接循环套用的正确模板（`{n}` 为序号，`{kind}` 取 `decision` / `action-item`）：

```markdown
---
date: '2026-09-11'
type: approval-page
status: active
project: global
---

# 会议提取待确认

## 2026-09-11 合成会议  [[meetings/notes/2026-09-11-synthetic]]

- [ ] `id: local:fixture#action-item-{n}` [action-item] 合成候选正文 {n}
  - target_project: demo-project
  - route: project-main
  - due_date: 2026-09-01
  - start_at:
  - end_at:
  - evidence: 说话人 甲 00:00:01
  - actionable: yes
  - historical: no
  - note: [[meetings/notes/2026-09-11-synthetic]]
  - transcript: [[meetings/transcripts/2026-09-11-synthetic]]
  - error:
  <!-- wb-original: <base64url(JSON: description,target_project,route,due_date)> -->
```

- 同一页里**候选 ID 不得重复**（重复会被判错并整页拒绝写入）。
- 上表空字段（`start_at` / `end_at` / `error`）**行尾不要留空格**——真实渲染器会带一个尾随空格，
  但解析只做 `startswith("  - start_at:")`，去掉不影响；而留空格会被仓库的 `git diff --check` 拦住。
- **101 条是能正常读入页面的**（已实测 101 条全部解析成功）；被拦住的是「单批操作」——
  `web/src/legacy-main.ts` 的 `REVIEW_BATCH_LIMIT = 100` 在发请求前就拒绝。所以 C1 要验证的是
  **客户端拦截**，不是页面读不出来。
- `route` 必须是合法枚举：`feishu-task` / `feishu-meeting` / `project-main` /
  `project-followup` / `project-inbox` / `global-inbox`；`kind` 同理（见 `domain/review.py`）。
- 让 `wb-original` 里的 `description` 与正文**不同**，撤销才有可观察效果。
- 在临时 vault 里**建好 `projects/demo-project.md`**，让批准后的写回有真实落点（否则 C2 虽然
  仍能计数，但得到的是失败响应，判断会变模糊）。
- 按四个规模各生成一份：**0 / 1 / 100 / 101** 条（0 条即只有 frontmatter 与标题）。

`wb-original` 的编码方式（与 `_encode_original()` 同口径，键序固定、紧凑分隔符、`ensure_ascii=False`）：

```python
import base64, json


def wb_original(description, target_project, route, due_date):
    raw = json.dumps(
        {
            "description": description,
            "target_project": target_project,
            "route": route,
            "due_date": due_date,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")
```

### 步骤与通过标准

| 覆盖 | 断言 | 通过标准 |
|---|---|---|
| C1 | 在 0 / 1 / 100 / 101 四种规模下分别点「批量批准」 | ✅ **第二轮已通过**（不再重跑）：101 条时 DevTools 过滤 `review/batch` 为 `0 / 2 requests`（提示上限且**零请求发出**）；100 条时为 `1 / 12 requests` 且 `POST /api/review/batch` 返回 `200 OK`，页面显示「待确认 0 · 已批准 100」 |
| C1 | 「一键拒绝过期项（N）」 | ✅ **本轮已通过**（不再重跑）：0 条时按钮原生 `disabled`，title 为「不受当前筛选影响：把截止日期早于今天的待确认条目全部置为拒绝（当前 0 条）」 |
| C4 | 落点为 `global-inbox` 与「新建会议（个人日程）」的候选 | `global-inbox` / `project-inbox` **本轮已验证可批准**；缺依据候选按钮 `disabled` 且 title 为「依据或目标项目缺失，请点「修改」补齐后再批准」（已验证）。**仍缺**：「新建会议（个人日程）」= `feishu-meeting` 落点，需要飞书，本轮未验证 |
| C2 | 打开 DevTools → Network，**清空后**点一次「确认应用（写回）」 | ✅ **本轮已通过**（不再重跑）：单击 `apply` 计数 = 1（`200 OK`）；快速双击时请求进行中按钮 `disabled`，最终 `apply` 计数仍 = 1（`200 OK`，`2.04 s`） |

### 陷阱

- C1 的 101 条**必须在网络层计数证明为 0 次请求**——只看提示文案不够，那正是本轮 C1 仍未关闭的原因。
- C2 **必须在网络层计数**，不能用"点了一次"或"按钮变灰了"代替。
- 本批只用本地落点（`project-main` / `project-inbox` / `global-inbox`），**不要用 `feishu-*` 落点**，
  否则会往真实飞书写。若夹具里混了飞书落点，请先改成本地落点再批准。
- 「检查并写回」处理的是**当前工作区全部已决定项**，不是当前筛选或选中项——预演里条数比勾选多属正常。

---

## 4. 批次 2 · 来源与截断（D2 / D3，覆盖 R13 / R14）

### 2.1 本轮发现的缺陷（已修复，需按修复后复验）

**非 UTF-8 文件打开时返回 500，用户看到的是无信息的兜底文案。**

- 现象：二进制来源显示 `ApiError: 服务内部错误，请稍后重试 [internal_error]`，
  而**不是**明确的「来源不是可读取的 Markdown 笔记」。
- 那串文案不是服务端写的，是**前端解析响应失败后的兜底**（`normalizeApiError`），
  所以「500」这一点当时只能在 Network 里看出来。
- 根因：`repositories/vault.py` 的 `load_note()` 直接 `read_text(encoding="utf-8")`，
  非 UTF-8 抛 `UnicodeDecodeError`；`/api/sources/read` 只检查了 `note.parse_error`
  （那是 frontmatter 错误），没兜住解码异常。
- 影响面**不止来源面板**：`load_note` 有 23 个调用点（项目扫描、问答检索、周报、审批扫描…），
  一个坏文件会让多个功能一起 500。
- 修复：把解码失败并入既有的 `parse_error` 通道——**所有 23 个调用点本来就都检查
  `note.parse_error`**（`thread_notes.py` 甚至为此抛 ValueError），所以这是顺着既有契约修，
  不是语义变更。`/api/review/source` 单独加了同样的保护。
- 回归测试：`tests/unit/test_vault_repo.py::test_load_note_reports_non_utf8_instead_of_raising`、
  `tests/unit/test_webapi.py::test_api_sources_read_rejects_non_utf8_file_instead_of_internal_error`
  （两处都做过变异检查：撤掉修复后测试确实失败）。

**复验时**：二进制夹具现在应得到 **415 + 明确文案**，不是 500。

### 夹具（在临时 vault 里造这些文件）

| 用途 | 文件 |
|---|---|
| 正常 | `projects/demo-project.md` |
| **非 UTF-8**（D2 的关键用例） | `projects/probe.md`，**内容是非 UTF-8 字节**（如 `\x89PNG\r\n\x1a\n...`） |
| 截断显示（R14/D3） | `projects/big.md`，正文 **100,000–256 KiB 之间** |
| 直接 413（R14） | `projects/huge.md`，**> 256 KiB** |
| 路径穿越 | 请求 `../../etc/passwd` 一类路径 |
| 符号链接越界 | `projects/escape.md` → 软链到 vault 外（如 `/etc/hosts`） |
| 非知识目录（R13） | `_signals/`、`notes/` 下的文件 |
| 不存在的文件 | `projects/missing.md` |
| workspace 隔离 | **另建第二个 workspace**，vault 里放一个同名但内容不同的文件 |

> **注意 `.md` 后缀**：`/api/sources/read` 会把非 `.md` 的来源 id 后缀改写成 `.md`
> （`legacy_app.py`：`if relative.suffix.lower() != ".md": relative = relative.with_suffix(".md")`）。
> 所以造一个 `probe.bin` 只会得到 404「来源不存在或已失效」——那是**另一个**用例，
> 不是「非 UTF-8」。要触发解码失败，文件必须真的叫 `.md`。

### 步骤与通过标准

1. 从审批候选的「来源」入口打开只读来源面板，逐个请求上表文件：
   - 正常 → 正常渲染
   - **非 UTF-8** → **415 + 明确文案**（如「来源不是可读取的 Markdown 笔记」）；
     **不得**出现 `[internal_error]`
   - `big.md` → 显示**前 100,000 字符**并出现「正文已截断」提示
   - `huge.md` → 明确 413，且**不**显示截断内容
   - 路径穿越 / 软链越界 / 非知识目录 → 明确拒绝（R13 为 400）
   - `missing.md` → 明确 404
2. 每个用例**同时记录 HTTP 状态码**（Network 面板）：本轮只拿到了界面文案，400/404/413
   都没单独取证。写回时把状态码一并附上。
3. 切到第二个 workspace，再请求同名文件 → 必须读到**第二个 workspace 的内容**，绝不能读到第一个的。

**通过标准**：以上每种情况都有明确、可区分的结果；没有静默空白；没有越界读取；
没有出现 `[internal_error]` 这类无信息兜底。

### 陷阱

- **符号链接越界**必须真造软链（`ln -s`），不能只改路径字符串。
- workspace 隔离必须**两个 workspace 都真实存在**，否则测不出隔离。
- 非 UTF-8 用例必须用**真的非 UTF-8 字节**（`printf '\x89PNG\r\n\x1a\n' > projects/probe.md`），
  用「读起来像乱码的中文」是无效的——那仍是合法 UTF-8。

---

## 5. 批次 3 · 同步冲突（E1 / E2，覆盖 R06）

### 夹具

在临时 vault 建一个**合成分叉**：本地提交与远端提交各一条，使同步进入 `diverged-protected`。
（做法与 `tests/integration/test_acceptance_dual_device.py` 相同：临时 bare remote + 两个 clone，
两边各提交后推一边。）

### 步骤与通过标准

| 覆盖 | 断言 | 通过标准 |
|---|---|---|
| E1 | 在冲突详情里点「导出冲突包」 | ✅ **本轮已通过**（不再重跑）：Chrome 原生下载记录 `summitworkbench-sync-recovery.zip · 979 B · 完成`。结论：上一轮"观测不到"是 **In-app Browser 的通道限制**，不是产品问题——本批必须用**原生 Chrome** |
| E2 | 在冲突弹层里做人工选择后按 Escape | ✅ **本轮已通过**（不再重跑）：原生确认框出现「当前弹层里有未保存内容。继续关闭并放弃草稿吗？」，取消后焦点实际回到冲突选择框 |
| R06 | 保护态横幅显示时让 `/api/sync/status` 失败一次 | ✅ **本轮已通过**（不再重跑）：停掉临时服务后刷新，横幅保留 `diverged-protected` 与上次同步信息，并显示「同步状态读取失败：TypeError: Failed to fetch（上方为上次成功读取的状态）」 |

### 陷阱

- **不要点击恢复写回**（`sync-conflict-apply`）。本批只验证导出、焦点与横幅三点。
- E1 的"下载成功"要以**事件/文件**为准；把响应体内容当成文件成功是错的。
- **本批必须用原生 Chrome**：E1 的下载事件在 Codex In-app Browser 里观测不到，
  换成原生 Chrome 后一次就拿到了。若沿用 In-app Browser 而看不到下载，那是通道限制，
  不要据此判产品失败。

---

## 6. 批次 4 · 项目与布局（E3，覆盖 R01）

### 6.1 先更正上一版的配方（**上一轮的「失败」是配方错，不是缺陷**）

上一版让执行者「打开详情 → 滚动到中部 → 返回 → 重新进入 → 期望 scrollY 恢复」，
结果实测 `scrollY=0`（`1359 → 0`）。经查源码，这是**符合设计**的：

- `showProjectView()` 在进入详情时**显式** `window.scrollTo({ top: 0 })`——详情总是从顶部开始。
- 它保存的是**打开详情之前列表页**的 `{tab, query, filter, scrollY}`；
  `backFromProjectDetail()` 在**返回列表时**才把那个 `scrollY` 还原。

所以 E3 要验的是**「返回列表后列表的滚动位置是否还原」**，不是「重新进入详情后详情是否停在原处」。
后者归零是预期行为，**不要记为失败**。

### 夹具

让**项目列表**明显高于视口——在临时 vault 里建**足够多的项目笔记**（例如 30–40 个
`projects/<name>.md`，`type: project-main`），使 `scan_all_projects()` 产出长列表。

### 步骤与通过标准

1. 停在**项目列表**（不要进详情），向下滚动到中部，记录 `Y1 = window.scrollY`（要求 `Y1 > 0`，
   并确认 `document.body.scrollHeight > window.innerHeight`，否则夹具无效）。
2. 点开任意一个项目详情。
3. 记录此刻 `window.scrollY`——**预期为 0**（详情从顶部开始），这是通过项，不是失败。
4. 点「返回」回到列表。
5. **通过标准**：回到列表后 `window.scrollY` 恢复到 `Y1`（给出实测前后值）；
   同时查询框内容与状态筛选值也保留。
6. R01 复验：制造乱序——在 Network 面板把某次 `/api/projects/view` 的响应**延迟**，
   然后快速切换项目详情并返回；**在途的旧响应不得把旧详情推回页面或抢焦点**。
   （本轮未制造乱序，所以 R01 仍未验证。）

### 陷阱

- 夹具**必须真的可滚动**——前两轮都因为 fixture 高度等于视口而无法验证。先用
  `document.body.scrollHeight` 与 `window.innerHeight` 自证夹具有效，再开始测。
- **不要**用「重新进入详情后期望滚动位置还原」当作判据（见 §6.1）。

---

## 7. 批次 5 · 端口与同源（E4，覆盖 R07）

### 夹具

同一个临时 workspace，在**两个不同 loopback 端口**上启动服务；先在一个端口上**留下一条明确的
未保存草稿**（例如问答会话的输入、或日志弹层的正文），再切到另一个端口。

### 步骤与通过标准

1. 端口 A：写入草稿，**不要提交**，记录草稿所在页面与内容。
2. 端口 B：打开同一页面，观察草稿是否存在。
3. **通过标准**：跨端口的行为**如实记录**——指南明确「动态 loopback 端口变化不承诺迁移」，
   所以**丢失不算失败**，但必须报告实测结果（存在/丢失/部分）。
   ✅ **本轮已取得实测结果（不必重跑）**：端口 A 输入框有草稿
   「合成端口 A 未保存草稿…」，切到端口 B 后显示 `0/10` 会话、输入框为空——**草稿跨端口丢失**。
   这与「不承诺迁移」的既定边界一致，**记为已测得的预期行为，不是缺陷**。
4. R07 复验（**仍未验证，需重跑**）：`/api/version` **省略 `workspace_id`** 时，问答历史仍应载入一次；
   然后再带 `workspace_id` 请求一次，确认不会重复载入。**必须在 Network 里给出两次请求的原始计数**——
   本轮没有取得计数证据。

---

## 8. 批次 6 · 交互健壮性（R03 / R04 / R05 / R09 / R10 / R11）

本批不需要特殊数据，重点是**时序与网络拦截**。

| 覆盖 | 步骤 | 通过标准 |
|---|---|---|
| R03 | 打开顶栏「↩ 撤销」 | ✅ **本轮已通过**（不再重跑）：`role=dialog` + `aria-modal` + 关闭按钮齐备；关闭后 `document.activeElement.id == "btn-undo"`、`backdropHidden=true` |
| R04 | 设置页保存模型后立刻刷新 | 保存前的旧读取**不得**覆盖保存后的新结果（可在 Network 里把读取响应延迟，制造乱序）。**本轮未验证：没有人为延迟旧响应** |
| R05 | 切到隐藏标签页停留 > 60 秒，再切回 | 隐藏页**期间不发**读取请求；回到前台**立即补一次**（版本 + 同步横幅）。用 Network 时间戳证明。**本轮未验证：没有取得隐藏页 > 60 秒的时间戳证据** |
| R09 | 让 `/api/external-actions` 的**旧响应晚于新响应**返回 | 审批页的外部写回列表**不被旧响应覆盖**。**本轮未验证：没有制造乱序** |
| R10 | 在捕捉/日志/产物里输入 > 100,000 字符 | ✅ **本轮已通过**（不再重跑）：输入 100001 字符后显示「内容超过 10 万字上限（当前 100001 字），请拆分后重试」 |
| R11 | 双击日志/产物的保存按钮、双击任务/会议行内编辑的保存 | ✅ **本轮已通过**（不再重跑）：`/api/threads/logs` 计数 = 1（`200 OK`，`2.02 s`），保存按钮在途 `disabled` |

### 陷阱

- R05 的"隐藏页暂停"要用**时间戳**证明，不能只看"没看到刷新"。
- R04 / R09 都要**人为制造乱序**（延迟旧响应），否则测不出竞态。
- 这三个未验证项有个共同点：**都不需要新产品 fixture，只需要在 DevTools 里做拦截/计时**。
  下一次执行时优先做它们，成本最低。

---

## 9. 批次 7 · 原生 App 黑盒（B4）

**唯一需要打包 App 的一批。** CI 里的 packaged smoke 只覆盖打包后的 server 与构建身份，
**不覆盖原生 UI**，所以这一批必须在**已安装的 `.app`** 里做，不能用浏览器代替。

### 9.1 上一轮的卡点与解法（**先读这段再动手**）

上一轮**正确地停了下来**：直接 `open -a SummitWorkbench` 会绑定产品所有者的**真实工作区**
（设置页显示 `/Users/yifengstudio/Documents/Work/_vault`、DeepSeek 已配置、飞书已授权），
继续操作就会碰真实数据。这个判断是对的。

但**不能用 `WORK_ROOT` 来隔离**：`webapp/server_entry.py` 明确写着打包后的 server
**永不消费 `WORK_ROOT` 或 `--work-root`**（那是给源码运行的）。App 只认 **active profile**。

App 的本机状态从 `home_dir()` 派生，而 `home_dir()` 就是 `Path.home()`
（`config/app_support.py` 的 docstring 明确说「测试通过显式 `home` 参数或 **HOME env 隔离**」）。
所以要隔离，就**用一个临时 `HOME` 直接启动可执行文件**，而不是 `open -a`：

```bash
ISO=$(mktemp -d /tmp/swb-app-iso-XXXXXX)
mkdir -p "$ISO/Library/Application Support"
HOME="$ISO" /Applications/SummitWorkbench.app/Contents/MacOS/SummitWorkbench
```

这样 profile registry 指向
`$ISO/Library/Application Support/SummitWorkbench/registry.json`——**不存在**，
App 应进入 **onboarding / 空安装**状态，而不是真实工作区。

### 9.2 动手前的**强制自检**（不通过就停）

启动后先看设置页：

- ✅ 期望：显示 onboarding 或空工作区，**不出现** `/Users/<真实用户>/Documents/Work/_vault`。
- ❌ 若仍显示真实 vault 路径：说明 `HOME` 没有生效（原生层可能用的是 `NSHomeDirectory()`，
  它读的是账户数据库而不是 `$HOME`）。**此时立即退出，不要再做任何操作**，
  把「原生 App 无法用环境变量隔离」作为 B4 的阻塞结论回报，不要强行继续。

### 9.3 步骤与通过标准

1. 按 §9.1 以临时 `HOME` 启动，通过 §9.2 自检。
2. 确认顶部/设置里显示的 build identity 与实际产物一致（记录 `frontend_build` 与 server 版本）。
3. 在 App 内走六页签可达性；若处于 onboarding，就**先走一遍新建工作台**流程
   （指向临时目录），这本身就是比浏览器更强的黑盒证据。
4. 若进入的是空安装：执行批次 1 的审批**只读预演**（**只做预演，不写回**）。
5. 关键：确认这些操作发生在 **WKWebView** 内而不是外部浏览器；记录原生层特有行为
   （窗口尺寸变化、菜单、快捷键、`ServiceSupervisor` 拉起/退出）。
6. 退出并重启 App，确认运行记录与版本握手正常（不出现 crash loop、不误认旧服务）。
7. 结束后删除临时 `HOME` 目录。

**通过标准**：上述在**原生 App 内**可复现；任何只在浏览器里通过的结果**不能**记为本批通过。
若 §9.2 自检不通过，本批结论就是**「因无法隔离而阻塞」**，并附上设置页实际显示的路径——
这是一个**有价值的结论**，比冒险操作真实数据好得多。

---

## 10. 不在本清单内

| 项 | 原因 |
|---|---|
| A6 真实双设备冲突恢复 | 需要第二台机器（MacBook Air） |
| F1 Developer ID / 公证 / Intel / Windows | 明确超出 `INTERNAL-DEV` 交付范围，非缺陷 |
| **R12** 文档漂移（PRD `updated` 表述） | **文档类**，不是浏览器可验项；已在源码层随实现更正，无需 UI 复验 |
| R02 | 已有真实浏览器/人工证据，见 `V0-4-4-UX-UI-HANDOFF.md` §9 |
| R08 | ✅ 本轮已在真实页面复验通过（见批次 1），不再重跑 |
| R13 / R14 | 与 D2 / D3 同一件事，已并入**批次 2**，不重复做 |

## 11. 回报格式

每批一条，按 `BROWSER-VERIFICATION-PROMPTS.md` §11：

```
批次：<0–7>
覆盖项：<C1 / D2 / E3 / R05 …>
环境：临时 HOME/WORK_ROOT；端口；frontend_build；浏览器或 App 版本
结论：通过 / 失败 / 未验证
证据：截图文件名，或 Console / Network 原始输出（含计数与时间戳）
失败时：最小复现步骤 + 期望 vs 实际
```

**任何一条没有观察到原始证据的，请写「未验证」并说明卡在哪**——这比写"看起来正常"有用得多。
