# 下一轮会话启动提示词（SummitWorkbench）

> **用法**：新开窗口时把本文件交给 Agent——直接说「读 `docs/implementation/NEXT-SESSION-PROMPT.md` 并按它开工」即可。
> **本文件是活文件**：每轮收口时按实测发现校正一次，别让它又变成一份过期文档。
> **最近校正**：2026-09-14（**UI 优化轮**）：删掉【决策】页签（决策只在各项目页「决策记录」里看，
> 全局查找交给「提问」）；【今日页】改上下两块（会议在上紧凑、待办任务在下占满整宽）；
> 「追加推进日志」项目勾选一项一行、英文 ID 收进 hover；全局口径「主显中文名、英文 ID 放次要位置、
> 只有引用来源保留完整路径」；审计出的 A 类（显示）/ B 类（布局）/ C 类（信息架构）全部处置。
> 装机 **build 49**（随后依次收窄了同步横幅、扫了原生壳与首启向导）。审计全表与逐条处置见
> `docs/implementation/UI-AUDIT-2026-09-14.md` 与
> `docs/acceptance/evidence/native-shell-copy-2026-09-14-build49.txt`。
> 上一轮（内容质量与「工作 vs 建库」边界）的校正见下方 §七 的结案块。

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
- vault：`~/Documents/Work/_vault`（纯 Markdown + git；**70 个内容页** + **16 个模板**；**16 篇决策** + 9 个主题簇页；
  `index/{projects,decisions,people,timeline,sop}.md`；**五条管线**
  `projects/{hii-affairs,it-development,huoman-community,huoman-logistics,hr}.md`）。
  索引 DB 在 vault **之外**：`~/Library/Application Support/SummitWorkbench/kb-index.sqlite`
  （篇数跟 vault 一致；块数随重建变化，`wb kb status` 为准）。
- 远端（唯一真源，私有）：`https://github.com/yifeng93/WorkKnowledge.git`，分支 `main`。
  （注意：**仓库自己的** origin 是 `git@github.com:SummitYifeng/SummitWorkbench.git`，两者不是一回事。）
- workspace_id `fb9494a4-a080-40dd-a5c3-fcc12d7dc2dd`；
  本机（Studio）device_id `0617854a-e193-4b3e-bb6d-fb5bb738937d`，角色 automation-primary，generation 1。
- 已安装的 App：`/Applications/SummitWorkbench.app` = **0.4.9 build 49**
  （`frontend_build v2026.09.14-9831168-92261f7c`、`git_revision 9831168`）；同步状态 `ready`，ahead 0 / behind 0。
  Studio 与 Air **两台机器均已接入**并实测四向同步通过。
- 最近提交以 `git log --oneline -8` 为准——**本节不再写死 hash**（历史上这里漂移过两轮）。
- **没有任何备份**（使用者明确选择不留）。旧 vault、旧远端、旧 workspace 都不可恢复：
  绝不做破坏性操作，绝不 force / reset / rebase / stash。

---

## 三、铁律

- 每次改完必须过门禁（见第四节）；不许为了「变绿」放松判据。发现判据本身写错了，要**说清楚为什么**
  并保留等价强度（例：Q1 的关键证据改成「等价入口 any-of」，同时保证两个入口都没召回时仍然红）。
- **涉及检索权重/词表的改动，必须先用真实问题量一遍再决定**（历史上有两次凭直觉的改动实测有害，
  44%→31% 被回退）。工具是 **`scripts/kb_measure.py`**：真库 4 问 × 16 期望块，**零 token**，
  并且 `--set key=value` 能直接扫权重（`--set topic_step=1.2`）、**不用改代码**。
  二值指标看不见变化，所以要连**分档**（命中 / 同篇但块不同 / 未召回）和**命中排名**一起读——
  实测 `--set conclusion_boost=1.0` 时档位一项不变、只有排名从 #13 掉到 #16。
  **不要**把 16 项二值当单一调参目标。
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
.venv/bin/python -m pytest --cov -q          # 期望 1200 passed, 1 skipped, 覆盖率 ≥80%（当前 83.85%）
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # 全过（文件数随未跟踪产物浮动，别写死）
.venv/bin/mypy                                # 期望 360 文件无问题
.venv/bin/python scripts/secret_scan.py
npm --prefix web run test:frontend            # 16 组 node 纯渲染/契约测试（73 源文件，含 UI 口径守卫）
# 真实库验收（9 题 = 4 题真调模型 Q1–Q4 + 5 题零 token R1/R2/D1/V1/S1）
.venv/bin/python scripts/kb_acceptance.py
# 已装 App 验收（4 题模型口径；只重查一题用 --only 省 token）
.venv/bin/python scripts/kb_acceptance_installed.py --only "Q1"
# 库内模板「插入即合法」守卫（**零 token**；动了 _vault/templates/ 必跑）
# keep 判据＝只做 Obsidian 的 {{date}}/{{time}}/{{title}} 替换，其余占位符原样留着也必须过 schema。
.venv/bin/python scripts/kb_check_templates.py
# 仓库种子模板（参考骨架）用 substitute 判据：先把占位符换成合法值再校验。
.venv/bin/python scripts/kb_check_templates.py --templates templates/vault --placeholders substitute
# vault 自检（**全部零 token**；动了 vault 内容、归档判据或检索时必须跑）
.venv/bin/wb vault check
.venv/bin/python scripts/kb_verify_links.py
# ⚠️ 逐字保留校验：**必须给 --materials-root**，否则只做引用的一半、不做「原件逐字在库」那一半。
#    2026-09-14 修好之前，它在这一半上是 100% 误报（全库 6 个 source 页），所以没人跑它。
.venv/bin/python scripts/kb_verify_quotes.py --vault ~/Documents/Work/_vault \
  --materials-root "/Users/yifengstudio/Desktop/当前材料"
# 检索度量（**零 token**；动了权重 / 词表 / 分块 / 主题通道就必须先跑它，别凭直觉）
.venv/bin/python scripts/kb_measure.py --no-rebuild
# 扫权重实验不用改代码（未知字段会报错，不会静默忽略）：
.venv/bin/python scripts/kb_measure.py --no-rebuild --set topic_step=1.2
# 要量「模型有没有真的引用关键块」时加 --with-model（这一层才花 token）
.venv/bin/python scripts/kb_measure.py --no-rebuild --with-model --only "Q3"
```

> **教训（2026-09-14，已经踩过一次）**：归档类判据**不能只用简化 fixture 测**。
> `kb_verify_quotes.py` 的单测 fixture 里根本没有 `## 关联` 区块，于是「剥页尾区块」那条分支
> 从未被真实页面形状覆盖，脚本在真库上误报 6/6 而单测全绿。
> 给这类判据补测试时，**fixture 要贴着真页面形状写**，并且要做**真库变异验证**
> （在真库副本上改一个字/删一行/插一个区块，判据必须立刻红）。

⚠️ **别写 `... | tail`**：管道会吞掉退出码，脚本真失败也会看着像成功（本轮踩过）。
证据落到 `docs/acceptance/evidence/`：
`kb-acceptance-2026-09-14.txt`（真实库 9 题）、
`kb-acceptance-installed-2026-09-14-build41.txt`（已装 build 41，4 题）、
`kb-measure-2026-09-14-post-seed-baseline.txt`（三线升级后检索读数 + 排名位移归因）、
`kb-measure-2026-09-14-post-first-batch.txt`（**首批入库后的回退 6/16 + 逐块归因**，本轮新增）。
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

> ✅ **内容质量与「工作 vs 建库」边界轮（2026-09-14）已结案**：
> 原作业单 `docs/implementation/NEXT-SESSION-PROMPT-CONTENT-QUALITY.md` 的 5 项交付全部完成——
> ① `_vault/conventions.md` 新增 **§0.8 内容边界** + **§4.9 项目页 / 对象页区块写法**；
> ② 5 个项目页改写（建库类内容 **0 命中**、`## 当前状态` 全部分点分层、`## 下一步` 只留工作事项）；
> ③「公司人事」重新定位为「与每个人的沟通」（目录与项目 ID `hr` 未动）；
> ④ 移出 vault 的建库事项汇总在 **`docs/implementation/WORKBENCH-MAINTENANCE-TODO.md`**；
> ⑤ App 目录过滤统一为 `repositories/ignore.py`，`Work/.obsidian` 不再漏进【项目】（build 44 已装机）。
> **不要再重做**；要接着做的是下面 2 / 4 两条（检索不足、继续收素材）。

> 🟡 **UI 优化轮的遗留（2026-09-14，build 47）**，都不阻塞使用：
> - B 类（排版）是**静态推断**：请在**窄窗口**里再看一眼项目详情双列与日志弹窗
>   （本轮已按最保守写法改：可收缩列 + `overflow-wrap` + 窄屏单列）。
> - ~~审计只覆盖 `web/src`，原生壳与首启向导未扫~~ —— **已扫并修（build 49）**：
>   更新提示的字面量缺陷、`SupervisorState.rawValue` / `compatibility` 枚举不外露、
>   英文技术词打头的错误文案、向导 3 处漏转义。守卫 `tests/unit/test_ui_copy_chinese_first.py`
>   （5 组 + 5 条变异）。⚠️ 原生壳侧**无法从装机二进制反查中文串**（`strings` 看不到 Swift
>   中文字面量），`.available` 更新提示也无法真机触发 —— 这两条是已知的**未验证**。
>   启动隔离服务必须带 `--static-dir`（否则拒绝启动）。**不要再重做**。
> - `/api/decisions` 现在没有界面入口（保留为契约 API + `index/decisions.md` 生成）；
>   确认长期不用再动 API。
> - ~~使用者写入的日志与 `hr` 页「当前状态」不一致~~ —— **已回填（2026-09-14 晚，vault `eb99c83`）**：
>   hr 线三处已对齐到「清单已返回、下一步 Overleaf」，阻塞改「当前无阻塞」；
>   分析笔记按 conventions §14 **不动**。**不要再重做**。
> - ~~自助路线「尚未实跑过一轮」~~ —— **已结案**：「追加推进日志」在真机上跑通
>   （App 自动提交 + 推送，提交 `75add13`）。
> - ~~同步横幅~~ —— **已收窄（build 48）**：一行短状态 + 一句建议 + 内部标识折叠；
>   分叉态主按钮改「处理冲突」。⚠️ 横幅只在非 ready 状态出现，装机时是 `ready`
>   ⇒ 该项**没有真机截图级证据**，只有 DOM 桩 + 真实 payload 与变异验证。

1. ~~**Air 备用机接入**~~ —— **已结案（2026-09-14）**：Air 已作为辅助设备接入完成，
   读 / 写 / 推送 / 拉取**四向实测通过**，两台机器 `/api/sync/status = ready 0/0`，
   四条判据（secondary 角色、0/0、块级出处、决策页 15 篇）全部通过。原委见
   `PLAN-WORK-KNOWLEDGE-BASE.md` §12 的「Phase 7」与「首启向导实机故障轮」。
   **不要再把它当待办**；`AIR-MACHINE-HANDOFF.md` 保留作历史作业单。
2. **已知检索不足（未解决，且本轮有回退）**：
   - ⚠️ **回退（2026-09-14 首批入库后）**：二值由 **7/16=44% → 6/16=38%**、分档 7/3/6 → **6/4/6**。
     Q2 的 `hii/clusters/relationships#关键结论` 掉出 limit=16 窗口。**已逐题 diff 定位到块**：
     新增的 `projects/huoman-logistics#阻塞` 冲到 #3——因为我在该块写了「2026-11 签约前必须**收口**」，
     而 Q2 问句是「还差哪些必须**收口**」→ **跨线假阳性**；再加新决策 `## 选项`(#10) 与四个项目页
     `## 下一步`(#8/#9/#11/#12/#13) 占席。**未改权重、未放宽判据**；也**不**为改回数字而改写新页面措辞
     （「收口」是 HII 材料既有高频词）。证据：`docs/acceptance/evidence/kb-measure-2026-09-14-post-first-batch.txt`。
     ⚠️ 排名均值 4.9→2.8 是**假象**（命中项变少、分母变小）——判断回退只看二值/分档。
     **追加 2025 两场后仍为 6/16、6/4/6（持平）** ⇒ 回退是**一次性、可归因**的，
     不是随规模持续恶化的趋势；这条支持「先不调权重」。若后续每批都继续挤出既有命中，则性质改变。
   - **上一条预言已应验**：上一轮就发现「Q2 锚点贴在窗口边缘 #16，加项目页前要留意」，本轮内容增长即触发。
   - Q3 的 `it/clusters/enrollment#关键结论` 在加「主题通道」后由「同篇不同块」变成**未召回**（净效果 6→7）。
   - 同篇多结论块互相竞争：分析笔记有 19 个「结论N」块，`max_chunks_per_note=3` 下哪 3 个进上下文
     仍偏字面相关度。
   - **结构性观察（本轮新增）**：Q2 的前 16 席里有 **6 席**是「结构相似但不同题」的块
     （5 个 `## 下一步` + 1 个 `## 阻塞`）。也就是说，**问题不在某一篇，而在「块标题撞问句措辞」**。
   - **度量工具**（2026-09-14）：`scripts/kb_measure.py` 给二值 + 分档 + 命中排名三层，零 token，
     `--set` 可直接扫权重。**当前基线**：二值 **6/16 = 38%**、分档 **6 / 4 / 6**、期望锚点自检 **16/16**。
   - **两条现成线索**：① `--set topic_step=1.2` 曾把一项「未召回」变成「同篇但块不同」而二值/排名不变
     （没有代价）；② 本轮发现块标题字面撞车是主要干扰源，可扫「块标题权重 / 项目过滤 / `max_chunks_per_note`」。
     ⚠️ **别直接改默认值**（4 题 16 项上的单点证据不够，且 `Weights.topic_step` 注释写明「不能压过正文相关度」）：
     先用脚本扫、把配置与读数记进 PLAN，再决定。
3. ~~飞书授权缓存观测~~ —— **已结案，不要再查**。`~/Library/Application Support/…/feishu-auth-state.json`
   只是 OAuth `state` 的暂存表（`_STATE_TTL = 600s`），重启后为空是正确行为；界面徽标读的是 vault 内的
   `_signals/feishu-auth.json`（持久）。结论与证据见 PLAN §12「收口轮」第 2 节。
4. **首批素材已入库（2026-09-14），三线内容仍很薄——继续收素材**：社群 / 后勤 / HR 各入库 1 批。
   规范已通过第一次实战检验（粒度与落点**未需修正**；三条采集习惯问题见 `SEED-MATERIAL-SPEC.md` §10）。
   **当前缺口（下一步该收的）**：
   - 社群：**2025 两场活动的一手复盘**（2026-06-07 已有，且已把方法论升级为「有效 / 需调整」）；
     社群构想 / 框架类原件；6/7 方案引用的《活动筹备与执行方案》《酒店备选清单》。
   - ⚠️ **需使用者明确一件事**：6/7 复盘要求「将来继续让学员做，需要给出更完善的执行指南，
     **而不是全部交出去**」——**下次下午场是否仍由学员主导尚未决定**（已搁置，不催）。
   - ⚠️ **台账里"待验证"的一条**：素材入口指南写的「你自己操作」路线**尚未实跑过一轮**——
     下一轮使用者按指南建第一页时，顺手确认：模板插入是否顺畅、`wb vault check` 是否真过、
     下次提问是否真能检索到。**若发现卡点，改的是指南与模板（不是让使用者迁就）。**
   - 后勤：物料采购进展；除 1977 酒店外的酒店 / 场地 / 供应商；行政制度类原件；
     1977 酒店的合同条款（时间线写着 2026-11 签约前收口）。
   - HR：人事制度类材料；除刘玉兰外其他团队成员的沟通。
   - 素材放 `~/Desktop/当前材料/{活满社群,活满后勤行政,HR}/`（每个目录内有 `README-放这里.md`）。
   - 库内模板 **16 个**（新增 `hr-person` / `event-retro` / `vendor` / `procurement` /
     `conversation-note` / `conversation-minutes` / `event-plan`）。
   - **已定边界（2026-09-14 决策）**：活满社群与活满后勤&行政是**两个独立部门、不跨线**——
     后勤产出（酒店/场地/供应商/物料）一律记 `logistics/`，社群只记活动与社群自身的事。
     见 `decisions/20260914-community-logistics-separate-departments#决定`。**别再提「社群管决策、后勤管执行」。**
   - **已定日志归属**：按时间的日志进各线 `logs/`（`community/logs/`、`logistics/logs/`、`hr/logs/`），不单独成线。
   - **明确不做（含将来）**：微信聊天记录、录音 / 转写（使用者已确认不会有）。
   - **判定口径（用过的）**：原件缺 `##` 小标题 → 只能整块引用（结论改放对象页）；
     一份文件混「定稿 + 过程稿」→ 结论层只用最终版、过程稿只留原件；
     使用者给「原稿 + 人工纪要」→ 纪要作分析笔记底稿、Agent 在其上补结论。
   - 入库仍走 C-lite 三件套（1 source + 1 分析笔记 / 对象页 / 事件页 + 0..N decision），规范见 `_vault/conventions.md` §11；
     幂等键 `source.ref + source.hash` **只在** `source` / `meeting-transcript` 页上判。
   - `_vault` 里的内容可以删（使用者已授权）。
   **下一窗口起手式**：读新放入的素材 → 判「原件 / 加工件」（二手提炼件不要建 source）→
   按 §3 粒度落点建对象页 / 事件页 → 跑 `wb vault check` + `kb_verify_links` +
   `kb_verify_quotes --materials-root`（**两个素材根都要给**：`当前材料` 与 `3份素材`）→
   内容再厚一些后，给三线各出一个真实问题用 `kb_measure.py` 量一遍。

---

## 八、两个必须保持同步的实现

`web/src/md.ts::mdToHtml` 与 `src/summit_workbench/webapp/views.py::md_to_html` 有明确的「同规则」契约
（标题 / 段落软换行 / 有序·无序·任务列表含嵌套 / 管道表格 / 引用 / 代码块 / `**粗体**` `*斜体*` `` `代码` ``
`[[目标|显示名]]`）。**改一边必须改另一边**，两边都有 XSS 断言（先整体转义、再套明确模式，
引号逃不出 `title` 属性）。前端测试 `web/scripts/test-md-render.mjs` 与后端
`tests/unit/test_webapp.py::test_md_to_html_*` 是同一批形状。

---

## 九、已经做完的（别再重做）

- 知识库结构（β 项目管线优先：**5 个** `projects/*.md`，主题簇页放 `<line>/clusters/`，
  对象页 / 事件页见 conventions §4.7–§4.8，没有 workstream 页）。
- 检索栈：FTS5 + trigram、问句路由器（点查/综合/回溯/决策/回顾）、多信号融合、块级 `路径#区块` 引用、
  双链扩展、同源去重；块边界为 `#`/`##`，但**文首 H1 是笔记标题、不算块边界**。
- 审批管线 7 个落点（含「知识沉淀」第 7 个 `RouteTarget`：目标页必须存在、只接受 vault 相对路径、拒穿越）。
- 决策页（API + UI + 路由契约快照）、Air 作业单、验收脚本与证据、SOP、App 内指南。
- 项目档案区块的 Markdown 渲染（build 41）：段落回流、有序列表、任务清单、嵌套、表格、
  wikilink 只显示标签；「指南」页 37 处编号列表也顺带修好。
- **种子基线轮（2026-09-14）**：三线升级为项目管线（`projects/` 2→5，删两个骨架页）；
  素材留存规范 `docs/implementation/SEED-MATERIAL-SPEC.md` + 库内模板 9→14；
  既有 HII/IT 内容修缮（补 `source`、决策字段顺序统一、Loyalty→Royalty、timeline 补双链、
  §4.4 证据补路径、IT 章节数纠错、补 `review/meetings.md`）。**别重做**。
- **首批种子入库（2026-09-14）**：社群（`activity-playbook` / 6-07 方案原件 / 6-07 事件页）、
  后勤（`hangzhou-1977-hotel` + 原件）、HR（`liu-yulan` + 原稿 + 分析）；
  模板 14→16（`event-plan` / `conversation-minutes`）。
- **2025 两场活动补齐（2026-09-14）**：`20250418-hangzhou-gathering`（Kick Off，含详细流程 Run of Show）与
  `20251216-year-end-gathering`（上海·音昱听堂）各入 source + 事件页 ⇒ **社群三场活动原件与事件页全部在库**；
  方法论页的 10 个环节里有 8 个已标出「验证于哪一场」，并把环节库提升为独立 `##` 块。**别重做**。
- **project 绑定守卫 + 自助路线端到端验证（2026-09-14）**：`wb vault check` 现在拒绝
  `project`/`projects` 里的未替换占位符（`_check_project_placeholders`）；新增
  `tests/unit/test_vault_project_binding.py`（18 条）与 `tests/unit/test_intake_route.py`（5 条端到端：
  模板留着占位符也要能解析 → 渲染后过校验 → 写进 vault 能被索引检索到 → draft 不被检索）。
  顺带修了**仓库 4/13 个种子模板插入即红**与 **`note` 模板默认 `draft`** 两个产品侧缺陷。
  ⚠️ **校验只在 CLI/Agent 侧**（`webapp/`、`workflows/` 都不调用 `validate_note`）⇒ **改校验不需要重建 App**。
  **别重做**。
- **素材入口指南（2026-09-14）**：库内 `index/sop.md` 新增「入口指南」一章（四条通道 / 建页三步 /
  不完美怎么办 / 常见错误 / 何时交 Agent），仓库 `docs/product/INTAKE-GUIDE.html` 为交互版
  （桌面另有一份副本）。**并且修掉了 16 个库内模板「插入不安全」的缺陷**（占位符未加引号 → YAML 非法），
  现全部「插入即合法」。使用者已确认工作方式＝**他自己在 Workbench / Obsidian 里操作、手记直接写 vault**。
  **别重做**。
- **2026-06-07 一手复盘入库（2026-09-14）**：260 字复盘 → `activity-playbook` 新增
  `## 复盘教训（跨场次累积）`（6 条教训）、设计理念第 4 条按复盘修正、6/7 事件页复盘区补齐、
  `## 可复用流程` 由 7 步扩到 10 步；规范 §3.1 场景表**新增「办完活动之后的复盘」并标为价值最高**。
  2025 两场的一手复盘仍缺。**别重做**。

---

- **内容质量与「工作 vs 建库」边界轮（2026-09-14）**：`conventions.md` 新增 §0.8（内容边界）与
  §4.9（项目页 / 对象页区块写法）；5 个项目页删净建库类内容并改成 `## 当前状态` 分点分层、
  `## 下一步` 只留工作事项（「下一步」只从材料 / 决定提炼，不推断）；「公司人事」重新定位为
  「与每个人的沟通」（`title` / `summary` / `aliases` / 正文，目录与项目 ID 未动），
  `hr/clusters/` 四个待建主题及 `index/projects.md` / `README.md` 同步删除；
  App 目录过滤统一为 `repositories/ignore.py`（点开头 + 机器目录名 + 下划线前缀），
  `Work/.obsidian` 不再出现在【项目】（build 44 已装机）。
  **移出 vault 的建库事项**见 `docs/implementation/WORKBENCH-MAINTENANCE-TODO.md`。**别重做**。
- **UI 优化轮（2026-09-14，build 47）**：按使用者 5 个选择题执行——删【决策】页签、
  今日页改上下两块、日志弹窗勾选一项一行、全局「中文优先 / 英文 ID 进 hover」口径、
  A/B/C 三类问题一起处置（逐条明细见 `docs/implementation/UI-AUDIT-2026-09-14.md`）。
  新增前端守卫 `web/scripts/test-ui-language.mjs`（5 条变异验证）；后端新增
  「信号标题用中文显示名」用例。⚠️ **真机真实数据验证抓出两个审计（只覆盖 `web/src`）
  看不到的问题**（`workflows/brief/collect.py` 拼项目 ID、`briefSourceLabel` 没剥 `#区块`）——
  以后这类轮次**必须**真机 + 真库再跑一遍。**别重做**。

## 十、怎么开始

1. 读第一节列的文件，`git log --oneline -8` 看最近改动。
2. 跑一遍第四节的完整门禁，确认起点是绿的（应当全绿）。
3. 问使用者这次要做哪一条（第七节的 1–2、4，或他新提的问题；第 3 条已结案）。
   如果是他报的界面/交互问题，按「先定位根因 → 修共享实现而不是就地打补丁 → 补测试与变异验证 →
   真实数据验证 → 重建安装 → 告诉他刷新」这套走。
4. 需要动 App 代码/界面时，记得最后一定要**重建并安装**，否则他看不到；并提醒 TCC 权限弹窗与 ⌘R 刷新。
