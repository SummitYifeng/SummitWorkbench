# 收尾提示词 v3：剩余 6 项 UI 层验收（整段复制给 Codex）

> **v3 变更**
> - ✅ **已关闭，不要重跑**：C1、E3（`Y1=1814` / 详情 `0` / `Y2=1814`）、R01（乱序成立，最终显示最后点开的项目）。
> - ❌ **R07 上一轮判「失败」是误判**：`0/10` 正是修复生效的样子。**是我的通过标准写错了**，
>   正确判据见任务 1。好消息是修复本身已被源码契约测试锁住。
> - 🔑 **R04 / R09 不需要任何真实凭据**。上一版让执行者去要模型密钥/飞书，那是我的错——
>   R04 用**假密钥**即可（保存路径不校验），R09 直接**造本地 outbox 行**即可。
>   **只有 C4 真的需要飞书授权。**
>
> 逐项结果见 `OPEN-VERIFICATION-ITEMS.md` §M。

---

## 复制区（从这里开始）

你是真实浏览器验收执行者。在**隔离环境**里跑完下面 6 个任务，逐条回报**原始证据**。

### 铁律

1. **只用临时环境**：临时 `HOME`、`WORK_ROOT`、vault。**绝不**指向真实工作区。
2. **不要连真实模型、不要连真实飞书**——唯一例外是任务 6（C4），且必须先取得明确授权。
   任务 2 用**假密钥**、任务 3 用**本地造的数据**，都不会产生任何外部副作用。
3. **没有实际观察到的，一律写「未验证」**并说明卡在哪。上一轮你把 R05 判未验证是对的。
4. **每条断言要有原始证据**：计数、时间戳、响应原文、界面文案等可判定量。
5. **不要点任何写回按钮**，除非任务明确要求。

### 环境准备

```bash
ISO=$(mktemp -d /tmp/swb-v3-XXXXXX)
mkdir -p "$ISO/home" "$ISO/work"
export HOME="$ISO/home" WORK_ROOT="$ISO/work"
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/wb web --host 127.0.0.1 --port 18931 &
```

按向导新建工作区，**模型与飞书都选「跳过」**。回报 `frontend_build`、端口、Chrome 版本。

需要 DevTools 协议时：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9333 --user-data-dir="$ISO/chrome" \
  --no-first-run --no-default-browser-check "http://127.0.0.1:18931/" &
sleep 5
curl -s http://127.0.0.1:9333/json/list | grep -c '"type": "page"'   # 必须 ≥ 1
```

`0` 或空数组就**先停下报告**，不要继续任务 1/3。

### 公共脚本 A · 扣住首个匹配请求（制造乱序）

存成 `watch.mjs`。会**自己查找或新建 page target**，并在导航**之前**启用拦截：

```js
// 用法: node watch.mjs <cdpPort> <appUrl> <url子串> <延迟毫秒>
const [, , port = '9333', appUrl = '', pattern = '', delayMs = '5000'] = process.argv;
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

await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
await send('Page.enable');
await send('Page.navigate', { url: appUrl });
console.log(`已连接 ${base} 并导航到 ${appUrl}；pattern=${pattern}，首个延迟 ${delayMs}ms。`);
```

### 公共脚本 B · 删除响应里的一个 JSON 字段

存成 `strip-field.mjs`。**自带校验**：在页面里请求一次并打印页面真实收到的内容。

```js
// 用法: node strip-field.mjs <cdpPort> <appUrl> <url子串> <字段名>
const [, , port = '9333', appUrl = '', pattern = '', field = ''] = process.argv;
const base = `http://127.0.0.1:${port}`;
const listTargets = async () => (await (await fetch(`${base}/json/list`)).json());

let list = await listTargets();
let page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) {
  await fetch(`${base}/json/new?url=${encodeURIComponent(appUrl)}`, { method: 'PUT' });
  await new Promise((r) => setTimeout(r, 1500));
  list = await listTargets();
  page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
}
if (!page) throw new Error(`没有 page target。原始返回：${JSON.stringify(list)}`);

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0, stripped = 0;
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
  const p = msg.params;
  if (p.responseStatusCode == null) return void send('Fetch.continueRequest', { requestId: p.requestId });
  try {
    const got = await send('Fetch.getResponseBody', { requestId: p.requestId });
    const text = got.base64Encoded ? Buffer.from(got.body, 'base64').toString('utf8') : got.body;
    const data = JSON.parse(text);
    const had = Object.prototype.hasOwnProperty.call(data, field);
    delete data[field];
    stripped += 1;
    const headers = (p.responseHeaders || []).filter((h) => !/^content-length$/i.test(h.name));
    headers.push({ name: 'content-type', value: 'application/json' });
    await send('Fetch.fulfillRequest', {
      requestId: p.requestId,
      responseCode: p.responseStatusCode,
      responseHeaders: headers,
      body: Buffer.from(JSON.stringify(data), 'utf8').toString('base64'),
    });
    console.log(`[${new Date().toISOString()}] 已改写 ${p.request.url}（原有 ${field}=${had}，现删除）`);
  } catch (err) {
    console.log(`改写失败，原样放行：${err.message}`);
    await send('Fetch.continueRequest', { requestId: p.requestId });
  }
});

await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
await send('Fetch.enable', { patterns: [{ urlPattern: `*${pattern}*`, requestStage: 'Response' }] });
await send('Page.enable');
await send('Page.navigate', { url: appUrl });
console.log(`已启用响应改写：${pattern} 去掉字段 ${field}`);

await new Promise((r) => setTimeout(r, 2500));
const probe = await send('Runtime.evaluate', {
  expression: `fetch('${appUrl.replace(/\/$/, '')}${pattern}').then(r=>r.text())`,
  awaitPromise: true, returnByValue: true,
});
console.log('页面实际收到的响应：' + probe.result.value);
console.log('改写次数：' + stripped);
```

---

### 任务 1 · R07：省略 `workspace_id` 时本地问答历史**仍载入一次**（**判据已更正**）

**上一轮为什么误判**：你把会话建在真实 workspace 键下，然后剥离字段，客户端就切到了回退键
`'unknown'` 的存储——**那是另一个存储键，空是正常的**。切 workspace 时清空是有意设计
（代码注释："旧工作区的预演/在途写回标记不得带入新工作区"）。所以「`2/10` → `0/10`」
**不是缺陷**。

R07 真正要验的是：**在省略 `workspace_id` 的情况下，本地历史仍然被载入**（而不是永远不载入）。
修复前的 bug 是守卫恒假、`loadAskStore()` 永不被调用；修复后会被调用一次。

**步骤**：

1. 启动脚本（它会把应用导航起来，并让 `/api/version` 一直省略该字段）：
   ```
   node strip-field.mjs 9333 http://127.0.0.1:18931/ /api/version workspace_id
   ```
2. 确认脚本打印的「页面实际收到的响应」里**确实没有** `workspace_id`（把这行原文贴回来）。
3. **在这个状态下**进第二大脑页签，新建 1–2 个会话。记录计数（形如 `2/10`）。
4. **刷新页面**（脚本仍在改写，字段仍被剥离）。
5. **通过标准**：刷新后计数**仍是 `2/10`**，会话列表还在。
   （修复前的行为会是 `0/10` —— 历史被丢掉。这就是判据。）
6. 再刷新或切走切回一次，仍然保留。

**回报**：字段确实被剥离的响应原文；刷新前/后的会话计数原文（`2/10` → `?`）。

> 如果刷新后是 `0/10`，那才是**真失败**，请把 Console 里
> `Object.keys(localStorage).filter(k => k.includes('wb.ask'))` 的原文一起贴回来。

### 任务 2 · R04：设置页保存后不被旧读取覆盖 —— **用假密钥即可**

**不需要真实模型凭据**：`POST /api/settings/provider` 走的是
`update_provider_settings(...)`，**不校验**密钥（校验是另一个 `/verify` 路由）。
保存一个**假字符串**就能制造"保存后的状态"。

**步骤**：

1. 先记录设置页当前 provider 文案（上一轮是「未配置」）。
2. 开拦截：`node watch.mjs 9333 http://127.0.0.1:18931/ /api/settings/profiles 6000`
3. 应用打开后进设置页（触发被扣住的 `/api/settings/profiles` 读取）。
4. 在第一个读取仍被扣住时，**在页面上保存一个假密钥**（例如
   `sk-dummy-for-race-test`），使文案变成「已配置」。
   若界面要求先选 provider 再填密钥，按界面来即可；**只写假值**。
5. 等被扣住的旧读取放行。
6. **通过标准**：最终文案仍是**保存后**的状态（「已配置」），**不被**旧读取（「未配置」）覆盖。

**回报**：保存请求与两次读取的时间戳、保存后的文案、旧读取放行后的最终文案。

> 若界面**不允许**保存假密钥（例如强制校验后才可提交），如实回报这条限制并判未验证——
> **不要**为了通过去要真实密钥。

### 任务 3 · R09：外部写回列表不被旧响应覆盖 —— **用本地造的数据**

`/api/external-actions` 读的是本地账本 `_vault/_signals/external-actions/log.jsonl`，
**不需要飞书**。每行是一个 JSON 对象。先取当前 workspace id：

```bash
WS=$(python3 -c "import json;print(json.load(open('$WORK_ROOT/_vault/.summit-workbench/workspace.json'))['workspace_id'])")
echo "$WS"
```

造第一行（`state` 用 `failed` 更容易在界面上看出来）：

```bash
mkdir -p "$WORK_ROOT/_vault/_signals/external-actions"
cat > "$WORK_ROOT/_vault/_signals/external-actions/log.jsonl" <<EOF
{"schema_version":1,"operation_id":"race-op-1","candidate_id":"local:fixture#action-item-1","workspace_id":"$WS","kind":"feishu-task","request_fingerprint":"fp-1","target_account_ref":"test","state":"failed","attempt":1,"timestamp":"2026-09-11T13:00:00+08:00","remote_id":null,"error":"合成数据：用于乱序验收","retry_allowed":true}
EOF
```

`kind` 只能是 `feishu-task` / `feishu-meeting`；`state` 只能是
`prepared` / `sending` / `succeeded` / `failed` / `unknown` / `reconciled-succeeded` / `reconciled-not-found`。
**`workspace_id` 必须与上面的 `$WS` 一致**，否则会被过滤掉。

**步骤**：

1. 开拦截：`node watch.mjs 9333 http://127.0.0.1:18931/ /api/external-actions 6000`
2. 进审批页 → 第一次读取被扣住（此时账本只有 1 条）。
3. **在被扣住期间**，往同一个 `log.jsonl` **追加**第二条（改 `operation_id` 为
   `race-op-2`、`error` 写成「合成数据：较新的一条」）：
   ```bash
   cat >> "$WORK_ROOT/_vault/_signals/external-actions/log.jsonl" <<EOF
   {"schema_version":1,"operation_id":"race-op-2","candidate_id":"local:fixture#action-item-2","workspace_id":"$WS","kind":"feishu-meeting","request_fingerprint":"fp-2","target_account_ref":"test","state":"failed","attempt":1,"timestamp":"2026-09-11T13:05:00+08:00","remote_id":null,"error":"合成数据：较新的一条","retry_allowed":true}
   EOF
   ```
4. 触发第二次读取（切走再切回审批页）→ 它会看到 **2 条**。
5. 等被扣住的第一次读取（只有 1 条）放行。
6. **通过标准**：最终列表是**较新的 2 条**，旧响应（1 条）**不得**把它覆盖回 1 条。

**回报**：脚本打印的两次请求时间戳；最终列表里两条 `error` 文案（或条数）。

### 任务 4 · R05：隐藏页 60 秒暂停 + 回到前台立即补一次

**用 Console 计数，不要肉眼数 Network 面板**，并**埋探针**做归因：

```js
performance.setResourceTimingBufferSize(1000);
const count = (p) => performance.getEntriesByType('resource').filter((e) => e.name.includes(p)).length;
window.__tick = 0;
window.__probe = setInterval(() => { window.__tick++; }, 60000);
({ base: { version: count('/api/version'), sync: count('/api/sync/status') }, at: new Date().toISOString() })
```

切到别的标签页 / 最小化，**隐藏 ≥ 130 秒**，切回后**立刻**读：

```js
({ after: { version: count('/api/version'), sync: count('/api/sync/status') },
   tick: window.__tick, at: new Date().toISOString() })
clearInterval(window.__probe);
```

**通过标准**：`after.version - base.version === 1` **且** `after.sync - base.sync === 1`。

**归因（必须如实写）**：
- `tick > 0` → 隐藏期间定时器**确实跑了**，因此"没有发请求"**证明可见性守卫生效**。
- `tick === 0` → **无法区分**是守卫生效还是浏览器节流。写「无法区分」，**不要**写通过。

### 任务 5 · D2：来源面板异常矩阵（**HTTP 矩阵已完成，只剩两件事**）

上一轮已经在真实浏览器里拿到完整 HTTP 矩阵，**不必重测**：

| 用例 | 状态码 | 响应 message |
|---|---|---|
| `projects/probe.md`（非 UTF-8） | **415** | 来源不是可读取的 Markdown 笔记 |
| `projects/big.md`（截断） | 200 | `bodyLen=100000`、`truncated=true` |
| `projects/huge.md` | **413** | 来源超过 256 KiB，请缩小范围后重试 |
| `../../etc/passwd` | **400** | 来源路径不在允许的知识范围内 |
| `projects/escape.md`（软链） | **400** | 来源路径越界 |
| `_signals/signal.md` | **400** | 来源路径不在允许的知识范围内 |
| `notes/note.md` | **400** | 来源路径不在允许的知识范围内 |
| `projects/missing.md` | **404** | 来源不存在或已失效 |

> 顺带确认：非 UTF-8 返回 **415 而不是 500**，说明第一轮修的缺陷在真实浏览器里**已验证修好**。

**只剩两件事**：

1. **界面文案**：从审批候选的「来源」入口（**不是直接 fetch**）逐个打开上述文件，
   记录**页面上实际显示的文字**。特别是非 UTF-8 那条：**不得**出现 `[internal_error]`，
   应是可读的中文提示。
2. **第二个 workspace 隔离**：另建**第二个** workspace（另一个端口或另一个 `WORK_ROOT`），
   在它里面放**同名但内容不同**的 `projects/demo-project.md`；回到第一个 workspace 打开该来源，
   必须读到**第一个**的内容；切到第二个打开，必须读到**第二个**的内容。

**回报**：每个用例一行：文件 → 面板显示的文字。

### 任务 6 · C4：「新建会议（个人日程）」落点 —— **这一项确实需要飞书授权**

会在**真实飞书日历建事件**：

- **没有明确授权就跳过**，回报「未验证：无飞书授权」，**不要**尝试。
- 有授权时：在隔离 workspace 造一条 `route: feishu-meeting` 的候选
  （带 `start_at`/`end_at`，本地 naive `YYYY-MM-DDTHH:MM`），确认它在真实页面上
  **可选中、可批准**；若被要求写回，只建一个事件，**回读校验后立即删除**，
  回报事件 id 与删除结果，**不留残留**。

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

## 附：状态与建议顺序

| 任务 | 覆盖 | 上一轮 | 说明 |
|---|---|---|---|
| 1 | R07 | ~~失败~~ → **判据更正** | 上一轮是误判；本轮验"剥离状态下建的会话刷新后仍在" |
| 2 | R04 | 未验证 | 改用**假密钥**，不需要真凭据 |
| 3 | R09 | 未验证 | 改用**本地 outbox 合成数据**，不需要飞书 |
| 4 | R05 | 未验证 | Console 计数 + 探针归因 |
| 5 | D2 | 未验证 | HTTP 矩阵已完成，只剩界面文案 + 第二 workspace |
| 6 | C4 | 未验证 | **唯一真正需要飞书授权的一项** |

**建议顺序：1 → 2 → 3 → 4 → 5 → 6。** 前五项都不需要你的任何凭据。

**已关闭，不要重跑**：C1、C2、R01、R03、R06、R08、R10、R11、D3、E1、E2、E3、E4。
