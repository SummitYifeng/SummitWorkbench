# 收尾提示词 v4：剩余 5 项 UI 层验收（整段复制给 Codex）

> **v4 变更**
> - ✅ **已关闭，不要重跑**：C1、C2、R01、R03、R06、R07、R08、R10、R11、D2、D3、E1、E2、E3、E4。
> - 🔧 **R04 上一轮的失败是我配方错**：`saveModel` 里有
>   `if (!secret) { toast('请先粘贴 DeepSeek API Key'); return; }`，**表单拒绝无密钥提交**，
>   而直接 POST 假密钥会**写登录钥匙串**（不受临时 `HOME` 隔离，ACL 不含调用方时会弹 GUI 框阻塞）
>   —— 这就是你看到的"10 秒未返回"。**已改为完全不需要凭据、且测试同一段守卫的配方。**
> - 🔧 **R09 上一轮的失败是时序**：旧脚本只扣 6 秒，来不及触发第二次读取。
>   已改为**闸门式**（扣住直到你 `touch` 一个文件），不再依赖秒数。**脚本已实测。**
> - **只有 C4 需要账号所有者介入**（真实飞书日历）。

---

## 复制区（从这里开始）

你是真实浏览器验收执行者。在**隔离环境**里跑完下面 6 个任务，逐条回报**原始证据**。

### 铁律

1. **只用临时环境**：临时 `HOME`、`WORK_ROOT`、vault。**绝不**指向真实工作区。
2. **不连真实模型、不连真实飞书**——唯一例外是任务 4（C4），必须先取得明确授权。
3. **没有实际观察到的，一律写「未验证」**并说明卡在哪。前几轮你把 R05 判未验证都是对的。
4. **每条断言要有原始证据**：计数、时间戳、响应原文、界面文案等可判定量。
5. **不要点任何写回按钮**，除非任务明确要求。

### 环境准备

```bash
ISO=$(mktemp -d /tmp/swb-v4-XXXXXX)
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

`0` 或空数组就**先停下报告**，不要继续任务 1/2。

### 公共脚本 A · 闸门式扣留（**决定性时序**，任务 1、2 用）

存成 `gate.mjs`。它**自己查找或新建 page target**、**导航到应用**、在导航**之前**启用拦截，
然后把**第一个**匹配请求一直扣住，直到 gate 文件出现；其余请求立即放行。

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
let id = 0, seen = 0;
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
  } else {
    console.log(`[${new Date().toISOString()}] #${n} 到达 ${request.url} → 立即放行`);
  }
  await send('Fetch.continueRequest', { requestId });
});

await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
await send('Page.enable');
await send('Page.navigate', { url: appUrl });
console.log(`已连接 ${base} 并导航到 ${appUrl}；pattern=${pattern}。#1 扣住直到 ${gateFile} 出现。`);
```

> **已实测**：#1 被扣住期间 #2–#5 正常通行；`touch` 闸门后 #1 才放行。

### 公共脚本 B · 删除响应里的一个 JSON 字段（任务 3 用，可跳过）

即 `strip-field.mjs`，与上一版相同（**已实测**）：把响应里某个 JSON 字段删掉再放行，
并会自检打印页面真实收到的内容。若任务 3 已通过可跳过，脚本见本文件 v3 版本或按需重写。

---

### 任务 1 · R04：设置页保存后不被旧读取覆盖 —— **不需要任何凭据**

**上一轮为什么失败（不是你的错）**：`saveModel` 里有
`if (!secret) { toast('请先粘贴 DeepSeek API Key'); return; }` —— 表单**拒绝无密钥提交**；
而绕过表单直接 POST 假密钥会走 `update_provider_settings` → **写 macOS 登录钥匙串**
（`security add-generic-password`）。钥匙串**不在临时 `HOME` 内**，ACL 不含调用方时会弹出
GUI 授权框，请求就一直不返回 —— 这正是你观察到的现象。

**改成不需要凭据、但测试同一段守卫的配方。** 要验的守卫是 `settingsRenderSequence`
（"先发起的旧响应不得覆盖后发起的新内容"），两次读取都打 `/api/settings/profiles`
（`web/src/features/settings/index.ts`）。只要**两次读取的内容不同**就能看出有没有被覆盖——
而该响应里含 `display_name`，它来自**临时 `HOME` 内**的 registry，可以随便改。

**关键前提（你先观察到的，是对的）**：设置页在读取期间会把内容清成「正在读取设置…」，
所以**扣住期间页面上没有可用表单**。因此触发第二次读取要靠**切页签**，而不是点保存。

**步骤**：

1. 找到临时 registry 并记下当前 `display_name`：
   ```bash
   REG="$ISO/home/Library/Application Support/SummitWorkbench/registry.json"
   cat "$REG"
   ```
2. 启动闸门脚本（它会自己打开应用）：
   ```bash
   node gate.mjs 9333 http://127.0.0.1:18931/ /api/settings/profiles "$ISO/gate-r04"
   ```
3. 在应用里切到**设置**页签 → 触发读取 **#1**，被扣住；页面显示「正在读取设置…」。
   确认脚本打印了 `#1 到达 … 被扣住`。
4. **在被扣住期间**，把 registry 里的 `display_name` 改成明显不同的值（例如原值后加
   `【已更新】`）并保存文件。记下改前/改后的值。
5. **切到别的页签，再切回设置** → 触发读取 **#2**，立即放行并渲染出**新**名称。
   确认脚本打印了 `#2 到达 … 立即放行`。
6. 确认页面上「工作区」卡片显示的是**新**名称。
7. **`touch "$ISO/gate-r04"`** → 扣住的 #1（携带**旧**名称）此刻才放行。
8. **通过标准**：页面上的「工作区」卡片**仍然是新名称**。
   若它变回旧名称 → 守卫失效（**那才是真失败**）。

**回报**：脚本全部输出（含两个时间戳）；改前/改后的 `display_name`；第 6 步与第 8 步页面上
「工作区」卡片实际显示的文字。

> **可选、需账号所有者同意**：想连"保存→刷新"这条触发路径一起验，就必须用**真实 DeepSeek 密钥**
> （表单强制校验，且保存会真的连网验证并写登录钥匙串）。**没拿到明确授权就不要做这一条**，
> 按上面的守卫测试给结论即可，并在回报里说明哪条路径验了、哪条没验。

### 任务 2 · R09：外部写回列表不被旧响应覆盖 —— **本地造数据 + 闸门**

`/api/external-actions` 读本地账本 `_vault/_signals/external-actions/log.jsonl`，**不需要飞书**。

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
2. 在应用里切到**审批**页签 → 触发读取 **#1**（此刻账本只有 1 条），被扣住。
   确认脚本打印了 `#1 到达 … 被扣住`。
3. **在被扣住期间**，往同一个 `log.jsonl` **追加**第二条：
   ```bash
   cat >> "$WORK_ROOT/_vault/_signals/external-actions/log.jsonl" <<EOF
   {"schema_version":1,"operation_id":"race-op-2","candidate_id":"local:fixture#action-item-2","workspace_id":"$WS","kind":"feishu-meeting","request_fingerprint":"fp-2","target_account_ref":"test","state":"failed","attempt":1,"timestamp":"2026-09-11T13:05:00+08:00","remote_id":null,"error":"合成数据：新的一条","retry_allowed":true}
   EOF
   ```
4. **切到别的页签，再切回审批** → 触发读取 **#2**，立即放行，渲染出 **2 条**。
   确认脚本打印了 `#2 到达 … 立即放行`，且页面上显示 2 条。
5. **`touch "$ISO/gate-r09"`** → 扣住的 #1（只有 1 条）此刻才放行。
6. **通过标准**：外部写回列表**仍然是 2 条**。
   若被覆盖回 1 条 → 守卫失效（**那才是真失败**）。

**回报**：脚本全部输出（含时间戳）；第 4 步与第 6 步列表里实际显示的条数与文案。

### 任务 3 · R07 复跑（**可选，已通过**）

R07 上一轮已通过（剥离 `workspace_id` 后 `2/10` 刷新两次仍是 `2/10`，
`localStorage` 为 `["wb.ask.threads.v1.unknown"]`），**除非想复现，否则跳过**。

### 任务 4 · C4：「新建会议（个人日程）」落点 —— **这一项需要账号所有者介入**

会在**真实飞书日历建事件**：

- **到这一步就停下来，向账号所有者请求授权**，不要自行尝试。
- 未获授权 → 回报「未验证：无飞书授权」。
- 获授权后：在隔离 workspace 造一条 `route: feishu-meeting` 的候选（带 `start_at`/`end_at`，
  本地 naive `YYYY-MM-DDTHH:MM`），确认它在真实页面上**可选中、可批准**；
  若被要求写回，只建一个事件，**回读校验后立即删除**，回报事件 id 与删除结果，**不留残留**。

### 任务 5 · B4：原生 App / WKWebView 黑盒 —— **不要用 `WORK_ROOT`**

**不能用 `WORK_ROOT` 隔离**：`webapp/server_entry.py` 明确写着打包后的 server
**永不消费 `WORK_ROOT` 或 `--work-root`**。App 只认 **active profile**，而本机状态从
`home_dir()`（= `Path.home()`）派生，所以要用**临时 `HOME` 直接启动可执行文件**，
**不要**用 `open -a`：

```bash
ISO2=$(mktemp -d /tmp/swb-app-XXXXXX)
mkdir -p "$ISO2/Library/Application Support"
HOME="$ISO2" /Applications/SummitWorkbench.app/Contents/MacOS/SummitWorkbench
```

**动手前强制自检（不通过就停）**：打开设置页看工作区路径。

- ✅ 期望：onboarding / 空工作区，**不出现** `/Users/<真实用户>/Documents/Work/_vault`。
- ❌ 若仍显示真实 vault 路径：说明 `HOME` 没生效（原生层可能用 `NSHomeDirectory()`，
  它读账户数据库而不是 `$HOME`）。**立即退出，不要再做任何操作**，把
  「原生 App 无法用环境变量隔离」作为 B4 的**阻塞结论**回报。

自检通过后：确认 build identity 与实际产物一致；走一遍新建工作台（指向临时目录）；
跑六页签可达性；确认操作发生在 **WKWebView** 内；退出重启确认不出现 crash loop、不误认旧服务。
结束后删除 `$ISO2`。

### 任务 6 · R05：隐藏页 60 秒暂停 + 回到前台立即补一次

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

**归因（必须如实写）**：`tick > 0` → 定时器确实跑了，因此"没发请求"**证明可见性守卫生效**；
`tick === 0` → **无法区分**守卫与浏览器节流，写「无法区分」，**不要**写通过。

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

| 任务 | 覆盖 | 状态 | 需要账号所有者？ |
|---|---|---|---|
| 1 | R04 | 配方改为**无凭据**测同一段守卫 | 否（可选路径才需要） |
| 2 | R09 | 改为**闸门式**（已实测脚本） | 否 |
| 3 | R07 | **已通过**，可跳过 | 否 |
| 4 | C4 | 待授权 | ✅ **真实飞书** |
| 5 | B4 | 临时 `HOME` 隔离配方 | 否 |
| 6 | R05 | 原配方不变，只需真的隐藏 130 秒 | 否 |

**建议顺序：1 → 2 → 6 → 5 → 4。** 前四项都不需要账号所有者介入；到 **4（C4）** 再停下请求授权。

**已关闭，不要重跑**：C1、C2、R01、R03、R06、R07、R08、R10、R11、D2、D3、E1、E2、E3、E4。
