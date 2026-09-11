# 收尾提示词 v2：剩余 4 项 UI 层验收（整段复制给 Codex）

> **v2 变更**：C1 已于 2026-09-11 关闭（证据 `0 / 2 requests` vs `1 / 12 requests`），**不要重跑**。
> 上一轮 4 个任务未验证，其中**任务 4 的失败是我的配方缺陷**（脚本没自检 page target），
> 已改成自愈版并**实测通过**；R07 的前提**原来写错了**（见该任务），已改为用实测过的响应改写脚本。
>
> 本文只覆盖剩下的项。上一轮逐项结果见 `OPEN-VERIFICATION-ITEMS.md` §M。

---

## 复制区（从这里开始）

你是真实浏览器验收执行者。在**隔离环境**里跑完下面 4 个任务，逐条回报**原始证据**。

### 铁律

1. **只用临时环境**：临时 `HOME`、临时 `WORK_ROOT`、临时 vault。**绝不**指向真实工作区。
2. **不连真实模型、不连真实飞书**——唯一例外是任务 6（C4），且必须先取得明确授权。
3. **没有实际观察到的，一律写「未验证」**并说明卡在哪。宁可我拿到诚实的「未验证」，
   也不要一个编造的「通过」。**上一轮你把 E3 判为未验证是正确判断**，即使 AX 证据看起来支持。
4. **每条断言要有原始证据**：计数、时间戳、响应原文、`window.scrollY` 数值等可判定量。
5. **不要点任何写回按钮**（「确认应用（写回）」「恢复写回」等），除非任务明确要求。

### 环境准备

```bash
ISO=$(mktemp -d /tmp/swb-v2-XXXXXX)
mkdir -p "$ISO/home" "$ISO/work"
export HOME="$ISO/home" WORK_ROOT="$ISO/work"
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/wb web --host 127.0.0.1 --port 18931 &
```

按向导新建工作区，**模型与飞书都选「跳过」**。回报 `frontend_build`、端口、Chrome 版本。

需要用 DevTools 协议时，**用独立端口 9333 并先自检**（上一轮用 9222 得到空 target 列表，
导致任务 4 白跑）：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9333 --user-data-dir="$ISO/chrome" \
  --no-first-run --no-default-browser-check "http://127.0.0.1:18931/" &
sleep 5
curl -s http://127.0.0.1:9333/json/list | grep -c '"type": "page"'   # 必须 ≥ 1
```

若这里是 `0` 或返回空数组：**不要继续任务 4 / 5**，先把原始输出贴回来报告环境问题。
（下面两个脚本都会**自己找或新建 page target**，所以通常不必手工处理；但自检失败说明
端口上不是你以为的那个 Chrome，那时候脚本报的错才是真的。）

### 任务 0 · E3：**项目列表**滚动位置恢复 —— 必须给出数值

**上一轮你已观察到 AX 从 `(showing 0-100 of 216 items)` 变成 `(showing 116-216 of 216 items)`，
这和"位置被恢复"是一致的，但**不能替代数值证据**（可能是别的原因导致重渲染）。所以只需补一个数值。

**夹具**：项目列表要高于视口（上一轮的 36 个项目已够，页面显示 `共 36`）。

**步骤**（在页面 Console 里取值，不要靠肉眼）：

```js
// 1) 自证夹具有效
({ scrollH: document.body.scrollHeight, innerH: window.innerHeight })
// 2) 停在列表，滚到中部，读 Y1
window.scrollY
// 3) 点开任意项目详情，读详情初始位置（预期 0，这是通过项不是失败）
window.scrollY
// 4) 点「返回」回到列表，读 Y2
window.scrollY
```

**通过标准**：`Y1 > 0` 且 `Y2 === Y1`（允许 ±2px）。**回报 `Y1` / 详情初始值 / `Y2` 三个数字原文**，
以及查询框内容与筛选值。

> 提醒：详情**总是从顶部开始**是设计如此（`showProjectView()` 显式 `scrollTo(0)`）。
> 要验的是"返回列表后列表位置还原"。上一轮有人把它测成"重新进入详情后期望停在原处"，那是错的。

### 任务 1 · R01 / R04 / R09：制造**乱序响应**

把下面脚本存成 `watch.mjs`。它**自己找或新建 page target**，并在导航**之前**启用拦截
（顺序很重要，否则页面首次加载的请求抓不到）：

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

> 这个脚本在写进本文档前**已实测**：首个请求被扣 4000ms，期间 #2、#3 正常通行，
> #1 最后才放行——乱序确实成立。脚本会打印每一笔的时间戳，**把这些时间戳原样贴回来**。

**R09 · 外部写回列表不被旧响应覆盖**

```
node watch.mjs 9333 http://127.0.0.1:18931/ /api/external-actions 6000
```
脚本会自己打开应用。进审批页；在第一个请求仍被扣住时，**再触发一次**外部写回列表刷新
（切走再切回审批页）。
**通过标准**：最终列表是**较新**那次的数据，旧响应到达后**不得**覆盖。

**R04 · 设置页保存后不被旧读取覆盖**

```
node watch.mjs 9333 http://127.0.0.1:18931/ /api/settings/profiles 6000
```
应用打开后进设置页（触发被扣住的读取），**立即**保存一次模型/provider 设置，
再等被扣住的读取放行。
**通过标准**：界面仍是**保存后**的状态。

**R01 · 项目详情不被过期响应推回**

```
node watch.mjs 9333 http://127.0.0.1:18931/ /api/projects/view 6000
```
快速连续点开项目 A、再点开项目 B。
**通过标准**：最终显示的是**最后点开**的项目；A 的迟到响应不得把 A 的详情推回，也不得抢焦点。
回报最终项目名与 `document.activeElement`。

**如果 `Fetch.enable` 报错或脚本抛异常**：把**原始错误栈与 `/json/list` 原文**贴回来，
不要改判为通过，也不要只写「失败了」。

### 任务 2 · R05：隐藏页 60 秒暂停 + 回到前台立即补一次

**不要靠肉眼数 Network 面板**（上一轮就是因此拿不到最终计数）。用页面 Console 计数，
并且在隐藏前**埋一个探针**来区分"守卫生效"和"只是浏览器节流了定时器"：

```js
// ① 先放大计时缓冲，避免条目被淘汰
performance.setResourceTimingBufferSize(1000);

// ② 计数函数
const count = (p) => performance.getEntriesByType('resource').filter((e) => e.name.includes(p)).length;

// ③ 隐藏前记录基线，并埋探针（探针用来证明"隐藏期间定时器到底有没有跑"）
window.__tick = 0;
window.__probe = setInterval(() => { window.__tick++; }, 60000);
({ base: { version: count('/api/version'), sync: count('/api/sync/status') }, at: new Date().toISOString() })
```

然后切到别的标签页 / 最小化，**隐藏 ≥ 130 秒**，切回后立刻读：

```js
({ after: { version: count('/api/version'), sync: count('/api/sync/status') },
   tick: window.__tick, at: new Date().toISOString() })
clearInterval(window.__probe);
```

**通过标准**：
- `after.version - base.version === 1` **且** `after.sync - base.sync === 1`（回到前台各补**恰好一次**）。
- 隐藏期间**没有**新增（这由上面的差值间接证明：若隐藏期间有发出，差值会 > 1）。

**关于归因（必须如实写）**：
- 若 `tick > 0`：说明隐藏期间定时器**确实跑了**，那么"没有发出请求"就**证明可见性守卫生效**。
- 若 `tick === 0`：**无法区分**是守卫生效还是浏览器节流。请在回报里写明
  「无法区分」，**不要**写成通过。

### 任务 3 · R07：`/api/version` 省略 `workspace_id` 时问答历史仍载入一次

**更正上一版的错误**：上一版说"用空安装模式就能自然触发"——**这是错的**。空安装跑的是
受限控制面（只有 onboarding），根本**没有第二大脑页签**，测不了问答历史。而在正常应用里
服务端**总会**带上 `workspace_id`。所以这一项**必须改写响应**。

把下面脚本存成 `strip-field.mjs`。它删掉响应里的一个 JSON 字段再放行，
**并且会自检**：自己在页面里请求一次并打印页面真实收到的内容：

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

> 同样**已实测**：原有 `workspace_id=true` 被删除后，页面实际收到
> `{"product_id":"summit-workbench","server_version":"0.4.4","frontend_build":"test"}`。
> **把这两行原文贴回来**——这是"省略字段"这个前提成立的证据。

**步骤**：
1. 先建 1–2 个问答会话（让第二大脑页签显示形如 `2/10`）。
2. 跑 `node strip-field.mjs 9333 http://127.0.0.1:18931/ /api/version workspace_id`。
3. 确认脚本打印的"页面实际收到的响应"里**确实没有** `workspace_id`。
4. 在第二大脑页签观察会话列表。

**通过标准**：
- 会话列表**仍然载入**（计数仍为 `2/10`，不是 `0/10`），**且没有被清空**。
- 再触发一次 `/api/version`（切到别的标签页再切回，或等 60 秒轮询），
  仍然**不重复载入、不清空**。

### 任务 4 · C4：「新建会议（个人日程）」落点 —— **需要授权**

会在**真实飞书日历建事件**：
- **没有明确授权就跳过**，回报「未验证：无飞书授权」，**不要**尝试。
- 有授权时：在隔离 workspace 造一条 `route: feishu-meeting` 的候选（带 `start_at`/`end_at`，
  本地 naive `YYYY-MM-DDTHH:MM`），确认它在真实页面上**可选中、可批准**；
  若被要求写回，只建一个事件，**回读校验后立即删除**，回报事件 id 与删除结果，**不留残留**。

### 任务 5 · D2：来源面板异常矩阵（含修复后复验）

**夹具**（临时 vault 内）：

| 用途 | 文件 |
|---|---|
| 正常 | `projects/demo-project.md` |
| **非 UTF-8** | `printf '\x89PNG\r\n\x1a\n\x00\x01\x02\xff\xfe' > _vault/projects/probe.md` |
| 截断 | `projects/big.md`，正文 100,000–262144 字节 |
| 413 | `projects/huge.md`，**> 262144 字节** |
| 路径穿越 | 请求 `../../etc/passwd` 一类路径 |
| 软链越界 | `ln -s /etc/hosts _vault/projects/escape.md` |
| 非知识目录 | `_signals/`、`notes/` 下的文件 |
| 缺失 | `projects/missing.md`（不创建） |
| workspace 隔离 | 另建**第二个** workspace，放**同名但内容不同**的文件 |

> 来源面板调 `/api/sources/read`，它会把非 `.md` 的来源 id 后缀改写成 `.md`。
> 所以 `probe.bin` 只会得到 404——**要触发解码路径，文件必须真的叫 `.md`**，
> 且必须是**真的非 UTF-8 字节**（"看起来像乱码的中文"仍是合法 UTF-8，无效）。

**步骤**：从审批候选的「来源」入口逐个打开，**每个用例同时记录 HTTP 状态码**与界面文案。

**通过标准**：
- **非 UTF-8 → 415 + 明确文案**（如「来源不是可读取的 Markdown 笔记」），
  **不得**出现 `[internal_error]`。（上一轮这里是 500，已修复，本轮是复验。）
- 截断 → 出现「正文已截断」，`document.querySelector('pre.source-reader').textContent.length === 100000`。
- 413 / 路径穿越 / 软链越界 / 非知识目录 / 缺失 → 明确文案 + 状态码
  （预期 413 / 400 / 400 / 400 / 404）。
- 第二个 workspace 的同名文件必须读到**第二个**的内容。

**回报**：每个用例一行：文件 → HTTP 状态码 → 界面文案。

### 回报格式（每个任务一段）

```
任务：<编号与覆盖项>
环境：临时 HOME/WORK_ROOT 路径；端口；frontend_build；Chrome 版本
结论：通过 / 失败 / 未验证
证据：计数、时间戳、响应原文、window.scrollY 数值、状态码等**原始值**
失败或未验证时：最小复现步骤 + 期望 vs 实际 + 卡在哪
```

最后给汇总表：任务 → 结论 → 一句话依据。

## 复制区结束

---

## 附：状态与建议顺序

| 任务 | 覆盖 | 上一轮 | 说明 |
|---|---|---|---|
| 0 | E3 | 未验证 | **只需补 3 个数字**，最便宜 |
| 1 | R01 / R04 / R09 | 未验证 | 脚本已修好并实测 |
| 2 | R05 | 未验证 | 改用 Console 计数 + 探针归因 |
| 3 | R07 | 未验证 | 上一版前提写错，已改为响应改写（已实测） |
| 4 | C4 | 未验证 | 需飞书授权 |
| 5 | D2 | 未验证 | 纯体力活 |

**建议顺序：0 → 2 → 1 → 3 → 5 → 4。** 上一个 **C1 已关闭**，不必重跑。

跑完把结果按格式发回，我据此更新 `OPEN-VERIFICATION-ITEMS.md`。
