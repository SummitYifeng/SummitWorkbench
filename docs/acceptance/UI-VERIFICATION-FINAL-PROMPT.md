# 收尾提示词：剩余 5 项 UI 层验收（整段复制给 Codex）

> **给执行者**：把下面「复制区」整段发给具备 computer use + Chrome DevTools 能力的 agent。
> 它是自包含的，不需要读本仓库其它文档。
>
> 本文只覆盖**上一轮之后仍然未验证**的项。已通过的 10 项（C2 / R08 / D3 / E1 / E2 / R06 / E4 /
> R03 / R10 / R11）**不要重跑**。上一轮的逐项结果见 `OPEN-VERIFICATION-ITEMS.md` §M。

---

## 复制区（从这里开始）

你是真实浏览器验收执行者。任务：在**隔离环境**里跑完下面 7 个任务，逐条回报**原始证据**。

### 铁律（违反则整轮作废）

1. **只用临时环境**：临时 `HOME`、临时 `WORK_ROOT`、临时 vault。**绝不**指向
   `~/Documents/Work/_vault` 或任何真实工作区。
2. **不连真实模型、不连真实飞书**——**唯一例外**是任务 7，且必须先取得明确授权（见该任务）。
3. **没有实际观察到的，一律写「未验证」**，并说明卡在哪。**不要**用「源码里是这样」「看起来正常」
   「应该没问题」代替观察。宁可我拿到 5 个诚实的「未验证」，也不要一个编造的「通过」。
4. **每条断言都要有原始证据**：Network 的**请求计数与时间戳**、Console 原始输出、
   `document.activeElement` 之类的可判定量，或截图文件名。
5. **本批全部是只读或界面层操作。不要点任何写回按钮**（「确认应用（写回）」、「恢复写回」等），
   除非该任务明确要求。

### 环境准备（所有任务共用）

```bash
ISO=$(mktemp -d /tmp/swb-final-XXXXXX)
mkdir -p "$ISO/home" "$ISO/work"
export HOME="$ISO/home"
export WORK_ROOT="$ISO/work"
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/wb web --host 127.0.0.1 --port 18931 &
```

- 首次进页面按向导新建工作区，**模型与飞书都选「跳过」**。
- 记录并回报：`frontend_build`（页面 / `static/build-meta.json`）、端口、浏览器版本。
- 浏览器要求：**原生 Google Chrome**（不是 In-app Browser）。
  上一轮已验证：In-app Browser 看不到下载事件，是通道限制不是产品缺陷。
- 需要 DevTools 协议时用独立实例，避免污染已有 Chrome：
  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 --user-data-dir="$ISO/chrome" \
    "http://127.0.0.1:18931/"
  ```

### 任务 1 · C1：101 条批量操作必须**零请求**

**夹具**：待确认页是纯 Markdown `_vault/review/meetings.md`。**不要**用真实模型生成 100 条候选
（那是 100 次模型调用）——直接写文件。硬性要求：必须有 `type: approval-page` frontmatter，
候选必须挂在 `## 日期 标题  [[笔记]]` 下，字段行恰好缩进两空格。可直接套用：

```markdown
---
date: '2026-09-11'
type: approval-page
status: active
project: global
---

# 会议提取待确认

## 2026-09-11 合成会议  [[meetings/notes/2026-09-11-synthetic]]

- [ ] `id: local:fixture#action-item-1` [action-item] 合成候选正文 1
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

- `wb-original` 的编码：`base64.urlsafe_b64encode(json.dumps({"description":...,"target_project":...,
  "route":...,"due_date":...}, ensure_ascii=False, separators=(",",":")).encode())`。
- 也先建好 `_vault/projects/demo-project.md`，让写回有真实落点。
- 同一页**候选 ID 不得重复**。生成 **101 条**和 **100 条**两份。

**步骤**：打开 DevTools → Network，过滤 `review/batch`，清空。点「批量批准」。

**通过标准**：
- 101 条：出现提示「本次批量操作包含 101 条，超过单批上限 100 条，未执行」，
  **且 `/api/review/batch` 请求数 = 0**（这就是上一轮缺的证据）。
- 100 条：请求数 = 1，成功提示出现。

**回报**：两个规模各自的请求计数原文。

### 任务 2 · D2：来源面板异常矩阵（含修复后复验）

**夹具**（全部在临时 vault 内造）：

| 用途 | 文件 |
|---|---|
| 正常 | `projects/demo-project.md` |
| **非 UTF-8** | `projects/probe.md`，内容为**真的非 UTF-8 字节**：`printf '\x89PNG\r\n\x1a\n\x00\x01\x02\xff\xfe' > _vault/projects/probe.md` |
| 截断 | `projects/big.md`，正文 100,000–262144 字节之间 |
| 413 | `projects/huge.md`，**大于 262144 字节** |
| 路径穿越 | 请求 `../../etc/passwd` 一类路径 |
| 软链越界 | `ln -s /etc/hosts _vault/projects/escape.md` |
| 非知识目录 | `_signals/`、`notes/` 下的文件 |
| 缺失 | `projects/missing.md`（不创建） |
| workspace 隔离 | 另建**第二个** workspace，放**同名但内容不同**的文件 |

**注意**：来源面板调 `/api/sources/read`，它会把非 `.md` 的来源 id 后缀改写成 `.md`。
所以造 `probe.bin` 只会得到 404——**要触发解码路径，文件必须真的叫 `.md`**。

**步骤**：从审批候选的「来源」入口逐个打开，**每个用例同时记录 HTTP 状态码**与界面文案。

**通过标准**：
- **非 UTF-8 → 415 + 明确文案**（如「来源不是可读取的 Markdown 笔记」）。
  **不得**出现 `[internal_error]`。上一轮这里是 500，已修复，本轮就是复验修复。
- 截断 → 出现「正文已截断」，`document.querySelector('pre.source-reader').textContent.length === 100000`。
- 413 / 路径穿越 / 软链越界 / 非知识目录 / 缺失 → 明确文案 + 状态码（预期 413 / 400 / 400 / 400 / 404）。
- 第二个 workspace 的同名文件必须读到**第二个**的内容。

**回报**：每个用例一行：文件 → HTTP 状态码 → 界面文案。

### 任务 3 · E3：**项目列表**滚动位置恢复

**先读这段，别重复上一轮的错**：`showProjectView()` 在进入详情时**显式**
`window.scrollTo({top: 0})`——**详情总是从顶部开始**。它保存并还原的是**打开详情之前列表页**的
滚动位置。上一轮验的是"重新进入详情后期望停在原处"，得到 `1359 → 0` 就报了失败，
那是**测错了对象**（归零是设计如此）。E3 要验的是下面这个。

**夹具**：让**项目列表**高于视口——在临时 vault 建 30–40 个 `projects/<name>.md`（`type: project-main`）。

**步骤与通过标准**：
1. 停在项目列表，先自证夹具有效：`document.body.scrollHeight > window.innerHeight`。不满足就加项目。
2. 向下滚到中部，记录 `Y1 = window.scrollY`（要求 `Y1 > 0`）。
3. 点开任意项目详情 → 记录 `scrollY`（**预期 0，这是通过项**）。
4. 点「返回」回到列表 → **`window.scrollY` 应恢复到 `Y1`**；查询框内容与状态筛选值保留。
5. 回报实测的 `Y1` 与返回后的值。

### 任务 4 · R01 / R04 / R09：制造**乱序响应**

这三条都要让**旧的响应晚于新的响应**返回。用 CDP 把**第一个**匹配请求扣住，其余立即放行。
把下面脚本存成 `delay-first.mjs`（Node 22+ 自带 `WebSocket`，无需依赖）：

```js
// 用法: node delay-first.mjs <cdpPort> <url子串> <延迟毫秒>
const [, , port = '9222', pattern = '', delayMs = '5000'] = process.argv;
const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) throw new Error('没有找到 page target');

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0, seen = 0;
const pending = new Map();
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const n = ++id;
    pending.set(n, { res, rej });
    ws.send(JSON.stringify({ id: n, method, params }));
  });

ws.addEventListener('message', async (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { res, rej } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
    return;
  }
  if (msg.method !== 'Fetch.requestPaused') return;
  const { requestId, request } = msg.params;
  if (!request.url.includes(pattern)) return void send('Fetch.continueRequest', { requestId });
  const n = ++seen;
  const wait = n === 1 ? Number(delayMs) : 0;
  console.log(`[${new Date().toISOString()}] #${n} 到达 ${request.url} → 扣住 ${wait}ms`);
  if (wait) await new Promise((r) => setTimeout(r, wait));
  console.log(`[${new Date().toISOString()}] #${n} 放行`);
  await send('Fetch.continueRequest', { requestId });
});

ws.addEventListener('open', async () => {
  await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  console.log(`拦截已启用 pattern=${pattern}，首个延迟 ${delayMs}ms。Ctrl-C 结束。`);
});
```

**R09 · 外部写回列表不被旧响应覆盖**
1. 开拦截：`node delay-first.mjs 9222 /api/external-actions 6000`。
2. 进审批页 → 6 秒内手动再触发一次外部写回列表刷新（切走再切回审批页）。
3. **通过标准**：最终列表展示的是**较新**那次的数据；旧响应到达后**不得**覆盖它。
   回报两次请求的时间戳与最终列表内容。

**R04 · 设置页保存后不被旧读取覆盖**
1. 开拦截：`node delay-first.mjs 9222 /api/settings/profiles 6000`。
2. 打开设置页（触发被扣住的读取）→ 立即保存一次模型/provider 设置 → 等被扣住的读取放行。
3. **通过标准**：界面仍是**保存后**的状态，不被保存前发出的旧读取覆盖。
   回报：写入请求与两次读取的时间戳、保存后界面显示的 provider 值。

**R01 · 项目详情不被过期响应推回**
1. 开拦截：`node delay-first.mjs 9222 /api/projects/view 6000`。
2. 快速连续点开项目 A、再点开项目 B（或点开后立刻返回）。
3. **通过标准**：最终页面显示的是**最后点开**的那个项目；A 的迟到响应**不得**把 A 的详情推回
   页面，也不得抢走焦点。回报：两次请求时间戳、最终显示的项目名、`document.activeElement`。

**如果 `Fetch.enable` 拦不到**（例如页面在另一个 Chrome 实例里）：如实报告，改用你能给出的
最接近的确定性手段，并说明它**不能**证明乱序——不要因此写「通过」。

### 任务 5 · R05：隐藏页 60 秒暂停 + 回到前台立即补一次

**背景**（供你判断，不必照抄）：代码里 `/api/version` 与 `/api/sync/status` 各有一个 60 秒
`setInterval`，进入回调先判 `document.visibilityState !== 'visible'` 就 `return`；
`visibilitychange` 回到可见时**立即**各补一次。

**步骤**：
1. 打开 DevTools → Network，**不要**清空，保持记录。记下开始时 `/api/version` 与
   `/api/sync/status` 的计数。
2. 切到另一个标签页（或最小化），让本页**隐藏 ≥ 130 秒**。记录隐藏期间的起止时间戳。
3. 切回。

**通过标准**：
- 隐藏期间：`/api/version` 与 `/api/sync/status` **均无新增请求**。
- 切回后**立即**各出现**恰好一次**（时间戳紧贴切回时刻）。

**诚实要求**：Chrome 本身会**节流后台标签页的定时器**，所以"隐藏期间无请求"可能被浏览器节流
一并满足。请在回报里**明确说明**你观察到的是"代码的可见性守卫生效"还是"可能只是浏览器节流"——
如果无法区分，就写「无法区分」。**不要把无法区分写成通过。**

### 任务 6 · R07：`/api/version` 省略 `workspace_id` 时问答历史仍载入一次

**关键**：不需要伪造响应。服务端在 `workspace_id` 为 `None` 时**本来就会省略该字段**——
用**空安装/无 active profile** 的模式启动即可自然触发（临时 `HOME` 下不建 profile）。

**步骤**：
1. 启动服务后先确认 `/api/version` 的响应**确实没有 `workspace_id` 字段**
   （Network → 该请求 → Response，把原文贴出来）。
2. 在第二大脑（问答）页签制造可观察状态：新建 1–2 个会话，确认计数显示形如 `2/10`。
3. 刷新页面。
4. **通过标准**：会话列表仍然载入（计数仍为 `2/10`，不是 `0/10`），
   **且没有出现"列表被清空"**。
5. 再触发一次 `/api/version`（切到别的标签页再切回，或等 60 秒轮询），
   **通过标准**：仍然**不重复载入、不清空**。
6. 若条件允许，再让 `/api/version` 带上真实 `workspace_id`（例如在有 profile 的模式下跑），
   观察此时的行为并**如实记录**——工作区变化时重置是预期的，不要记为缺陷。

### 任务 7 · C4：「新建会议（个人日程）」落点 —— **需要授权，否则跳过**

这一项会**在真实飞书日历里创建事件**。因此：

- **只有在用户明确授权、并提供了可用凭据/环境时才做**。
- 若没有明确授权：**跳过**，回报「未验证：无飞书授权」，**不要**尝试。
- 若获得授权：
  1. 在**隔离 workspace** 里造一条落点为 `feishu-meeting` 的候选
     （`route: feishu-meeting`，带 `start_at` / `end_at`，注意 time 为本地 naive `YYYY-MM-DDTHH:MM`）。
  2. 在真实页面上确认该候选**可选中、可批准**（这是本项要验的资格逻辑）。
  3. 如被要求执行写回：只创建一个事件，**回读校验后立即删除**，并回报事件的 id 与删除结果。
  4. **不要**留下任何真实对象。

### 回报格式（每个任务一段）

```
任务：<编号与覆盖项>
环境：临时 HOME/WORK_ROOT 路径；端口；frontend_build；浏览器或 App 版本
结论：通过 / 失败 / 未验证
证据：Network 请求计数与时间戳原文 / Console 原文 / activeElement 值 / 截图文件名
失败或未验证时：最小复现步骤 + 期望 vs 实际 + 卡在哪
```

最后给一张汇总表：任务 → 结论 → 一句话依据。

## 复制区结束

---

## 附：这份提示词对应的开放项

| 任务 | 覆盖 | 上一轮状态 |
|---|---|---|
| 1 | C1 | 101 条拦截文案已观察到，缺 Network 计数 |
| 2 | D2 | 非 UTF-8 曾 500，已修复，待复验；其余用例缺 HTTP 状态码 |
| 3 | E3 | 上轮配方写错，本轮更正为列表滚动 |
| 4 | R01 / R04 / R09 | 均未制造乱序 |
| 5 | R05 | 未取得隐藏页 > 60 秒的时间戳证据 |
| 6 | R07 | 未取得省略/带 `workspace_id` 的请求计数 |
| 7 | C4 | 「新建会议（个人日程）」需飞书 |

跑完后把结果按上面的格式发回，我会据此更新 `OPEN-VERIFICATION-ITEMS.md`。
