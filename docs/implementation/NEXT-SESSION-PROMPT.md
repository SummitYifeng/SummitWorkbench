# 下一轮会话启动提示词（SummitWorkbench）

> **用法**：新开窗口时把本文件交给 Agent——直接说「读 `docs/implementation/NEXT-SESSION-PROMPT.md` 并按它开工」即可。
> **本文件是活文件**：每轮收口时按实测发现校正一次，别让它又变成一份过期文档。
> **最近校正**：2026-09-14（收口轮：起点复核、build 号漂移、条目 3 结案）。原委见
> `PLAN-WORK-KNOWLEDGE-BASE.md` §12 的「收口轮 · 起点复核 + 文档漂移 + 条目 3 结案」一节。

你在 `/Users/yifengstudio/Documents/GitHub/SummitWorkbench` 里继续一个「本地优先」的 macOS 应用项目：
原生 Swift 壳 + 打包在内的 Python FastAPI 服务 + 原生 TS 的 SPA 面板。核心用途是使用者的
「工作知识库 / 第二大脑」：会议纪要与材料入库 → AI 分类 → 人工审批 → 沉淀进知识库或写回飞书。

---

## 一、先读这几份文件（按顺序，它们是唯一真源）

1. `docs/implementation/PLAN-WORK-KNOWLEDGE-BASE.md` —— 计划 + **§12「执行进度（滚动更新）」**。
   状态：Phase 0–6 完成；Phase 7（Air 备用机）Studio 侧完成、Air 侧待使用者在另一台机器上执行。
   末尾另有「使用者反馈修复 · 项目档案区块不渲染 Markdown（build 41）」与「收口轮」两节。
2. `docs/implementation/AIR-MACHINE-HANDOFF.md` —— Air 接入作业单（含这一对机器的真实值）。
3. `docs/product/WEB_USAGE_GUIDE.md` —— App 内「指南」页的唯一真源。
   ⚠️ `web/src/guide.md` 是 `node web/scripts/sync-guide.mjs` 生成的、**被 gitignore 的构建产物**；
   改它会被下次构建覆盖。**要改文案只能改 `docs/product/WEB_USAGE_GUIDE.md`。**
4. `docs/RELEASING.md` —— 打包/发布流程与踩坑记录。
5. `docs/implementation/kb-spine-sample-comparison.md` —— 知识库结构选型（已定 β 方案）。

---

## 二、环境与身份（已核实，可直接用）

- 仓库：`/Users/yifengstudio/Documents/GitHub/SummitWorkbench`；Python venv `.venv`；CLI `.venv/bin/wb`。
- vault：`~/Documents/Work/_vault`（纯 Markdown + git；**53 个内容页** + 9 个模板；15 篇决策 + 8 个主题簇页；
  `index/{projects,decisions,people,timeline,sop}.md`；两条管线 `projects/hii-affairs.md`、`projects/it-development.md`）。
  索引 DB 在 vault **之外**：`~/Library/Application Support/SummitWorkbench/kb-index.sqlite`（实测 53 篇 / 685 块）。
- 远端（唯一真源，私有）：`https://github.com/yifeng93/WorkKnowledge.git`，分支 `main`。
  （注意：**仓库自己的** origin 是 `git@github.com:SummitYifeng/SummitWorkbench.git`，两者不是一回事。）
- workspace_id `fb9494a4-a080-40dd-a5c3-fcc12d7dc2dd`；
  本机（Studio）device_id `0617854a-e193-4b3e-bb6d-fb5bb738937d`，角色 automation-primary，generation 1。
- 已安装的 App：`/Applications/SummitWorkbench.app` = **0.4.9 build 41**
  （`frontend_build v2026.09.14-288f13d-4d072dbb`、`git_revision 288f13d`）；同步状态 `ready`，ahead 0 / behind 0。
- 最近提交：`053a20e`（记录渲染修复）、`288f13d`（渲染修复本体）、`d43566a`（验收 any-of）、
  `8889f79`（Air 作业单）、`425dff3`（截断重试 + 指南）。开工先 `git log --oneline -8` 对一眼。
- **没有任何备份**（使用者明确选择不留）。旧 vault、旧远端、旧 workspace 都不可恢复：
  绝不做破坏性操作，绝不 force / reset / rebase / stash。

---

## 三、铁律

- 每次改完必须过门禁（见第四节）；不许为了「变绿」放松判据。发现判据本身写错了，要**说清楚为什么**
  并保留等价强度（例：Q1 的关键证据改成「等价入口 any-of」，同时保证两个入口都没召回时仍然红）。
- **涉及检索权重/词表的改动，必须先用真实问题量一遍再决定**（历史上有两次凭直觉的改动实测有害，
  44%→31% 被回退）。16 项二值指标会随权重微调翻转，**不要**把它当单一调参目标。
- 关键修复要有**变异验证**：把守卫去掉后，测试必须立刻红。
- 改动要落到真实数据上验证，而不是只看单测：既有做法是 Python `build_project_view(vault, name)` 取真实
  blocks → 用 esbuild 打包真前端渲染函数 → 统计残留标记。
- 提交信息**必须用 `-F <文件>`** 传（提交信息里有反引号，直接写在命令行会被 shell 执行）。
  提交信息统一带 `[skip ci]`（无远端 CI）。中文提交信息，讲清「为什么」与「验证了什么」。
- 使用者用中文沟通；他重视诚实标注「已知不足 / 未验证」，也喜欢在动手前用选择题对齐需求。

---

## 四、门禁与验收（全部要绿）

```bash
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
.venv/bin/python -m pytest --cov -q          # 期望 1129 passed, 1 skipped, 覆盖率 ≥80%（当前 83.72%）
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy                                # 期望 359 文件无问题
.venv/bin/python scripts/secret_scan.py
npm --prefix web run test:frontend            # 16 组 node 纯渲染/契约测试（76 源文件）
# 真实库验收（9 题 = 4 题真调模型 Q1–Q4 + 5 题零 token R1/R2/D1/V1/S1）
.venv/bin/python scripts/kb_acceptance.py
# 已装 App 验收（4 题模型口径；只重查一题用 --only 省 token）
.venv/bin/python scripts/kb_acceptance_installed.py --only "Q1"
```

⚠️ **别写 `... | tail`**：管道会吞掉退出码，脚本真失败也会看着像成功（本轮踩过）。
证据落到 `docs/acceptance/evidence/`：
`kb-acceptance-2026-09-14.txt`（真实库 9 题）、
`kb-acceptance-installed-2026-09-14-build41.txt`（**已装 build 41，4 题**，本轮新增）。
**只改文档、没动代码时**，不重复跑两项会调模型的验收（上一条已被本轮覆盖且工作树未变），
在汇报里写明「未重跑及其理由」即可。

⚠️ 两条验收都**必须写工作区之外**（真实索引库在 `~/Library/Application Support/…`），
`kb_acceptance_installed.py` 还要用 `pgrep`/`ps` 读运行中 App 的会话令牌。
若当前沙箱只给 workspace-write，会以 `attempt to write a readonly database` / `ps` 被拒的形式失败——
那是**权限问题、不是回归**；按规则就地申请更宽权限，别去改脚本或改判据。

---

## 五、跟正在运行的 App 打交道

打包 App 是 production 模式，**所有 API 都要会话令牌**：

```bash
# 端口在 runtime record 里；令牌从 server 进程环境里读（不要打印它）
python3 - <<'PY'
import json,re,subprocess,urllib.request
rec=json.load(open("/Users/yifengstudio/Library/Application Support/SummitWorkbench/runtime.json"))
pid=subprocess.run(["pgrep","-f","SummitWorkbenchServer"],capture_output=True,text=True).stdout.split()[0]
tok=re.search(r"WB_SESSION_TOKEN=(\S+)",subprocess.run(["ps","eww","-p",pid],capture_output=True,text=True).stdout).group(1)
req=urllib.request.Request(f"http://127.0.0.1:{rec['port']}/api/version",headers={"X-WB-Session-Token":tok})
print(json.load(urllib.request.urlopen(req,timeout=30)))
PY
```

触发器（手动同步）：`POST /api/sync/status` 看状态、`POST /api/sync/run` 做一次 fetch→ff→push（**绝不 force**）。

---

## 六、重新构建并安装（本仓库固定套路）

```bash
cd /Users/yifengstudio/Documents/GitHub/SummitWorkbench
# 1) 发布脚本拒绝覆盖已存在的同名发布目录：先移开
mv dist/releases/0.4.9 dist/releases/0.4.9.superseded-b41
# 2) 从上一个含内置凭据的包里取证，写 0600 临时 env 文件（不要用 eval "$(heredoc)"，
#    那会把非机密的 app_id 打进日志）
umask 077; python3 - <<'PY' > /tmp/wb-feishu.env
import json,shlex
d=json.load(open('dist/releases/0.4.8/arm64/SummitWorkbench.app/Contents/Resources/feishu-defaults.json'))
for k,v in [("WB_FEISHU_APP_ID",d["app_id"]),("WB_FEISHU_APP_SECRET",d["app_secret"]),("WB_FEISHU_REDIRECT_URI",d.get("redirect_uri",""))]:
    if v: print(f"{k}={shlex.quote(v)}")
PY
chmod 600 /tmp/wb-feishu.env
set -a; . /tmp/wb-feishu.env; set +a
REQUIRE_BUNDLED_FEISHU=true BUILD_NUMBER=42 ARCH=arm64 scripts/release-macos.sh   # 构建较慢，放后台
rm -f /tmp/wb-feishu.env
# 3) 安装（会终止正在运行的实例并重启）
scripts/install-macos-app.sh dist/releases/0.4.9/arm64/SummitWorkbench.app --replace-running
```

- 版本号若动过，必须先 `uv pip install -e . --no-deps`，否则 `/api/version.server_version` 会报旧值。
- **DMG 文件名里不含 build 号**：重建后要认包，用 `dist/releases/0.4.9/arm64/SHA256SUMS`，
  或装完看 `/api/version.build`。`docs/RELEASING.md` 里有逐个 build 的账。
- ⚠️ ad-hoc 签名包每次替换后，**第一次读 vault 会弹「想访问文稿文件夹」——必须点允许**，
  否则界面一直转圈。这条要提醒使用者（作业单里也写了）。
- 给使用者的界面改动，装完要让他**刷新页面（⌘R）**；能自动热更的只有客户端插件。

---

## 七、当前待办（按优先级）

1. **Air 备用机接入**（需要使用者坐在那台机器上，你碰不到）：
   照 `docs/implementation/AIR-MACHINE-HANDOFF.md` 走。要点：装**同一个 build（现在是 41）** → 首次启动向导选
   「从另一台 Mac 克隆」→ 填 `https://github.com/yifeng93/WorkKnowledge.git` /
   目标文件夹（**必须还不存在**）`~/Documents/Work/_vault` / GitHub 用户名 `yifeng93` / 有 Contents 读写权限的 PAT
   → 「连接并检查」→「确认并开始使用」→ 连 DeepSeek key 与飞书一键授权。
   合格判据：角色显示**辅助设备（secondary）**（vault 里的主设备声明是 Studio，会自动判定）、
   `/api/sync/status = ready 0/0`、问一句真问题能答出**块级出处**、「决策」页 15 篇。
   这条路径已在 Studio 上拿真远端真凭据跑过（暂存克隆成功、marker 在、兼容性 read-write、
   另一设备 id 判 secondary），只有 Air 本机的 GUI 点击与权限弹窗未验证。
2. **已知检索不足（未解决）**：
   - Q3 的 `it/clusters/enrollment#关键结论` 在加「主题通道」后由「同篇不同块」变成**未召回**（净效果 6→7）。
   - 同篇多结论块互相竞争：分析笔记有 19 个「结论N」块，`max_chunks_per_note=3` 下哪 3 个进上下文
     仍偏字面相关度。
   - 度量是 16 项二值指标，个别项会随权重微调翻转 → 不适合当调参目标。
   若要做，先建**更可信的度量**（比如按「答案里是否出现关键结论、出处是否可解析」分档），再动权重。
3. ~~飞书授权缓存观测~~ —— **已结案，不要再查**。`~/Library/Application Support/…/feishu-auth-state.json`
   只是 OAuth `state` 的暂存表（`_STATE_TTL = 600s`），重启后为空是正确行为；界面徽标读的是 vault 内的
   `_signals/feishu-auth.json`（持久）。结论与证据见 PLAN §12「收口轮」第 2 节。
4. **素材尚未收完**：使用者的材料在 `/Users/yifengstudio/Desktop/当前材料`（是他自己整理过的版本，
   原始会议记录**故意**没放进来；他也说了材料**不完整**）。入库走 C-lite 三件套：
   1 份 `source`（逐字、不可改）+ 1 篇分析笔记（`##` 结论）+ N 篇 `decision`（6 固定区块 + 第 7 区块 `## 关联`）。
   规范见 `_vault/conventions.md`；幂等键 `source.ref + source.hash` **只在** `source`/`meeting-transcript` 页上判。
   `_vault` 里的内容可以删（使用者已授权）。
   他的四条工作线是：HII 沟通（loyalty / 商标 IP / 日常人员）、IT 开发计划、活满社群 + 工作日志 + 思考、HR。
   **已核实（2026-09-14）**：库里的 HR 与活满社群**只有骨架页**，工作日志 / 思考**只有模板**（`insights/`
   是空的），而素材目录里**只有 HII（4 份）+ IT（4 份）**——这三类素材一份都没有。
   ⇒ 这条**卡在素材**：使用者把材料放进目录后才谈得上开工。

---

## 八、两个必须保持同步的实现

`web/src/md.ts::mdToHtml` 与 `src/summit_workbench/webapp/views.py::md_to_html` 有明确的「同规则」契约
（标题 / 段落软换行 / 有序·无序·任务列表含嵌套 / 管道表格 / 引用 / 代码块 / `**粗体**` `*斜体*` `` `代码` ``
`[[目标|显示名]]`）。**改一边必须改另一边**，两边都有 XSS 断言（先整体转义、再套明确模式，
引号逃不出 `title` 属性）。前端测试 `web/scripts/test-md-render.mjs` 与后端
`tests/unit/test_webapp.py::test_md_to_html_*` 是同一批形状。

---

## 九、已经做完的（别再重做）

- 知识库结构（β 项目管线优先：只有 2 个 `projects/*.md`，主题簇页放 `<line>/clusters/`，没有 workstream 页）。
- 检索栈：FTS5 + trigram、问句路由器（点查/综合/回溯/决策/回顾）、多信号融合、块级 `路径#区块` 引用、
  双链扩展、同源去重；块边界为 `#`/`##`，但**文首 H1 是笔记标题、不算块边界**。
- 审批管线 7 个落点（含「知识沉淀」第 7 个 `RouteTarget`：目标页必须存在、只接受 vault 相对路径、拒穿越）。
- 决策页（API + UI + 路由契约快照）、Air 作业单、验收脚本与证据、SOP、App 内指南。
- 项目档案区块的 Markdown 渲染（build 41）：段落回流、有序列表、任务清单、嵌套、表格、
  wikilink 只显示标签；「指南」页 37 处编号列表也顺带修好。

---

## 十、怎么开始

1. 读第一节列的文件，`git log --oneline -8` 看最近改动。
2. 跑一遍第四节的完整门禁，确认起点是绿的（应当全绿）。
3. 问使用者这次要做哪一条（第七节的 1–2、4，或他新提的问题；第 3 条已结案）。
   如果是他报的界面/交互问题，按「先定位根因 → 修共享实现而不是就地打补丁 → 补测试与变异验证 →
   真实数据验证 → 重建安装 → 告诉他刷新」这套走。
4. 需要动 App 代码/界面时，记得最后一定要**重建并安装**，否则他看不到；并提醒 TCC 权限弹窗与 ⌘R 刷新。
