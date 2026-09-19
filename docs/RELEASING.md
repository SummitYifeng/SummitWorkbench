# SummitWorkbench macOS 发布

## 当前本地交付状态（2026-09-19，本地 main）

> **2026-09-17 边界校正**：下方关于 `kb_acceptance*.py`、本地 SQLite/FTS/BM25 和第二大脑本地问答的内容属于历史发布证据；这些脚本与实现已退役，当前发布门禁不再执行它们。语义检索由 SummitKnowledge 负责。

本轮发布产物由提交 `2d1cf3a` 构建，完成 Dulwich `1.2.15` API/类型迁移与 CI 手动触发收窄。
`tests/integration/test_packaged_app.py` 已随发布脚本通过；前端身份为
`v2026.09.19-6550855f`。本地完整门禁为 **1266 passed / 1 skipped**、覆盖率 **84.04%**，
vault 只读门禁 86 篇全部通过；跨端回归闸门仍需用户明确确认一次临时写入与极小模型费用后运行。
以下历史发布记录保留原结论；正式 DMG 的发布身份仍以对应 `release-metadata.json` 为准。

本机与 `dist/` 的对应关系（`dist/` 只保留最新一份）：

| 项 | 值 |
| --- | --- |
| 装机包 | `/Applications/SummitWorkbench.app` = build `2026091917`（安装后 smoke 通过） |
| 本次产物 | `dist/releases/0.4.9/arm64/`（App + DMG + SHA256SUMS + release-metadata + SBOM + test-manifest） |
| App SHA-256 | `b253f8c701f7d43b591a2dcff98f23ff669fd49c3f8e94f228a791ecb0449671`（见 metadata） |
| DMG SHA-256 | `52468c18e6879066a96265e01c0b6be7c75a51b9f23d09d92972f39c2d99be2b` |
| 本机测试基线 | `pytest -q` → **1266 passed, 1 skipped**；`--cov` → **84.04%**（门槛 80%） |

本轮契约改动：`meeting-note` 由九区块减为八区块（不再生成 `## AI 建议`）；决策页新增「只记业务结论」硬规则与机器守卫 `scripts/kb_check_decision_hygiene.py`。
本轮界面调整：设置页主区只留 工作区 / AI 模型 / 飞书 三张卡（每张一行），「自动化与更新」「模型参数（只读）」移入「高级与维护」折叠区（见 `docs/DESKTOP_APP.md`）。

> 历史 `dist/releases/*`（17 套，约 1.9G）已按使用者要求整体清理；需要旧产物请从
> 对应 `git_commit` 重新执行 `BUILD_NUMBER=<n> ARCH=arm64 scripts/release-macos.sh` 重建。

本轮交付里与使用者直接相关的两处行为变化（改版时要一起维护）：

1. **原生壳恢复 Dock 图标**：`Info.plist` 的 `LSUIElement=false` + `AppDelegate` 用
   `.regular`；`WB_DOCK_ICON=0` 可退回旧的菜单栏模式（见 `docs/DESKTOP_APP.md`）。
2. **模型侧逐能力显式参数**：新增 `digest` 能力；`max_output_tokens` 是「思考 + 答案」
   共用预算，抽取/摘要/分类类任务 `thinking="disabled"`（见 `config.example.toml` 与设置页
   「模型参数（只读）」卡片）。

当前 v0.4.4 build 9 的本地内部包已经完成发布验证。它是 arm64、M2+、ad-hoc 的
`INTERNAL-DEV` 包，不是 Developer ID/notarized 公网发行包。发布结论依据本地门禁和本机交互验收；
日常远端质量门（`.github/workflows/ci.yml`）永久只接受 `workflow_dispatch` 手动触发；push 和 PR 不会自动运行。发布或合并前先运行 `scripts/pre-push-gate.sh`，需要远端复核时再使用 `gh workflow run ci.yml --ref main`。

tag 触发的 `.github/workflows/release.yml` 曾在 `v0.4.3-rc.3`–`v0.4.3-rc.5` 上成功运行；随后账户
用完免费 Actions 额度且没有有效支付方式，`v0.4.3` 与 `v0.4.4` 的 tag 运行被平台拒绝启动。仓库迁移到
`SummitYifeng` 组织后额度已恢复，并已用 `v0.4.4-rc.1` 实跑验证：签名 DMG、`update-feed.json`、
SBOM、SHA256SUMS 全部产出，作为 **prerelease** 发布到公开 Updates 仓库，`latest` 保持 `v0.4.2`
不变（rc 渠道不污染 stable）。自动发布链路因此可用；日常发布仍可继续使用本文件的本地脚本。

> ⚠️ **2026-09-19 同一问题复发**：远端 CI 再次因账单停摆 —— `main` 最近 3 次推送
> （run #308 / #309 / #310）的**四个 job 全部没有启动**，注解为
> `The job was not started because recent account payments have failed or your spending
> limit needs to be increased`。也就是说 **CI 的红不是代码问题，远端质量门当前完全失效**，
> 唯一在守门的是本地门禁（`pytest` / `ruff` / `mypy` / `pre-push` 钩子）。
> 恢复需在 GitHub → Settings → Billing & plans 处理支付方式/额度；在那之前
> **不要用「CI 绿」当作合并依据**。

## 内部/个人自用包（仅 M2+ Apple Silicon）

发布脚本要求显式 build number，只构建 arm64，并生成名字和 App 界面均标明
`INTERNAL-DEV` 的 ad-hoc 包。不需要 Apple Developer ID、notarization、Intel 或 Windows：

```bash
BUILD_NUMBER=123 ARCH=arm64 scripts/release-macos.sh
```

产物包含 App、DMG、`SHA256SUMS`、`release-metadata.json`、`SBOM.json` 和 notary
不适用摘要。`INTERNAL-DEV` 只用于内部/个人自用、离线启动 smoke 和包内容检查。

## 构建与验证

不需要准备证书或账号：

```bash
BUILD_NUMBER=456 ARCH=arm64 \
scripts/release-macos.sh
```

最近一次产物位于：

`dist/releases/0.4.9/arm64/SummitWorkbench-0.4.9-arm64-INTERNAL-DEV.dmg`（build 2026091917）

认包请以该目录下的 `release-metadata.json`（含 `git_commit` 与 `app`/`dmg` 的 SHA-256）
与 `SHA256SUMS` 为准，或装完后看设置页的 build 号；**不要凭 DMG 文件名**（文件名不含 build 号）。
下面这一节保留 build 36–50 的历史账目，其产物已在 2026-09-18 的清理中移除。

历史记录（build 50，产物已清理）：`dist/releases/0.4.9/arm64/…dmg`，
SHA-256 `5fcd183f7b6e8dea2b73cc5baef1000fd1aa9ed03d930c8cdd855fc7ba86888b`，
版本 `0.4.9`、构建来源提交 `02a59c4`（把原生壳界面文案抽成纯函数 `UICopy`，
加上功能单测与变异验证），对应前端 build identity 为 `v2026.09.14-02a59c4-92261f7c`。

各轮的账（2026-09-14 按各自 `release-metadata.json` 逐个复核）：

| build | 提交 | 内容 |
| --- | --- | --- |
| 36 / 37 | `f202d3e` | 检索修复 + 知识沉淀落点（37 是刷新 distribution 元数据后的重建） |
| 38 | `6ba2f60` | 「决策」页 |
| 39 | `1ba837d` | Q1 主题通道 |
| 40 | `425dff3` | 回答截断重试 + 指南补齐 |
| 41 | `288f13d` | 项目档案区块渲染真 Markdown |
| 42 | `70f6753` | 逐字保留校验真库 6/6 误报 + `sources/read` 空值/仅区块 500 |
| 43 | `73d495a` | Air 首启向导 `~用户名` 崩溃 + 向导错误被 WebKit 盖掉 |
| 44 | `d5fb5c3` | 统一目录忽略规则 ⇒ `Work/.obsidian` 不再出现在【项目】（三处遍历共用 `repositories/ignore.py`） |
| 45 | `bb02cfc` | UI 优化轮主体（删【决策】页签 / 今日页上下两块 / 中文优先口径）。⚠️ **这个包已不在本机**：准备 build 46 时误 `rm -rf dist/releases/0.4.9`，把 b45 的产物一并删掉了；代码仍可通过提交 `bb02cfc` 复现 |
| 46 | `5437ceb` | 简报防停摆标题改用档案中文显示名 + 修 ruff E501 |
| 47 | `70c3303` | 简报出处标签先剥 `#区块` 锚点 + 项目自身页面引用不重复显示项目 ID |
| 48 | `d4bf2aa` | 同步横幅收窄（一行短状态 + 建议句 + 内部标识折叠）；分叉态主按钮改「处理冲突」 |
| 49 | `9831168` | 原生壳 + 首启向导文案口径（更新提示字面量缺陷、`rawValue`/`compatibility` 枚举不外露、英文技术词进括号、向导 3 处漏转义） |
| 50 | `02a59c4` | 界面文案抽成纯函数 `UICopy`（更新提示 / 服务状态中文名）+ 原生功能单测 + 变异验证（**当前装机**） |

> ⚠️ 本文件上一版把 **build 38 的标题配了 build 37 的 SHA-256**（`54b0b912…` 实际属于 b37）。
> 上表按每个 build 自己的 `release-metadata.json` 重新核对，是本轮的修正。

旧构建按仓库既有先例移到 `dist/releases/0.4.9.superseded-b<NN>/`，脚本拒绝覆盖已存在的发布目录。
并已内置飞书默认凭据（`REQUIRE_BUNDLED_FEISHU=true`，凭据与 0.4.8 包逐项一致）。发布目录同时包含
`SHA256SUMS`、`release-metadata.json`、`SBOM.json`、`notary-log.json`、`test-manifest.json`
和本地验证摘要。`test-manifest.json` 的 `checks` 列出本次构建真跑过的 13 项门禁
（ruff / mypy / pytest / 路由契约 / 前端契约 / 前端构建 / 打包 server / Swift 编译 / 严格签名 /
离线 smoke / 打包集成 smoke / DMG 校验和）。

**0.4.9 的验证（2026-09-14，已安装 App 实跑）**

- 版本一致性：`/api/version` 报 `server_version=0.4.9`、`build=43`、`git_revision=73d495a`、
  `frontend_build=v2026.09.14-73d495a-4d072dbb`（build 43 实测）。
  ⚠️ 升级版本号后必须跑一次 `uv pip install -e . --no-deps` 刷新 **venv 里的 distribution 元数据**，
  否则打包出的 server 会在诊断里报旧版本号（`server_version` 来自 `importlib.metadata`，不是 `pyproject`）。
- 检索（R2 块边界）：app 自己回答「HIC 当前的 Royalty 完整计算公式」时，检索轨迹里出现
  `hii/sources/20260912-hii-hic-ip-overview#三、授权关系…`、`#十七、一句话总览` 这类**原件一级章节锚点**——
  在 0.4.8（只按 `##` 切块）里这些块根本不存在。
- 检索（验收题）：app 自己回答「Danny 来华目前还差哪些必须收口？下一步谁做什么？」，
  逐条给出 P0/P1/P2 并引 `hii/visits/danny-kim-2026-09#未决问题`、`#关键结论`。
- 审批落点：已安装前端产物内含新落点「知识沉淀」（`知识沉淀` / `knowledge-note` / `sink_target` 均命中）。
- 第二大脑验收（build 41，2026-09-14 实跑）：`scripts/kb_acceptance_installed.py` 4 题模型口径
  **全部合格**；真实库 `scripts/kb_acceptance.py` 9 题（4 题真调模型 + 5 题零 token）**全部合格**。
  证据见 `docs/acceptance/evidence/kb-acceptance-installed-2026-09-14-build41.txt`。
- 缺陷修复实测（build 42）：`GET /api/sources/read` 的空值与「只有 `#区块`」由 **500 → 400**，
  越界路径仍 400、正常路径仍 200；逐字保留校验在真库上由 6 条误报 → 0 条。
  证据见 `docs/acceptance/evidence/kb-round-2026-09-14-verbatim-and-sources-read.txt`。
- 首启向导实测（build 43）：在**隔离 `HOME`** 下让已安装产物进首启模式打
  `/api/onboarding/remote/stage` —— `~nosuchuser/…` 得 **400 `invalid_path`**（可读文案），
  `~/Documents/Work/_vault` 得 **409 `target_parent_missing`**（说明 `~` 已解析成功）。
  证据见 `docs/acceptance/evidence/onboarding-air-2026-09-14.txt`。
- 目录过滤实测（build 44，2026-09-14 真库真机）：`GET /api/projects`（`/api/state` 的 `projects`）
  只列出 5 条 vault 档案线程（`hii-affairs` / `hr` / `huoman-community` / `huoman-logistics` /
  `it-development`），**`.obsidian` 已不出现**；同一进程下 `GET /api/projects/view?name=hr`
  返回的 `## 当前状态` 已是有序列表块、正文里不再有「素材放 / 已示范一次 / 建对象页」这类建库内容。
  变体验证见 `tests/unit/test_ignore_dirs.py`（去掉点开头判据 ⇒ 4 条红）。
- 原生壳文案的功能单测（build 50）：`scripts/test-native-automation.sh` 现在跑两套
  （automation + UI copy）；3 条变异验证全部让脚本以 **133** 退出并给出中文断言消息。
  ⚠️ 这类文案是**短中文字面量（≤15 字节）**，Swift 会 small-string 内联 ⇒ **二进制搜不到**
  （校准：「关闭」「确定」「取消」也是 0 命中，而 18 字节的「复制诊断信息」能查到）。
  **不要再拿 `strings` 去验证它们**，见证据文件 §5.1。
- 原生壳 + 向导实测（build 49）：**隔离 `HOME` 启动已安装的打包服务**并 GET 受限 app 的 `/`
  （首启向导），核对中文兼容性映射 / 短标识 / 3 处转义全部在、枚举直贴为 0。
  ⚠️ 必须带 `--static-dir`，否则服务拒绝启动。证据见
  `docs/acceptance/evidence/native-shell-copy-2026-09-14-build49.txt`（含「原生壳侧无法从
  二进制反查中文串、`.available` 更新提示无法真机触发」两条**未验证**的如实标注）。
- 同步横幅实测（build 48）：横幅只在**非 ready / 非 unconfigured** 状态出现，装机时本机是
  `ready`（横幅隐藏）⇒ 无法在真机上直接看到，因此这一项的证据是
  `web/scripts/test-sync-render.mjs`（DOM 桩 + 真实形状的 payload：`local-ahead` 与
  `diverged-protected`）与**变异验证**（把 label/value 网格放回可见区 ⇒ 红；把分叉态主按钮
  改成次要 ⇒ 红）。装机包内已核对：`sync-row` / `sync-state` / `sync-hint` /
  `sync-actions-inline` 在，`sync-title` 与旧的置中按钮排**为 0**。
- UI 优化轮实测（build 47，2026-09-14 真机）：
  - **已装包产物核对**：`Contents/Resources/web/static/assets/index-*.js|css` 里 `bf-stack` /
    `log-proj-name` / `settings-ids` / `sync-more` 均在，`bf-grid` / `view-decisions` /
    `tab-decisions` / `minmax(160px, 1fr)`（旧的窄网格）**均为 0**；
    `build-meta.json` 的 `git_revision = 70c3303`、前端 `v2026.09.14-70c3303-b241b9ac`。
  - **真实数据渲染**：用真库 + 当日快照 + 真项目名跑 `briefCardHtml`，**可见文本里 5 个项目 ID
    0 命中**、无 `.md` / `sources/` 路径残渣；会议区在待办区之前、容器是 `bf-stack`。
    ⚠️ 这一步抓出了两个**审计（只覆盖 `web/src`）看不到**的问题：后端信号标题里带项目 ID
    （`collect.py`），以及 `briefSourceLabel` 没剥 `#区块` 锚点——都已修并补测试。

### ⚠️ 构建前必须先提交（否则 `git_commit` 会指错）

`release-metadata.json` 的 `git_commit` 与前端 `frontend_build` 都取自**构建那一刻的 HEAD**。
2026-09-14 实测踩到：先把修复写完但**没提交**就构建，产物里的 `git_commit` 指向的是一个
**不含该修复**的提交（当时的 `c8869c1`）。正确顺序是：

1. 先提交代码（含测试）；
2. 再构建 —— 产物 stamp 才等于该代码提交；
3. 最后单独提交文档（把 build 号 / SHA 写进本文件）。

那次脏 stamp 的产物已按先例移开（`dist/releases/0.4.9.superseded-b42-dirtystamp/`），
并用同一个 build 号重建，避免留下一个「装了修复但对不上提交」的包。
另注：构建会重新生成 `src/summit_workbench/webapp/static/` 里的前端产物，它内嵌 `git_revision`，
所以**每次构建后这些文件都是脏的**，应与当轮的文档一起提交。

脚本会执行临时目录构建、ad-hoc 签名、DMG、checksum、SBOM、动态端口离线 smoke 和
完整性验证，不会访问飞书或 Apple 网络服务。

## 内置飞书凭据（分发给同事的构建必读）

分发给同事的 DMG 必须**内置飞书默认凭据**，否则同事装完点「授权飞书」会失败：飞书
`authen/v2/oauth/token` 强制要求 `client_secret`（PKCE 的 `code_verifier` 只是可选增强，
不能替代它），而分发包没有可代持秘密的后端。构建方式：

```bash
REQUIRE_BUNDLED_FEISHU=true \
WB_FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx \
WB_FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
BUILD_NUMBER=456 ARCH=arm64 \
scripts/release-macos.sh
```

- **本机重建时凭据从哪来**：从**上一个含内置凭据的包**里取证，不要手抄、不要落进仓库。
  已安装的 App 或上一次的发布目录都行：

  ```bash
  # 1) 旧发布目录要先移开（脚本拒绝覆盖已存在的同名发布目录）
  mv dist/releases/0.4.9 /tmp/swb-releases-0.4.9-superseded
  # 2) 从包内 feishu-defaults.json 生成 0600 临时 env 文件（值不落日志）
  umask 077; python3 - <<'PY' > /tmp/wb-feishu.env
  import json,shlex
  d=json.load(open('/Applications/SummitWorkbench.app/Contents/Resources/feishu-defaults.json'))
  for k,v in [("WB_FEISHU_APP_ID",d["app_id"]),("WB_FEISHU_APP_SECRET",d["app_secret"]),("WB_FEISHU_REDIRECT_URI",d.get("redirect_uri",""))]:
      if v: print(f"{k}={shlex.quote(v)}")
  PY
  chmod 600 /tmp/wb-feishu.env
  set -a; . /tmp/wb-feishu.env; set +a
  ARCH=arm64 BUILD_NUMBER=<n> REQUIRE_BUNDLED_FEISHU=true scripts/release-macos.sh
  rm -f /tmp/wb-feishu.env
  ```

  漏了这两步会在**打包阶段**才失败：`✗ REQUIRE_BUNDLED_FEISHU=true 但缺少 WB_FEISHU_APP_ID /
  WB_FEISHU_APP_SECRET`（前面几十分钟的测试与 PyInstaller 全白跑）。
  构建前还要 `uv sync --extra dev --extra web --extra packaging`，否则缺 PyInstaller。
- `scripts/build-macos-app.sh` 在**签名之前**把这三个值写成
  `Contents/Resources/feishu-defaults.json`（0600）。写在签名之后会破坏 ad-hoc 签名。
- 只给 `WB_FEISHU_APP_ID` 或只给 `WB_FEISHU_APP_SECRET` 会直接构建失败；`REQUIRE_BUNDLED_FEISHU=true`
  时两者缺一即失败（避免发布出「同事无法授权」的包）。
- `WB_FEISHU_REDIRECT_URI` 可选，默认 `http://localhost:8765/callback`，须与飞书开放平台
  「安全设置 → 重定向 URL」登记的完全一致。
- 远端发布走 `.github/workflows/release.yml`：`WB_FEISHU_APP_ID` 取自仓库 **variable**
  `WB_FEISHU_APP_ID`（非秘密），`WB_FEISHU_APP_SECRET` 取自 **secret**
  `WB_FEISHU_APP_SECRET`（发布 environment 下），二者缺失会让构建步骤失败。
- 密钥永不进版本库：`build/`、`dist/` 均在 `.gitignore` 中，仓库内不存在
  `feishu-defaults.json`；`scripts/secret_scan.py` 与 `verify-macos-release.sh` 的通用扫描
  覆盖其他所有包内文本文件，只有这一个文件被**显式**列为例外并改为结构化校验
  （只校验非空字段，不打印值）。

**这是一处明示的安全取舍**：拿到 DMG 的人都能提取该 app_secret（应用级凭证），可据此以应用
身份调用飞书 API、读取该应用已授权范围内的数据。仅在「内部自建应用 + 信任圈子」前提下可接受。
若要消除，需要把令牌换取搬到管理员自建的后端代理（app_secret 只留在服务端）。

未内置凭据的构建（开发/CI 质量门）仍可用 `~/.config/summit_workbench/config.toml` 的
`[feishu]` 表 + Keychain 手工配置；运行时优先级始终是「显式配置/Keychain > 内置默认值」。

## 用户安装与卸载

把对应架构的 DMG 拖入 `/Applications`，首次启动后按图形化向导新建或连接 workspace。
同事的完整首次流程只有三步：**新建/连接工作区 → 粘贴 DeepSeek API Key → 点「授权飞书」**
（前提是管理员已在飞书开放平台把该同事加入应用「可用范围」）。

### 升级后第一次打开要允许访问「文稿」

vault 建在 `~/Documents` 下，而 `~/Documents` 是 macOS 的 **TCC 保护目录**。内部包是
**ad-hoc 签名**，每次构建的签名都不同，macOS 因此把「换了新签名的 App」当成新应用：
升级安装后**第一次**读取 vault 时，系统会弹一次
「"SummitWorkbench" 想访问「文稿」文件夹中的文件」，必须点**允许**。

这一步没法绕过也没法预授予（这是 TCC 的设计）。**没点之前，界面会表现为问答/首页一直转圈**：
服务本身是活的（`/api/version` 秒回），但任何要读 vault 的接口都会一直等。
若误点了「不允许」，去 **系统设置 → 隐私与安全性 → 文件与文件夹**（或「完全磁盘访问权限」）
里为 SummitWorkbench 打开再重试。2026-09-13 装 build 22 时实测踩到，详见
`docs/acceptance/OPEN-VERIFICATION-ITEMS.md` §U.4。
升级替换 App 不删除 profile、vault 或 Keychain；删除 App 也不会删除用户数据。若要
清理本机数据，须在 App 外另行备份并明确删除 `~/Library/Application Support/
SummitWorkbench`、日志目录和用户选择的 vault，不能把卸载 App 当成数据删除操作。
