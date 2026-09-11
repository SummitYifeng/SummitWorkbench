# 收尾提示词 v5：剩余 4 项 UI 层验收（整段复制给 Codex）

> **v5 变更**
> - ✅ **R04 已通过**（放行 #1 后页面仍显示 `work 【已更新】`），**不要重跑**。
> - ❌ **B4 上一轮的结论"原生服务未隔离"很可能是误判**：你看到的
>   `--work-root /Users/…/Documents/Work` 是**原生层传的参数**，而打包服务
>   `server_entry.py` 第 112 行是 `resolve_active_workspace(allow_env_fallback=False)` ——
>   **它根本不消费 `--work-root`**。判断是否隔离要看**界面显示的工作区**，不是进程参数。
>   而且**要同时设 `WORK_ROOT`**：原生层 `Models.swift:124` 就是
>   `environment["WORK_ROOT"] ?? (NSHomeDirectory() + "/Documents/Work")`。
> - 🔧 **R09 的触发方式换了**：切页签可能让被扣住的请求被取消（你遇到的
>   `Invalid InterceptionId`）。改为在**审批页内点「批准」**触发第二次读取 ——
>   `decide/batchDecide` 会调 `refreshReview()` → `refreshExternalActions()`，
>   **不离开页面**（注意：dry-run 的「检查并写回」**不会**触发，别用它）。
> - 🔧 **R05 不再需要真的切走浏览器**：用 `visibilityState` 覆盖 + 派发 `visibilitychange`
>   事件，并用 5 秒探针**证明定时器未被节流**，从而彻底消除"无法区分"的歧义。
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
    console.log(`\n取消计数：${cancelled}（0 = 乱序成立）`);
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
5. **`touch "$ISO/gate-r09"`** → 扣住的 #1（只有 1 条）此刻才放行。
6. **通过标准**：外部写回列表**仍然是 2 条**。若被覆盖回 1 条 → 守卫失效（**真失败**）。
7. 看脚本打印的**取消计数：必须是 0**。若是 1，说明 #1 又被取消了，本次**不成立**，
   如实报「未验证」并附脚本输出。

**回报**：脚本全部输出（含时间戳与取消计数）；第 4 步与第 6 步列表里实际显示的条数与文案。

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

### 任务 3 · B4：原生 App 黑盒 —— **要同时设 `WORK_ROOT`，并按界面判断隔离**

**上一轮的结论很可能是误判，先读这段**：

- 你看到进程参数是 `--work-root /Users/…/Documents/Work`，据此判断"未隔离"。
  但打包服务 `server_entry.py` 第 112 行是
  `active_workspace = resolve_active_workspace(allow_env_fallback=False)` ——
  **它根本不消费 `--work-root`，而是从 profile registry 解析**。
  所以那个参数是**原生层传下来的、服务端会忽略**的，**不能作为隔离与否的判据**。
- 而原生层**确实读环境变量**：`Models.swift:124`
  `let workRoot = environment["WORK_ROOT"] ?? (NSHomeDirectory() + "/Documents/Work")`。
  **上一轮只设了 `HOME`、没设 `WORK_ROOT`**，所以它回退到了真实家目录。

**正确启动方式（两个都设）**：

```bash
ISO2=$(mktemp -d /tmp/swb-app-XXXXXX)
mkdir -p "$ISO2/home/Library/Application Support" "$ISO2/work"
HOME="$ISO2/home" WORK_ROOT="$ISO2/work" \
  /Applications/SummitWorkbench.app/Contents/MacOS/SummitWorkbench
```

**判据是界面，不是进程参数**：等 App 加载完成（不要停在「正在启动…」），打开设置页看工作区。

- ✅ **通过**：显示 onboarding / 空工作区，**不出现** `/Users/<真实用户>/Documents/Work/_vault`
  → 隔离成立，继续下面的黑盒检查。
- ❌ **失败**：确实显示了真实 vault 路径 → 隔离不成立，**立即退出**，把设置页文案原文贴回来，
  作为 B4 的**阻塞结论**。
- ⚠ 若 App 停在「正在启动 SummitWorkbench…」超过 60 秒：贴回原生层日志
  （`$ISO2/home/Library/Logs/SummitWorkbench/` 与真实 `~/Library/Logs/SummitWorkbench/`
  里最新的一份），并报「未验证：App 未能启动」。

隔离成立后：确认设置页显示的 build identity 与实际产物一致；走一遍新建工作台（指向
`$ISO2/work`）；跑六页签可达性；确认操作发生在 **WKWebView** 内；退出重启确认不出现
crash loop、不误认旧服务；结束后删除 `$ISO2`。

**回报**：启动命令原文；设置页工作区文案原文；六页签结果；重启结果。

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
| 1 | R09 | 未验证（旧请求被取消） | 改**页内「批准」**触发，脚本会报取消计数 |
| 2 | R05 | 未验证（三轮都没做成） | 改 `visibilityState` 覆盖 + 5 秒探针，不用真隐藏 |
| 3 | B4 | 未验证（判断依据有误） | 同时设 `WORK_ROOT`，**按界面判断** |
| 4 | C4 | 未验证 | 需授权，**唯一需要账号所有者的一项** |

**建议顺序：2 → 1 → 3 → 4。** 前三项都不需要账号所有者介入。

**已关闭，不要重跑**：C1、C2、R01、R03、R04、R06、R07、R08、R10、R11、D2、D3、E1、E2、E3、E4。
