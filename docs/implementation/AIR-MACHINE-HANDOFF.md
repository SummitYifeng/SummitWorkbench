# Air 备用机接入作业单（Studio → Air）

> 目的：把**这台 Studio**（主设备）已经跑通的工作知识库，接到**另一台 Mac（Air，备用设备）**上。
> 面向操作者，照着填、照着点即可；具体按钮含义见 `docs/product/WEB_USAGE_GUIDE.md`
> 的「我想同步到别的设备」。本作业单只补两样东西：**这一对机器要填的真实值**，和**装完怎么算合格**。

---

## 0. Studio 侧当前状态（2026-09-14，已核实）

| 项目 | 值 |
| --- | --- |
| App 版本 | `0.4.9`（build **43**，`frontend_build = v2026.09.14-73d495a-4d072dbb`） |
| 工作区 id | `fb9494a4-a080-40dd-a5c3-fcc12d7dc2dd` |
| Studio device id | `0617854a-e193-4b3e-bb6d-fb5bb738937d` |
| 主设备声明 | 就是 Studio，generation **1** |
| vault 路径 | `~/Documents/Work/_vault` |
| 远端仓库 | `https://github.com/yifeng93/WorkKnowledge.git`（私有） |
| 同步状态 | `ready`，**ahead 0 / behind 0**（SOP 定稿那次提交已推上去） |
| 内容规模 | vault 内 **53 个内容页**（另有 9 个 `templates/*.template.md` 不计入）；含两条管线主页 + 8 个主题簇页 + **15 篇决策** |

**Air 要克隆的就是上面这个远端**——所以 Air 一旦连上，看到的就是已经收口的知识库，不是半成品。

---

## 1. 在 Air 上要填的四个值

首次打开同一个 App 会直接进连接向导，选「**从另一台 Mac 克隆**」，然后：

| 向导字段 | 填什么 |
| --- | --- |
| 私有 HTTPS 仓库地址 | `https://github.com/yifeng93/WorkKnowledge.git` |
| 目标文件夹（**必须还不存在**） | `~/Documents/Work/_vault`（Air 上不要提前建这个目录，也不要把旧 vault 放这儿） |
| GitHub 用户名 | `yifeng93` |
| 访问令牌（PAT） | 一个对该仓库有 **Contents: Read and write** 的 token（细粒度 token 就够；不要用 classic 的全权 token） |

> 只接受 `https://`。`git@…` 和 `http://` 会被当场拒掉，这是有意的。
> PAT 只用于本次连接，确认后存进系统钥匙串的 workspace 级条目，**不写进仓库、不写进草稿、不回显**。

### ⚠️ 三条踩过的坑（2026-09-14 实机验证）

1. **先建父目录 `~/Documents/Work`，但不要建 `_vault`。** 克隆要求目标 vault 的**父目录已存在**
   （`stage_remote_clone` 里的 `target.parent.is_dir()`），否则会报
   `目标 vault 的父目录不存在`。父目录建好、`_vault` 留给向导创建。
2. **目标文件夹写 `~/Documents/Work/_vault` 或绝对路径都行**（build 43 起）。build 42 上如果写成
   **`~用户名`**（例如 `~yifengstudio/…`）而 Air 上没有这个用户，会直接崩、且界面只显示一句英文
   「The string did not match the expected pattern.」——那是**旧版的一个真 bug**，build 43 已修：
   现在会给一句能看懂的 400 文案。（绝对路径在任何版本上都安全。）
3. **PAT 粘贴后把光标移到末尾按一下 delete 再提交**（去掉从 GitHub 页面复制时带上的换行/空格）。
   build 43 起前后端都会 strip，但养成这个习惯没坏处。

---

## 2. Air 上的操作步骤

1. **装 App**：把 Studio 上这一份装到 Air（同一个 DMG：
   `dist/releases/0.4.9/arm64/SummitWorkbench-0.4.9-arm64-INTERNAL-DEV.dmg`，
   build **43**，SHA-256 `9ca464c920dd4a391364cd62f670f5eb4ce4c15b48c8d8dd6cf362caf9196219`）。
   **DMG 文件名里没有 build 号**，而第 3 节要求「两台装同一个 build」——所以到 Air 上先核一眼
   SHA-256（`shasum -a 256 <那个.dmg>`），或装完在「设置」里确认 build 是 **43**，别只认文件名。
   内部 ad-hoc 签名，没有公证：第一次打开若被拦，右键「打开」→ 确认一次即可。
2. **首次启动** → 向导选「从另一台 Mac 克隆」→ 填第 1 节的四项 → 点「**连接并检查**」。
   通过后会显示工作区短码与兼容性（此时还没正式落盘，可改地址重来）。
3. 点「**确认并开始使用**」→ 向导第 2 步：粘贴 **DeepSeek API Key** → 「连接并验证」。
4. 第 3 步：点「**一键授权**」连飞书（飞书应用凭据已内置在 App 里，不需要手填 app_id/secret）。
5. 第 4 步：「进入工作台」。

### 第一次读 vault 会弹系统权限

装的是 ad-hoc 签名包，**第一次访问「文稿文件夹」时 macOS 会弹「想访问文稿文件夹」——
必须点「允许」**，否则界面会一直转圈。这是签名方式导致的，不是故障。同理，Air 上以后每次
替换 App 后第一次读 vault 也可能再弹一次。

---

## 3. 装完怎么算合格（Air 上逐条对）

> **进度（2026-09-14）**：**已过**——向导接入（build 42 + 绝对路径）、Air 写 → 自动提交 →
> **推送成功**（vault `875f56e`）→ Studio 快进到同一提交、两端 `ready` **0/0**；
> 由此确认 **PAT 的写权限可用**（克隆只需读、推送需要写，这是此前唯一没验过的风险点）。
> **仍待逐条回报**：下面第 1、3、4 条。

1. **「设置」→「高级与维护」→「定时自动化主设备」**：本机角色应显示 **辅助设备（secondary）**，
   主设备显示的是 **Studio 的 device id**（`0617854a-…`）。
   这是自动判定的：vault 里那份主设备声明写的是 Studio，所以 Air 不会去抢。
2. **顶部「⇅ 立即同步」**：状态应为 **ready**，ahead 0 / behind 0。 ✅ **已过**（2026-09-14）
3. **问一句真问题**（「问点东西」页）：例如
   「根据之前和 HII 的沟通，当前我们达成的商标共识规范是什么？」——
   应给出商标共识条目，并引用 `projects/hii-affairs#关键结论` 这类**块级**出处，来源可点开核查。
4. **「决策」页**：应能看到 **15 篇**决策，按管线/主题/状态筛选正常。

四条都过 → Air 接入完成。

---

## 4. Air 上「能做什么 / 不做什么」

| | Air（辅助设备） |
| --- | --- |
| 读、搜索、提问、看决策台账、审批与写回、编辑 Markdown、手动同步 | **都可以**，和 Studio 一样 |
| 晨间简报 / 每周复盘 / 会议同步这类**定时自动化** | **不会自动跑**（同一时间只允许一台 Mac 跑） |
| 需要时手动跑一次 | 可以，在界面里手动触发即可 |

> 想反过来让 Air 当主设备（比如 Studio 送修或换机）：
> 「设置」→「高级与维护」→「定时自动化主设备」→ 勾选确认 → 「**接管主设备**」。
> 接管会把归属转到 Air、generation 加一，**Studio 需要重新声明或确认**——所以两边都在用时先沟通。

---

## 5. 这台 Studio 上已经替 Air 验过的部分

Air 的接入路径不是「应该能行」，而是**在 Studio 上拿真远端真凭据跑过一遍**：

- 用 workspace 级钥匙串凭据对 `https://github.com/yifeng93/WorkKnowledge.git` 做了一次真实的
  暂存克隆：**成功**，工作区标记存在，兼容性判定 **read-write**，workspace id 与预期一致。
- 用**另一个设备 id**（模拟 Air）对该 vault 判定角色 → **secondary**；
  用 Studio 自己的 device id 判定 → **automation-primary**。即第 3 节第 1 条的预期结果。
- 克隆出来的 staging 与临时目录已清理，Studio 侧工作树干净。
- **首启向导那条路本身也验过了**（2026-09-14，用**隔离 `HOME`** 让**已安装的 build 43** 进首启模式，
  直接打 `/api/onboarding/remote/stage`）：

  | 输入 | 结果 |
  | --- | --- |
  | `~nosuchuser/Documents/Work/_vault` | `400 invalid_path`：「解析不了「~nosuchuser」：这台机器上没有这个用户。…请写成 ~/… 或直接用绝对路径」 |
  | `~/Documents/Work/_vault` | `409 target_parent_missing`——说明 `~` **已解析成功**、走到了克隆预检 |

  第一条正是 build 42 上让向导只显示一句英文的那个输入；第二条印证了第 1 节的新注意事项
  「父目录得先存在」。

尚未验证的只有 Air 本机上的 GUI 点击与系统权限弹窗——那必须在 Air 上做。

---

## 6. 卡住了看这里

| 现象 | 原因 / 处理 |
| --- | --- |
| 「目标 vault 已存在，未覆盖」 | Air 上那个文件夹已经有了。删掉它（确认里面没有要留的东西）再重试，向导不会覆盖已有目录。 |
| 「私有 remote clone 需要预期 workspace id…」 | 这是内部报错，正常向导不会出现；真遇到就重开向导重来一次。 |
| 克隆报认证失败 | PAT 过期 / 权限不足 / 用户名填错。重新签一个对该仓库有 Contents 读写权限的 token。 |
| 兼容性不是 read-write | Air 上的 App 版本比工作区旧。两台**装同一个 build** 再试。 |
| 连上后界面一直转圈 | 大概率是第 2 节那个「文稿文件夹」权限弹窗没点允许。去「系统设置 → 隐私与安全性 → 文件与文件夹」补授权，或重启 App 让它再弹一次。 |
| 提示 `dirty-protected` | 本机有**没提交的手工改动**，自动拉取不动 git（脏工作树绝不自动合并）。先提交或还原，再点「⇅ 立即同步」。 |
