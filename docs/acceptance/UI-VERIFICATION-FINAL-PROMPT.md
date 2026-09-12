# 收尾提示词 v6：剩余 3 项 UI 层验收（整段复制给 Codex）

> **v6 变更**
> - ✅ **R05 已通过**（`after.version - base.version = 1`、`sync` 同为 +1、`tick=14`）——**不要重跑**。
> - 🔧 **B4 的「卡在启动页」根因已查明，并给了修法（已实测）**：App 用 `NSHomeDirectory()`
>   找 runtime 记录，而服务用 `$HOME` 写 → 设了 `HOME` 之后两边**对不上**，端口永远拿不到，
>   于是 `readiness_timeout` 循环。**补一个 `WB_RUNTIME_RECORD` 即可**。见任务 3。
>   另外：真实日志在 **`~/Library/Logs/summitworkbench-panel.log`（是文件，不是目录）**，
>   上一轮找错了位置。
> - 🔧 **R09 的判据改成「放行 #1 之后再读一次列表」**：上一轮拿到了放行**前**的 2 条，
>   但没人记录放行**后**的状态；脚本汇总行又没打出来。现在汇总行在正常/Ctrl-C/异常退出时
>   都会打印，且第 6 步明确要求放行后再读一次。
> - 环境准备里新增 `ISO`/`WORK_ROOT` 非空断言（上一轮有临时脚本因路径变量取空而把夹具
>   种进了仓库目录）。
> - **只有 C4 需要账号所有者介入。**

---

## 复制区（从这里开始）

你是真实浏览器验收执行者。在**隔离环境**里跑完下面 4 个任务，逐条回报**原始证据**。

### 铁律

1. **只用临时环境**：临时 `HOME`、`WORK_ROOT`、vault。**绝不**指向真实工作区。
2. **不连真实模型、不连真实飞书**——唯一例外是任务 4（C4），必须先取得明确授权。
3. **没有实际观察到的，一律写「未验证」**并说明卡在哪。
4. **每条断言要有原始证据**：计数、时间戳、响应原文、界面文案等可判定量。
5. **不要点「确认应用（写回）」「恢复写回」**。点「批准/拒绝」只改标记、不写回，是允许的。

### 环境准备

```bash
ISO=$(mktemp -d /tmp/swb-v5-XXXXXX)
mkdir -p "$ISO/home" "$ISO/work"
export HOME="$ISO/home" WORK_ROOT="$ISO/work"
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/wb web --host 127.0.0.1 --port 18931 &
```

**每段脚本开头先做这个断言**（防止变量为空时把文件写到仓库里）：

```bash
: "${ISO:?ISO 未设置，请先执行上面的 mktemp}"
: "${WORK_ROOT:?WORK_ROOT 未设置}"
```

> **⚠ 一个真实踩过的坑**：不要在**跨命令**时用 `$(cat /tmp/xxx 2>&1)` 这类方式传递临时路径。
> 若那个文件不存在，`2>&1` 会把 `cat` 的**报错文本**当成路径值，而脚本里的 `Path(...)` 又是
> **相对路径**，于是整棵临时夹具树会被种进**仓库目录**（曾经真的发生过，导致 `ruff check .`
> 扫描到垃圾文件而失败）。**每个 shell 调用都是独立的**——要么在每个块里重新 `export`，
> 要么把临时根路径显式写死成字面量。

按向导新建工作区，**模型与飞书都选「跳过」**。回报 `frontend_build`、端口、Chrome 版本。

需要 DevTools 协议时（**必须带 `--password-store=basic --use-mock-keychain`**，理由见下）：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9333 --user-data-dir="$ISO/chrome" \
  --password-store=basic --use-mock-keychain \
  --no-first-run --no-default-browser-check "http://127.0.0.1:18931/" &
sleep 5
curl -s http://127.0.0.1:9333/json/list | grep -c '"type": "page"'   # 必须 ≥ 1
```

`0` 或空数组就**先停下报告**，不要继续任务 1。

> **为什么必须加这两个开关**：以一次性 `--user-data-dir` 启动的 Chrome 默认会去读写**系统登录
> 钥匙串**，可能弹出钥匙串授权 / 默认钥匙串弹窗。这类弹窗是**模态**的，会阻塞钥匙串访问——
> 而应用的凭据读写（例如 C4 的飞书令牌）正好走钥匙串，于是可能**因为一个弹窗而卡住**，
> 让失败看起来像产品缺陷。`--password-store=basic` 让 Chrome 改用本地文件存密码、
> **完全不碰系统钥匙串**；`--use-mock-keychain` 进一步避免钥匙串交互。
> 这两个开关**不影响 CDP**，已实测（加了之后 `page_count` 仍为 1，拦截脚本可用）。
>
> **若运行前/运行中看到钥匙串弹窗**：先**取消 / 不允许**（这个 profile 是一次性的，不需要钥匙串），
> 确认弹窗消失后再继续。**不要把弹窗留在屏幕上就开始验证**，否则结果不可信。

### 公共脚本 · 闸门式扣留（任务 1 用）

存成 `gate.mjs`。它自己查找/新建 page target、导航到应用、在导航**之前**启用拦截，
把**第一个**匹配请求一直扣住直到 gate 文件出现，其余立即放行。
**被扣住的请求若被页面取消，它会明确告警**——那种情况本次不成立，需要重来。

```js
// 用法: node gate.mjs <cdpPort> <appUrl> <url子串> <gateFile>
import { existsSync } from 'node:fs';
const [, , port = '9333', appUrl = '', pattern = '', gateFile = ''] = process.argv;
const base = `http://127.0.0.1:${port}`;
const listTargets = async () => (await (await fetch(`${base}/json/list`)).json());

async function ensurePage() {
  let list = await listTargets();
  let page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) {
    console.log('· 没有 page target，尝试 PUT /json/new 建一个…');
    await fetch(`${base}/json/new?url=${encodeURIComponent(appUrl)}`, { method: 'PUT' });
    for (let i = 0; i < 24; i++) {
      await new Promise((r) => setTimeout(r, 500));
      list = await listTargets();
      page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) break;
    }
  }
  if (!page) throw new Error(`${base}/json/list 始终没有 page target。原始返回：${JSON.stringify(list)}`);
  return page;
}

const page = await ensurePage();
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0, seen = 0, cancelled = 0;
const pending = new Map();
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const n = ++id;
    pending.set(n, { res, rej });
    ws.send(JSON.stringify({ id: n, method, params }));
  });

const waitForGate = async () => {
  console.log(`      … 等待放行闸门：touch ${gateFile}`);
  for (;;) {
    if (existsSync(gateFile)) return;
    await new Promise((r) => setTimeout(r, 200));
  }
};

const release = async (requestId, label) => {
  try {
    await send('Fetch.continueRequest', { requestId });
    return true;
  } catch (err) {
    cancelled += 1;
    console.log(`⚠ ${label} 放行失败：${err.message}`);
    console.log('⚠ 这通常意味着页面刷新/导航，把被扣住的请求取消了。');
    console.log('⚠ 本次乱序【不成立】，请重来：过程中不要刷新、不要离开审批页签。');
    return false;
  }
};

// 汇总行必须「一定」出现：正常结束、Ctrl-C、异常退出都会打印。
const summary = () => console.log(`\n=== 汇总：拦截 ${seen} 次，放行失败 ${cancelled} 次（0 = 乱序成立）===`);
process.on('exit', summary);
process.on('SIGINT', () => { summary(); process.exit(0); });
process.on('uncaughtException', (err) => { console.log(`异常：${err.message}`); summary(); process.exit(1); });

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
  if (n === 1) {
    console.log(`[${new Date().toISOString()}] #1 到达 ${request.url} → 扣住（等你 touch 闸门）`);
    await waitForGate();
    console.log(`[${new Date().toISOString()}] #1 收到闸门 → 放行`);
    await release(requestId, '#1');
    summary();
  } else {
    console.log(`[${new Date().toISOString()}] #${n} 到达 ${request.url} → 立即放行`);
    await release(requestId, `#${n}`);
  }
});

await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
await send('Page.enable');
await send('Page.navigate', { url: appUrl });
console.log(`已连接 ${base} 并导航到 ${appUrl}；pattern=${pattern}。#1 扣住直到 ${gateFile} 出现。`);
```

> **已实测**：#1 被扣住期间后续请求正常通行；`touch` 闸门后 #1 才放行。

---

### 任务 1 · R09：外部写回列表不被旧响应覆盖 —— **页内触发，不要切页签**

`/api/external-actions` 读本地账本 `_vault/_signals/external-actions/log.jsonl`，**不需要飞书**。

**上一轮为什么没成**：`#2` 确实先到达并渲染了 2 条，但放行 `#1` 时报
`Invalid InterceptionId` —— **被扣住的旧请求已被页面取消**（很可能因为切了页签/刷新），
所以"旧响应返回后仍保持 2 条"这一步**没有真正发生**。你的判断是对的。

**这次改为页内触发**：点候选上的**「批准」**会走 `decide/batchDecide` → `refreshReview()`
→ `refreshExternalActions()`，**不离开页面**，旧请求不会被取消。
（注意：dry-run 的「检查并写回」**不会**触发 `refreshReview`，别用它。）

**夹具**：审批页上至少要有 1 条候选。用已验证的格式（frontmatter + `## 日期 标题  [[笔记]]`
+ 两空格缩进字段）：

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

写入 `_vault/review/meetings.md`，并建好 `_vault/projects/demo-project.md`。

**账本**：

```bash
WS=$(python3 -c "import json;print(json.load(open('$WORK_ROOT/_vault/.summit-workbench/workspace.json'))['workspace_id'])")
mkdir -p "$WORK_ROOT/_vault/_signals/external-actions"
cat > "$WORK_ROOT/_vault/_signals/external-actions/log.jsonl" <<EOF
{"schema_version":1,"operation_id":"race-op-1","candidate_id":"local:fixture#action-item-1","workspace_id":"$WS","kind":"feishu-task","request_fingerprint":"fp-1","target_account_ref":"test","state":"failed","attempt":1,"timestamp":"2026-09-11T13:00:00+08:00","remote_id":null,"error":"合成数据：旧的一条","retry_allowed":true}
EOF
```

`kind` 只能是 `feishu-task` / `feishu-meeting`；`state` 只能是 `prepared` / `sending` /
`succeeded` / `failed` / `unknown` / `reconciled-succeeded` / `reconciled-not-found`。
**`workspace_id` 必须与 `$WS` 一致**，否则会被过滤掉。

**步骤**：

1. 启动闸门脚本：
   ```bash
   node gate.mjs 9333 http://127.0.0.1:18931/ /api/external-actions "$ISO/gate-r09"
   ```
2. **进审批页签**（之后不要再来回切换）→ 触发读取 **#1**（账本此时 1 条），被扣住。
   确认脚本打印 `#1 到达 … 扣住`。
3. **在被扣住期间**，追加第二条：
   ```bash
   cat >> "$WORK_ROOT/_vault/_signals/external-actions/log.jsonl" <<EOF
   {"schema_version":1,"operation_id":"race-op-2","candidate_id":"local:fixture#action-item-2","workspace_id":"$WS","kind":"feishu-meeting","request_fingerprint":"fp-2","target_account_ref":"test","state":"failed","attempt":1,"timestamp":"2026-09-11T13:05:00+08:00","remote_id":null,"error":"合成数据：新的一条","retry_allowed":true}
   EOF
   ```
4. **就在审批页上点候选的「批准」**（只改标记，不写回）→ 触发读取 **#2**，立即放行，
   页面显示 **2 条**。确认脚本打印 `#2 到达 … 立即放行`。
   **记录此刻列表里的两条文案**（记为「放行前状态」）。
5. **`touch "$ISO/gate-r09"`** → 扣住的 #1（只有 1 条）此刻才放行。
6. **稍等 2–3 秒（等旧响应真正被页面收下并重绘），再读一次列表。**
7. **通过标准（这才是真正的断言）**：**放行 #1 之后**列表**仍然是 2 条**
   （与第 4 步的「放行前状态」逐字一致）。若变成 1 条 → 守卫失效（**真失败**）。
8. 脚本结束时会打印 `=== 汇总：拦截 N 次，放行失败 M 次 ===`。
   **M 必须是 0**；若 M ≥ 1，说明 #1 被页面取消、**旧响应根本没返回**，本次**不成立** →
   如实报「未验证」，不要拿第 4 步的状态当结论。

**回报**：脚本全部输出（含时间戳与末尾汇总行）；**第 4 步与第 7 步两次列表的原文**（这是关键）。

> 上一轮之所以只能判「未验证」：第 4 步的状态拿到了，但**没人记录第 7 步**（放行后的状态），
> 而脚本汇总行又没打出来。这一轮把「放行后再读一次」明确成第 6 步，并把汇总行改成
> 正常退出 / Ctrl-C / 异常退出都会打印。

### 任务 2 · R05：隐藏页暂停 + 回到前台补一次 —— **不用真的切走浏览器**

**不要再真的隐藏 130 秒**：把 `visibilityState` 做成可控的，并派发 `visibilitychange`
事件。页面在浏览器看来一直可见，所以**定时器不会被节流**——这就彻底消除了
"分不清守卫与节流"的歧义。

在页面 Console 里：

```js
// ① 让 visibilityState 可控
window.__hidden = false;
Object.defineProperty(document, 'visibilityState', {
  configurable: true,
  get: () => (window.__hidden ? 'hidden' : 'visible'),
});

// ② 计数 + 5 秒探针（探针用来证明定时器确实在跑）
performance.setResourceTimingBufferSize(1000);
const count = (p) => performance.getEntriesByType('resource').filter((e) => e.name.includes(p)).length;
window.__tick = 0;
window.__probe = setInterval(() => { window.__tick++; }, 5000);
window.__base = { version: count('/api/version'), sync: count('/api/sync/status'), at: new Date().toISOString() };
window.__base;

// ③ 进入"隐藏"
window.__hidden = true;
window.__hiddenAt = new Date().toISOString();
```

**等 ≥ 70 秒**（应用轮询间隔是 60 秒，需要它至少触发一次）。然后：

```js
// ④ 回到可见并派发事件
window.__hidden = false;
document.dispatchEvent(new Event('visibilitychange'));
await new Promise((r) => setTimeout(r, 1500));   // 给请求落账
({
  after: { version: count('/api/version'), sync: count('/api/sync/status') },
  tick: window.__tick, base: window.__base, hiddenAt: window.__hiddenAt,
  at: new Date().toISOString(),
});
clearInterval(window.__probe);
```

**通过标准**：
- `after.version - base.version === 1` **且** `after.sync - base.sync === 1`。
- `tick >= 12`（70 秒 ÷ 5 秒）→ **证明定时器确实在运行且未被节流**，因此隐藏期间
  "没有发出请求"就是**可见性守卫生效**，而非浏览器节流。

**若 `after` 比 `base` 多 2**：把两个请求的时间戳一并贴回来（可能是应用自身的 60 秒轮询
恰好在切回时触发），由我判断，**不要**自行判通过。

**回报**：③ 和 ④ 的原始对象（含 `tick` 与时间戳）。

### 任务 3 · B4：原生 App 黑盒 —— **必须补一个 `WB_RUNTIME_RECORD`**

**上一轮为什么卡在「正在启动…」——根因已查明（不是产品缺陷）**

App 判断服务"就绪"的方式是：用子进程 PID 去读一份 **runtime 记录**，从里面拿端口，再探测。

- 原生侧 `RuntimeRecord.swift:24` 从 **`NSHomeDirectory()`** 取路径
  → `<真实家目录>/Library/Application Support/SummitWorkbench/runtime.json`
  （`NSHomeDirectory()` **不认 `$HOME`**）。
- 服务侧 `server_entry.py:149-153` 用
  `active_workspace.runtime_dir or active_workspace.application_support`
  → 这条链来自 **`Path.home()`（认 `$HOME`）**。

于是设了 `HOME=<临时>` 之后：**服务把记录写进临时家目录，App 去真实家目录找** → 永远找不到
端口 → 探测一直失败 → `readiness_timeout`，每 13 秒重启一次，指数退避，UI 永久停在启动页。
真实日志（**这是文件，不是目录**）里能看到这个循环：

```
~/Library/Logs/summitworkbench-panel.log
```

> **顺带纠正上一轮的排查方向**：日志在这个**文件**里，不在
> `~/Library/Logs/SummitWorkbench/` 目录下。上一轮说"两个日志目录都没有输出"，
> 其实是**找错了位置**。

**修法：显式指定 `WB_RUNTIME_RECORD`**，让服务把记录写到 App 会去找的那个路径。
服务端支持这个环境变量（`server_entry.py:88`），且**子进程会继承 App 的环境**
（`ServiceSupervisor.swift:151` 用 `ProcessInfo.processInfo.environment`），所以从启动命令传入即可。

**启动前的强制前置检查**（写记录会落到**真实** app-support 目录，必须确认不冲突）：

```bash
pgrep -f "SummitWorkbenchServer" && echo "⚠ 有服务在跑，先退出" || echo "✅ 无服务在跑"
ls "$HOME/Library/Application Support/SummitWorkbench/runtime.json" 2>/dev/null \
  && echo "⚠ 已存在 runtime.json，先退出真实 App" || echo "✅ 无 runtime.json"
```

**启动方式**：

```bash
ISO2=$(mktemp -d /tmp/swb-app-XXXXXX)
mkdir -p "$ISO2/home/Library/Application Support" "$ISO2/work"
REAL_RECORD="$HOME/Library/Application Support/SummitWorkbench/runtime.json"
HOME="$ISO2/home" WORK_ROOT="$ISO2/work" WB_RUNTIME_RECORD="$REAL_RECORD" \
  /Applications/SummitWorkbench.app/Contents/MacOS/SummitWorkbench
```

> 这个做法**已实测**：打包服务会把记录写到 `$REAL_RECORD`，临时 `HOME` 下**不写任何东西**，
> 且记录里 `workspace_id: null`（证明确实是空安装、没有指向真实工作区）。

**判据仍是界面**：App 应能真正加载完成（不再停在「正在启动…」）。打开设置页看工作区。

- ✅ **通过**：显示 onboarding / 空工作区，**不出现** `/Users/<真实用户>/Documents/Work/_vault`
  → 隔离成立，继续下面的黑盒检查。
- ❌ **失败**：仍停在「正在启动…」→ 先看
  `~/Library/Logs/summitworkbench-panel.log` 的最新几行：
  `service_ready` 才算就绪；若是 `service_exited reason="readiness_timeout"`，
  说明记录没对上，把日志贴回来。
- ❌ 若设置页确实显示了真实 vault 路径 → 隔离不成立，**立即退出**并贴回文案。

**收尾（必做）**：退出 App 后确认 `$REAL_RECORD` 已被清理（服务正常退出会 unlink）；
若残留则删掉，并**核对它本来就不存在**。再删除 `$ISO2`。

隔离成立后：确认设置页显示的 build identity 与实际产物一致；走一遍新建工作台（指向
`$ISO2/work`）；跑六页签可达性；确认操作发生在 **WKWebView** 内；退出重启确认不出现
crash loop、不误认旧服务。

**回报**：两个前置检查的输出；启动命令原文；设置页工作区文案原文；六页签结果；重启结果；
收尾后 `$REAL_RECORD` 的状态。

### 任务 4 · C4：「新建会议（个人日程）」落点 —— **需要账号所有者介入**

会在**真实飞书日历建事件**：

- **到这一步就停下来，向账号所有者请求授权**，不要自行尝试。
- 未获授权 → 回报「未验证：无飞书授权」。
- **开始前先确认屏幕上没有钥匙串弹窗**：飞书令牌是从**登录钥匙串**读的
  （`com.summitworkbench.credentials.<workspace_id>` / `feishu:<app_id>:refresh_token`），
  一个模态弹窗就能让读取阻塞，从而产出一个**与产品无关的失败**。若出现弹窗，先处理掉再继续。
- 获授权后：在隔离 workspace 造一条 `route: feishu-meeting` 的候选（带 `start_at`/`end_at`，
  本地 naive `YYYY-MM-DDTHH:MM`），确认它在真实页面上**可选中、可批准**；
  若被要求写回，只建一个事件，**回读校验后立即删除**，回报事件 id 与删除结果，**不留残留**。

### 回报格式

```
任务：<编号与覆盖项>
环境：临时 HOME/WORK_ROOT；端口；frontend_build；Chrome 版本
结论：通过 / 失败 / 未验证
证据：计数、时间戳、响应原文、界面文案等**原始值**
失败或未验证时：最小复现步骤 + 期望 vs 实际 + 卡在哪
```

最后给汇总表：任务 → 结论 → 一句话依据。

## 复制区结束

---

## 附：状态

| 任务 | 覆盖 | 上一轮 | 本轮变化 |
|---|---|---|---|
| 1 | R09 | 未验证（只缺"放行后"的状态） | 判据改为**放行 #1 后再读一次**；汇总行改为任何退出方式都会打印 |
| 2 | R05 | ✅ **已通过** | 不必重跑 |
| 3 | B4 | 未验证（卡在启动页） | **补 `WB_RUNTIME_RECORD`**（已实测）；日志位置也纠正了 |
| 4 | C4 | 未验证 | 需授权，**唯一需要账号所有者的一项** |

**建议顺序：3 → 1 → 4。** 前两项都不需要账号所有者介入。

**已关闭，不要重跑**：C1、C2、R01、R03、R04、R05、R06、R07、R08、R10、R11、D2、D3、E1、E2、E3、E4。
