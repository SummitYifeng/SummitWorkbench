# SummitWorkbench 多设备与可分发产品化开发计划

> 版本：1.1
>
> 日期：2026-09-06
>
> 状态：可执行；P0-01 至 P0-13、P1-01、P1-02、P1-03、P1-04 已完成；下一工作包为 P1-05
>
> 适用基线：`v0.4.1` 之后、M3 之前
>
> 目标执行模型：Codex `gpt-5.6-luna`；每个新任务只实施一个工作包
>
> 关联文档：`DEVELOPMENT_PLAN.md`、`HANDOFF_HARDENING_P0_P1.md`、ADR 0016–0031

## 0. 这份计划怎么用

这不是方向性建议，而是可以逐包实施、逐包验收的工程计划。它解决三个具体使用场景：

1. 当前使用者在 Mac Studio 与 MacBook Air 上使用同一套知识库；
2. 同事安装同一个 SummitWorkbench App，但创建完全独立的个人知识库与工作台；
3. App 从“绑定开发者电脑的自用工具”升级为“可签名、可安装、可诊断、可升级的本地优先产品”。

### 0.1 Luna 执行协议

每个 Codex 新任务必须遵守以下规则：

1. 先完整阅读本计划、该工作包列出的必读文件和仓库根目录 `README.md`；不得只读工作包标题。
2. 运行 `git status --short`。保留用户已有改动；若目标文件存在无法安全合并的改动，停止并说明冲突，不得 reset、checkout 或覆盖。
3. 一次只实施一个工作包。不得“顺手”进入下一个工作包，不得做未列入范围的全库重构。
4. 先补失败测试或特征测试，再修改实现；安全边界必须同时有成功与拒绝路径测试。
5. 优先复用已有 `workspace_lock`、原子写、JSONL、Pydantic schema、Git 封装与前端生命周期模块，不复制第二套机制。
6. 不访问真实飞书、不使用真实模型、不修改真实 Keychain、不读写真实 `~/Documents/Work`。测试只能使用 fake、`MockTransport`、临时目录和临时仓库。
7. 未经明确要求，不 push、不发布、不替换 `/Applications` 中的 App、不注册真实 LaunchAgent、不执行真实凭据迁移。
8. 完成目标测试和全量质量门后，才能把工作包状态由 `[ ]` 改成 `[x]`，并在第 15 节实施记录中追加证据。
9. 缺少 Apple Developer 证书、第二台 Mac、真实私有远端或飞书测试账号时，完成可离线验证部分，但不得把真机门标为通过。
10. 交付回复固定包含：完成范围、用户可见变化、主要文件、测试结果、尚未验证项、下一工作包；不要只回复“完成”。
11. 工作包状态按原始实现要求、测试矩阵与验收逐项判定，不按“已有提交”或“测试全绿”自动判定完成；任一必需契约未接入生产路径时只能标为 `[~]`。

### 0.2 每包完成后的通用质量门

Python 相关工作包：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

前端相关工作包额外运行：

```bash
npm --prefix web run build
node web/scripts/verify-build.mjs src/summit_workbench/webapp/static
```

macOS App 相关工作包额外运行：

```bash
scripts/build-macos-app.sh
uv run pytest -m integration
```

只有发布工作包可以使用签名、notarization 和安装命令。普通代码包只做 ad-hoc 构建验证。

### 0.3 状态标记与 2026-09-05 基线复核

- `[x]`：实现要求与可离线验证的测试矩阵全部完成；真机门若受外部条件限制，必须在实施记录中明确写“未验证”。
- `[~]`：已有可用实现和测试，但至少一项原始生产契约、生产接线或验收仍未完成。
- `[ ]`：尚未开始，或只有不足以构成工作包交付的零散准备。

对基线 `bf734d8` 的复核结论如下；本结论覆盖第 15 节早期实施记录中的旧“完成”判定，但不改写历史提交事实：

1. 仓库为 `main = origin/main = bf734d8`，复核前工作树干净；提交 `70dfae6..bf734d8` 线性存在。
2. 当前全量质量门通过：ruff、format、mypy（240 files）、pytest（677 passed，1 skipped）以及前端 build/verify-build。测试全绿证明现有行为稳定，不等于未覆盖的产品契约已经完成。
3. P0-06 与 P0-08 保持 `[x]`。P0-07C 已收口 P0-07 的 production 缺口：active profile/runtime context、onboarding-required 受限控制面、compatibility 写门与 workspace-scoped provider 配置已接线；P0-07 现为 `[x]`。
4. P0-09C 已收口 P0-09 的 production 缺口：Dulwich HTTPS transport 使用 workspace-scoped 凭据回调，remote clone 具备 staging/marker/兼容性/确认回滚，production backend 选择改为显式注入；P0-09 现为 `[x]`。
5. P0-10C 已收口 P0-10 的复核缺口：状态持久化、真实 pending/ahead/behind、失败时 last-success 保留、统一写前保护与 commit 后 push、完整状态详情、主设备声明均已接线；P0-10 现为 `[x]`。
6. 不把上述缺口塞进一个超大的 P0-11。已按固定顺序完成 P0-07C → P0-09C → P0-10C，下一包为 P0-11A。

## 1. 已确认的现状与主要缺口

当前项目已经有可靠的领域模型、文件仓库、工作区锁、原子写、容错 JSONL、FastAPI 面板、
Swift/AppKit + WKWebView 外壳、PyInstaller 自包含服务端和较完整测试。但它仍然默认只有一位使用者、
一台电脑、一个固定目录：

| 领域 | 当前状态 | 产品化风险 |
|---|---|---|
| 工作目录 | 原生壳默认 `~/Documents/Work` | 无首次设置、无多工作区、同事安装后不知道从哪里开始 |
| 设备身份 | 无 `device_id` | 无法区分 Studio、Air 和同事电脑的写入来源 |
| 工作区身份 | 无稳定 `workspace_id` | 凭据、同步、迁移和自动化无法安全隔离 |
| 同步 | 扫描已有 Git 仓库并 ff-only/push | 不负责克隆；本机锁不能协调两台 Mac；分叉后缺少产品级保护态 |
| 自动提交 | 显式 add 路径，但 commit 提交整个暂存区 | 可能夹带用户预先暂存的其它文件；撤销可接收任意提交 SHA |
| 外部副作用 | 飞书客户端统一重试瞬时故障 | 非幂等 POST 在“服务端成功、客户端丢响应”时可能重复创建日程 |
| Web 边界 | 固定端口、无会话认证 | 端口冲突；若绑定到非 loopback 或遭跨站请求，写接口缺少保护 |
| 文件持久化 | 已有原子替换，但临时文件名固定且缺少完整 fsync | 并发、异常退出或断电场景仍可加强 |
| 凭据 | Keychain，但部分调用把秘密作为命令参数 | 进程参数可见；同一 app/account 命名不足以隔离工作区 |
| Git 运行时 | 调用系统 `git` | 全新 Mac 可能触发 Xcode Command Line Tools，App 并非真正开箱可用 |
| 自动化 | shell 脚本要求 `wb` 命令 | 只拿到 `.app` 的同事无法注册和管理定时任务 |
| 分发 | 当前架构构建 + ad-hoc 签名 | 不能作为可信外部分发包；无 notarization、DMG、发布验证与升级通道 |
| 代码组织 | `webapp/app.py`、`web/src/main.ts` 过大 | 继续扩展 onboarding、sync、settings 会显著增加回归风险 |

## 2. 产品边界与目标架构

### 2.1 必须守住的产品边界

- App bundle 是只读、无用户数据的统一程序；不得把任何人的 vault、配置、token 或日志打进 App。
- 每个知识库拥有一个稳定 `workspace_id`；同一人的 Studio 与 Air 使用相同 `workspace_id`。
- 每台 Mac 拥有不同 `device_id`；`device_id`、本机路径、日志和凭据永不经 Git 同步。
- 同事必须创建新的 `workspace_id`；不得复制当前使用者的 vault、配置目录或 Keychain 项。
- Vault 与可选项目仓库通过私有 Git remote 同步；禁止使用 iCloud/Dropbox/网盘直接同步含 `.git` 的目录。
- 凭据采用 BYOK：每位使用者在自己的 Mac 上配置自己的模型 API Key 和飞书授权。
- 第一阶段不建设 SummitWorkbench 云服务，不建立共享账号，不代管同事的 token。
- Git 同步永不使用 force push、自动 rebase、自动 stash、自动冲突覆盖或破坏性 reset。
- 网络不可用时允许本地工作并明确显示“待同步”；已确认分叉时进入受保护状态，不继续静默写共享热点文件。
- 一个工作区最多一个“自动化主设备”。Studio 可为主设备，Air 默认辅助设备；同事的 Mac 可成为她自己工作区的主设备。

### 2.2 目标关系

```text
同一个 SummitWorkbench.app
├── 你的 Mac Studio
│   ├── workspace_id = W-YIFENG
│   ├── device_id = D-STUDIO
│   └── role = automation-primary
├── 你的 MacBook Air
│   ├── workspace_id = W-YIFENG
│   ├── device_id = D-AIR
│   └── role = secondary
└── 同事的 Mac
    ├── workspace_id = W-COLLEAGUE
    ├── device_id = D-COLLEAGUE
    └── role = automation-primary（可选）
```

### 2.3 数据落点

建议统一为：

```text
~/Library/Application Support/SummitWorkbench/
├── registry.json                         # 本机 profile 索引，不同步
├── device.json                           # 本机 device_id，不同步
├── profiles/<workspace_id>/
│   ├── config.toml                       # 本机路径和非秘密配置，不同步
│   ├── sync-state.json                   # 本机同步状态，不同步
│   └── runtime/                          # 端口、实例、会话等短期状态，不同步
└── backups/                              # 配置/迁移备份，不同步

~/Library/Logs/SummitWorkbench/
└── summit-workbench.log                  # 本机滚动日志，不同步

<用户选择的 Work Root>/
├── _vault/
│   ├── .summit-workbench/workspace.json  # 随 vault 同步，唯一 workspace_id
│   └── ...                               # 当前知识库内容
└── <project repositories>/               # 可选择接入，不要求同事拥有你的项目
```

Keychain 命名必须至少包含 `workspace_id`：

```text
service = com.summitworkbench.credentials.<workspace_id>
account = llm:<provider>:<credential_name>
account = feishu:<app_id>:app_secret
account = feishu:<app_id>:refresh_token
account = git:<host>:<username>
```

任何 schema 示例和诊断输出只允许出现 Keychain 引用，不得出现秘密值。

### 2.4 工作区兼容契约

`_vault/.summit-workbench/workspace.json` 初始字段：

```json
{
  "schema_version": 1,
  "workspace_id": "uuid-v4",
  "display_name": "Yifeng Workbench",
  "created_at": "2026-09-05T00:00:00Z",
  "min_reader_version": "0.5.0",
  "min_writer_version": "0.5.0"
}
```

规则：

- `workspace_id` 创建后不可修改；复制 App 不会复制它，连接既有 vault 时从 marker 读取。
- App 低于 `min_reader_version`：拒绝打开并提示升级。
- App 可读但低于 `min_writer_version`：只读打开，禁止写入。
- 未知更高 `schema_version`：只读保护，不猜测字段语义。
- marker 缺失的旧 vault 只能通过显式“升级现有工作区”生成 marker；升级前先备份，不静默生成。
- `api_protocol` 继续只表示原生壳与本地服务的兼容性，不替代 workspace schema。

## 3. 优先级、依赖和发布门

### 3.1 工作包总表

| 顺序 | 工作包 | 优先级 | 依赖 | 复杂度 | 状态 |
|---:|---|---|---|---|---|
| 1 | P0-01 Git 自动提交与撤销信任边界 | P0 | 无 | M | [x] |
| 2 | P0-02 本地写入与自动提交事务边界 | P0 | P0-01 | M | [x] |
| 3 | P0-03 飞书重试分类与客户端生命周期 | P0 | 无 | M | [x] |
| 4 | P0-04 飞书外部动作 Outbox 与不确定态 | P0 | P0-03 | L | [x] |
| 5 | P0-05 本地 Web 边界、输入预算与错误语义 | P0 | 无 | M | [x] |
| 6 | P0-06 文件耐久性、隔离去重与锁根统一 | P0 | 无 | M | [x] |
| 7 | P0-07 Workspace/Profile/Device 领域与存储 | P0 | P0-06 | L | [x] |
| 8 | P0-08 新建/升级/连接工作区服务 | P0 | P0-07 | L | [x] |
| 9 | P0-09 可打包 Git 后端与凭据适配 | P0 | P0-01、P0-07 | L | [x] |
| 10 | P0-10 多设备同步协调器与主设备规则 | P0 | P0-02、P0-09 | L | [x] |
| 11 | P0-07C Active Profile 生产运行时收口 | P0 | P0-07、P0-08 | M | [x] |
| 12 | P0-09C 私有 HTTPS Git 与 remote clone 收口 | P0 | P0-07C、P0-08、P0-09 | L | [x] |
| 13 | P0-10C 同步状态、写边界与主设备声明收口 | P0 | P0-02、P0-09C、P0-10 | L | [x] |
| 14 | P0-11A 可恢复首次使用向导 | P0 | P0-04、P0-08、P0-10C | L | [x] |
| 15 | P0-12 动态端口、会话认证与原生生命周期 | P0 | P0-05、P0-07C、P0-11A | L | [x] |
| 16 | P0-11B 设置中心与安全 profile 切换 | P0 | P0-11A、P0-12 | L | [x] |
| 17 | P0-13 Apple Silicon 内部 DMG 分发 | P0 | P0-11B、P0-12 | L | [x] |
| 18 | P1-01 App 内定时任务与自动化主设备 | P1 | P0-10C、P0-13 | L | [x] |
| 19 | P1-02 工作区 schema 迁移、备份与回滚 | P1 | P0-07C | M | [x] |
| 20 | P1-03 后端路由/服务拆分 | P1 | P0 发布门 | M | [x] |
| 21 | P1-04 前端 feature 拆分与状态管理 | P1 | P1-03 | L | [x] |
| 22 | P1-05 诊断包、日志、隐私与可支持性 | P1 | P0-07C、P1-03 | M | [ ] |
| 23 | P1-06 CI、覆盖率门与发布矩阵 | P1 | P0-13 | M | [ ] |
| 24 | P1-07 签名自动更新 | P1 | P0-13、P1-06 | L | [ ] |
| 25 | P2-01 追加式操作事件与确定性投影视图 | P2 | P1 发布门 | XL | [ ] |
| 26 | P2-02 同步冲突解释与恢复工作台 | P2 | P2-01 | L | [ ] |
| 27 | P2-03 组织级 OAuth Broker（可选） | P2 | 明确扩展产品边界 | XL | [ ] |

复杂度说明：S 为单一小改动，M 为一个清晰模块，L 需要跨 Python/前端/原生中的两个层，XL 必须再拆成子包。

### 3.2 P0 内部发布门：允许 M2+ Apple Silicon 自用/内部试用

以下条件全部满足后，才可以把 App 发给同事：

- 表中全部 P0 工作包（含 P0-07C/P0-09C/P0-10C、P0-11A/P0-11B）通过；不得跳过收口包直接打发布包。
- 在 M2+ Apple Silicon 的干净 macOS 用户账户中，拖入 `/Applications` 后首次启动不需要仓库源码、Python、Node、`uv` 或 `wb` 命令。
- 内部 ad-hoc/unsigned-dev 完整性验证通过；不要求 Developer ID、notarization 或 stapling。
- 使用者可只通过图形界面创建自己的新工作区，完成一条 capture，重启后数据仍在。
- 新工作区中不出现当前使用者的姓名、路径、项目、Git remote、飞书 app id、模型 provider、token 或日志。
- Studio 与 Air 连接同一测试 vault 时得到相同 `workspace_id` 和不同 `device_id`。
- Studio 为自动化主设备、Air 为辅助设备；Air 不会重复生成晨间简报或周报。
- 两台设备先后编辑可正常快进同步；离线写入后恢复网络，能够 push 或明确进入分叉保护态。
- 已知分叉时不得自动覆盖任何一侧；UI 必须说明本地/远端领先状态和下一步。

### 3.3 P1 发布门：允许长期日常使用

- 定时任务完全由 App 安装、暂停、恢复和查看，不依赖 shell 脚本或源码环境。
- 工作区升级有版本检查、备份、失败回滚和双版本兼容测试。
- Python 与前端质量门进入 CI；发布产物按架构验证，覆盖率有最低门槛。
- 用户可导出脱敏诊断包；日志不包含会议正文、token、Authorization header 或模型输入。
- 已验证的签名更新通道可从前一个正式版本升级，失败不会损坏 vault。

## 4. P0 工作包：数据安全与产品化底座

### P0-01 · Git 自动提交与撤销信任边界

**目的**：系统自动提交不得夹带用户预先暂存的文件；撤销与 diff 只能操作真实的 `wb:` 单父提交。

**必读文件**：

- `src/summit_workbench/repositories/autocommit.py`
- `src/summit_workbench/repositories/git.py`
- `src/summit_workbench/webapp/app.py` 中 `/api/undo/*`
- `tests/unit/test_autocommit.py` 与 undo Web API 测试
- ADR 0027

**实现要求**：

1. 在 `GitRepo` 增加精确读取暂存路径、提交主题、提交父节点数和校验 commit 对象的方法。
2. `commit_paths` 获取 `workspace_lock(vault_dir.parent)` 后，先检查暂存区；只要调用前已有任何 staged path，返回新的可见状态 `index-not-clean`，不再 add、不 commit、不改变原暂存区。
3. add 后只检查本次目标路径是否有 staged diff；不得用“整个暂存区非空”推断本次路径有变化。
4. `message` 必须规范化为单行并以 `wb:` 开头；不合规时返回失败，不创建任意主题的系统提交。
5. `revert_commit` 的 SHA 只接受 API 历史返回的完整 40 位小写/大小写十六进制 commit id；解析为 commit 后确认：主题以 `wb:` 开头、恰有一个 parent、提交仍可从当前仓库解析。
6. 读取 touched paths、检查 dirty、执行 revert 必须在同一把锁内，消除检查与执行之间的竞态。
7. `commit_diff_text` 使用相同的 wb commit 校验；手工提交、merge commit、无效 SHA 均拒绝。
8. Web API 对“不允许撤销”返回 4xx 和稳定错误码，不再只返回 HTTP 200 + `ok:false`。
9. 所有 Git 命令参数使用参数数组并加 revision/path 分隔保护；不得拼 shell 字符串。

**必须新增的测试**：

- 仓库预先 stage `manual.md`，系统只要求提交 `inbox.md`：操作被拒绝，两个文件状态均不被改写。
- 无预先 stage 时，只提交目标路径，另一未暂存修改仍留在工作树。
- 目标路径内容未变时返回 `nothing-to-commit`。
- 手工提交 SHA、merge commit SHA、短 SHA、含选项字符的 SHA、未知 SHA 都不能 diff/revert。
- wb commit touched file 在锁内被模拟改脏时，revert 拒绝且仓库不进入 revert 冲突态。
- 正常 wb commit 可列出、查看 diff、revert，并生成反向提交。

**验收**：目标测试与全量 Python 门通过；原暂存区在任何拒绝/失败路径上字节级等价；不改动飞书或业务文件格式。

**停止条件**：如果 Git 现有调用依赖“预先 staged 后由 wb 一并提交”，先用测试证明调用点并报告，不得擅自清空或临时保存 index。

### P0-02 · 本地写入与自动提交事务边界

**目的**：一次本地业务操作的“文件变更 + wb commit”在同一个工作区临界区完成，不让两个并发操作合并进同一个 undo 提交。

**建议新增**：`src/summit_workbench/workflows/local_mutation.py`、对应单元/集成测试。

**实现要求**：

1. 定义 `LocalMutationResult`，至少包含 `operation_id`、业务返回值、changed paths、commit result。
2. 定义单一编排函数：在 `workspace_lock(vault_dir.parent)` 内执行纯本地 mutation、收集变更路径、调用 `commit_paths`。已有 repository 锁允许线程内重入，不得删除底层锁。
3. 每次操作生成稳定 `operation_id`；commit 主题格式固定为 `wb: <action> [<operation_id>]`，日志和 API 返回同一 id。
4. 迁移纯本地写端点：capture、线程日志、线程产物、线程状态、项目创建/激活/归档/改名、本地会议导入落盘阶段。
5. 网络调用、LLM、飞书操作绝不放进工作区锁。包含外部副作用的端点只把最终本地镜像/审计部分交给本 helper；外部动作由 P0-04 的 outbox 管理。
6. mutation 成功但 Git 非仓库/无变化时，业务仍成功并返回可见 commit 状态。
7. mutation 抛错时不调用 commit；若文件已部分改变，必须依赖各 repository 的原子写或显式补偿，测试锁定行为。
8. 不把 autocommit 塞进通用 repository 层，避免每次低层写都生成不可预测提交。

**测试矩阵**：

- 两个线程同时 capture，各得到不同 operation id、两个 wb commit、两条内容，无合并提交。
- 一个 mutation 失败，另一个成功：成功操作仍提交，失败操作不产生 commit。
- 非 Git vault 仍完成本地写并返回 `not-git`。
- 同一线程 repository 重入锁不死锁。
- 模拟慢网络函数并断言持锁区间不包含网络等待。

**验收**：每个迁移端点只有一个明确的本地事务入口；undo 历史能按 operation id 对应一次用户操作。

### P0-03 · 飞书重试分类与客户端生命周期

**目的**：只重试明确安全的调用，并确保 HTTP 连接在 App 生命周期结束时关闭。

**必读文件**：`providers/feishu/client.py`、`providers/_resilient.py`、飞书 task/calendar provider、FastAPI dependency 创建位置。

**实现要求**：

1. 引入显式 `RetryMode`：`safe`、`idempotency-key`、`never`；不得再根据 HTTP method 隐式重试全部请求。
2. GET 默认 `safe`；POST 默认 `never`。只有 provider 明确传入服务端支持的幂等键时，POST 才使用 `idempotency-key`。
3. 飞书任务创建已有 `client_token` 时，将该 token 一路传到 retry policy，并测试重复发送使用同一个 token。
4. 日历事件创建在未证明官方幂等能力前使用 `never`；超时或连接中断返回“结果未知”，不自动第二次 POST。
5. PATCH/DELETE 逐端点标注策略，不使用全局猜测。若重放可能改变语义，使用 `never`。
6. `FeishuClient` 实现 `close()` 和上下文管理协议；只关闭自己创建的 client，不关闭注入的测试/共享 client。
7. App 使用 lifespan 或等价资源容器复用一个受控 client，并在服务关闭时确定性释放。
8. 错误对象保留 `retryable`、`retry_after`、`result_unknown` 等机器字段；日志不得包含 token/正文。

**测试矩阵**：

- GET 遇 429/5xx/timeout 按上限重试并尊重 Retry-After。
- 普通 POST 遇 timeout 只调用一次并标记 unknown。
- 带相同 client token 的任务 POST 可重试，所有 attempt 请求体 token 相同。
- 业务 4xx/code 非零不重试。
- 自建 client 被 close；注入 client 不被误关；App shutdown 完成 close。

**验收**：每个飞书写 provider 都有显式 retry mode；代码审查中不再存在无分类的 `.post()` 自动重试。

### P0-04 · 飞书外部动作 Outbox 与不确定态

**目的**：把“本地批准”与“飞书是否真正创建成功”分开记录，避免响应丢失后重复创建会议或任务。

**建议新增**：

- `domain/external_action.py`
- `repositories/external_action_outbox.py`
- `workflows/external_actions.py`
- `webapp` 对应查询/恢复 API 与前端状态组件
- ADR `0028-external-action-outbox.md`

**状态机**：

```text
prepared -> sending -> succeeded
                    -> failed          # 已确认远端拒绝，可修改后重试
                    -> unknown         # 可能已成功，禁止自动重试
unknown  -> reconciled-succeeded
         -> reconciled-not-found -> prepared（必须由用户确认）
```

**实现要求**：

1. Outbox 使用现有 schema-versioned、容错 JSONL 基础；每次状态变化追加事件，不原地覆盖历史。
2. 每条动作至少包含：`operation_id`、`candidate_id`、`workspace_id`、kind、请求指纹、目标账号引用、状态、attempt、时间、remote id、脱敏错误。
3. 请求指纹由规范化后的业务字段计算；不得保存 Authorization、app secret、模型 key 或不必要的会议正文。
4. 用户点击 apply 时，先可靠写 `prepared`，再发网络请求；成功后写 `succeeded` 和 remote id。
5. 网络层返回 unknown 时写 `unknown`；后续重复 apply 同一 candidate 必须停止在“需要核对”，不能再次 POST。
6. 飞书会议创建必须实际使用 `candidate_id/operation_id`；若 API 无幂等字段，在描述或可检索元数据中加入最小、可识别的 WB marker，并提供核对逻辑。若 provider 不支持可靠查询，则 UI 明确要求用户人工确认。
7. `review_apply` 每个 action 分别捕获 `FeishuError`、验证错误和本地 IO 错误；单条失败/unknown 不终止同批其他动作。
8. API/UI 展示 succeeded、failed、unknown；unknown 使用高辨识提示，并提供“重新核对”“确认已创建”“确认未创建并允许重试”，最后一项需二次确认。
9. 对已 succeeded candidate 保持幂等：重复 apply 只读取 remote id，不发请求。

**测试矩阵**：

- 服务端模拟已接收但 client timeout：outbox 为 unknown，第二次 apply 的 POST 调用数仍为 1。
- 已 succeeded 的候选重复处理不再调用远端。
- batch 中一条 FeishuAPIError 不阻断后一条成功动作。
- 进程在 `prepared` 后退出，重启可见待恢复；不得静默丢失。
- outbox 坏行被隔离，其余动作仍可恢复。
- workspace A 与 B 的同 candidate id 不相互命中。

**验收**：所有远端创建型动作都可回答“未发送、发送中、成功、明确失败、结果未知”之一；不存在“异常后直接再建一次”的路径。

### P0-05 · 本地 Web 边界、输入预算与错误语义

**目的**：即便未来配置错误，也不能把无认证的写接口暴露到局域网；异常和超大输入要可控。

**实现要求**：

1. production 模式只允许绑定 `127.0.0.1` 或 `::1`；`0.0.0.0`、局域网 IP 在启动前拒绝。development 模式若显式开放，启动信息必须警告且仍要求认证。
2. 增加 Host allowlist；仅接受当前 loopback host/实际端口组合。
3. 对 POST/PATCH/DELETE 做 Origin 校验：有 Origin 时必须与当前服务同源；无 Origin 的受信原生调用仍需 P0-12 的 session token。
4. 为所有请求模型定义 `max_length`、枚举和列表上限。建议起始值：普通标题 200、URL 2048、正文 100,000 字符、批量候选 100、搜索 query 2,000。
5. 上传改为分块读取，默认单文件上限 10 MiB；超限立即停止、删除临时文件、返回 HTTP 413。文件名只作展示，不参与路径拼接。
6. 建立统一错误 envelope：`code`、`message`、`operation_id`、可选 `details`；验证失败 422、未认证 401、禁止 403、冲突 409、锁忙 423、外部服务失败 502/503。
7. 逐步淘汰 HTTP 200 + `{"ok": false}`；前端连接层同时兼容迁移期旧格式，但新端点只用 HTTP 语义。
8. `/api/ask` 的模型/检索失败不得返回 `ok:true` 或把错误 HTML 当答案。
9. CORS 默认关闭；不得用 `*` 解决本地访问问题。

**测试矩阵**：

- production 非 loopback bind 被拒绝。
- 伪造 Host、跨源 Origin、无认证 unsafe request 被拒绝；同源合法请求通过。
- 10 MiB 边界前后、超长字段、超大数组、路径型文件名均有测试。
- 锁忙、分叉、飞书失败、未知异常分别映射稳定 HTTP status/code。
- `/api/ask` 错误绝不伪装成功。

**验收**：所有现有 38 个路由有读/写分类表；每个写路由至少经过统一认证/Origin/input/error 中间层。

**38 条路由读写分类（P0-05）**：统一安全中间层覆盖下表全部路由；其中 `POST` 为写请求，
`GET` 为读取或只读预演。SSR 兼容路由保留旧页面响应，但同样经过 Host/Origin 边界。

| 方法 | 路由 | 分类 |
|---|---|---|
| GET | `/api/version` | 读 |
| GET | `/api/state` | 读 |
| POST | `/api/projects/rename` | 写 |
| POST | `/api/projects/activate` | 写 |
| POST | `/api/projects/archive` | 写 |
| POST | `/api/projects/create` | 写 |
| GET | `/api/review` | 读 |
| POST | `/api/review/decide` | 写 |
| POST | `/api/review/batch` | 写 |
| POST | `/api/review/edit` | 写 |
| POST | `/api/review/plan` | 读（POST 只读预演） |
| GET | `/api/external-actions` | 读 |
| POST | `/api/external-actions/{operation_id}/reconcile` | 写 |
| POST | `/api/review/apply` | 写 |
| POST | `/api/threads/state` | 写 |
| GET | `/api/projects/view` | 读 |
| POST | `/api/threads/logs` | 写 |
| POST | `/api/threads/artifacts` | 写 |
| POST | `/api/capture` | 写 |
| POST | `/api/tasks/complete` | 写 |
| POST | `/api/tasks/update` | 写 |
| POST | `/api/meetings/update` | 写 |
| POST | `/api/run/brief` | 写 |
| POST | `/api/run/weekly` | 写 |
| POST | `/api/ask` | 读（问答请求） |
| POST | `/api/meetings/import` | 写 |
| GET | `/api/undo/history` | 读 |
| GET | `/api/undo/diff` | 读 |
| POST | `/api/undo/revert` | 写 |
| POST | `/api/shutdown` | 写 |
| POST | `/run/brief` | 写（SSR 兼容） |
| POST | `/run/weekly` | 写（SSR 兼容） |
| POST | `/ask` | 写（SSR 兼容） |
| GET | `/review` | 读（SSR 兼容） |
| POST | `/review/decide` | 写（SSR 兼容） |
| POST | `/review/edit` | 写（SSR 兼容） |
| GET | `/review/plan` | 读（SSR 预演） |
| POST | `/review/apply` | 写（SSR 兼容） |

P0-08 追加（onboarding 服务 API，无 UI；create/upgrade/connect 均为全流程事务服务，
失败整体回滚并返回 409 + `onboarding_rejected` 稳定码）：

| 方法 | 路由 | 分类 |
|---|---|---|
| GET | `/api/onboarding/status` | 读（active / env-compat / onboarding-required）|
| POST | `/api/onboarding/preflight` | 读（POST 只读预演，结构化预检报告）|
| POST | `/api/onboarding/create` | 写 |
| POST | `/api/onboarding/upgrade` | 写 |
| POST | `/api/onboarding/connect` | 写 |

### P0-06 · 文件耐久性、隔离去重与锁根统一

**目的**：完善异常退出耐久性，避免重复隔离坏行和因自定义 vault 路径导致锁分裂。

**实现要求**：

1. `_atomic.py` 使用目标同目录内的唯一临时文件；写入后 flush + `fsync(file)`，`os.replace` 后在支持的平台 `fsync(parent directory)`。
2. 替换时尽量保留原文件 mode；异常路径清理本次临时文件，不删除其他进程临时文件。
3. JSON/文本写统一使用该原语；搜索剩余直接 `write_text` 的持久状态，按风险逐一迁移，不改 fixture 生成代码。
4. `_jsonl.py` 为隔离记录生成稳定 id：`sha256(source-relative-path + line-number + raw-line)`；同一坏行重复读取只写一次 quarantine。
5. quarantine 保存截断后的 raw、原因、首次发现时间和稳定 id；raw 上限防止诊断文件膨胀。
6. 新增 `WorkspacePaths` 或等价单一解析对象，明确 `work_root`、`vault_dir`、`lock_root`、profile state。所有锁调用从这里取得 lock root。
7. 修正飞书 session 等使用默认 work root 而不是实际 vault/profile lock root 的调用；同一个 workspace 的所有写者必须落在同一 `.wb.lock`。

**测试矩阵**：

- 两个并发 atomic writer 不共用临时路径，最终文件是任一完整版本而不是拼接/半截。
- replace 失败后原文件完整，本次 temp 被清理。
- 同一坏 JSONL 行读三次，quarantine 只有一条；新增另一坏行后为两条。
- 自定义 vault 路径下，web、brief、Feishu refresh、sync 解析出同一 lock root。
- mock `fsync` 验证文件与目录耐久步骤；不依赖特定文件系统 timing。

**验收**：持久化路径与锁根只有一个权威解析入口；没有固定 `.tmp` 名称；隔离文件不会因每次 status 刷新无限重复。

### P0-07 · Workspace/Profile/Device 领域与存储

**目的**：把“用户知识库”“本机安装”“设备角色”从固定路径中显式建模。

**建议新增**：

- `domain/workspace.py`
- `config/app_support.py`
- `config/profiles.py`
- `repositories/profile_registry.py`
- `repositories/workspace_manifest.py`
- ADR `0029-workspace-profile-device.md`

**领域模型**：

- `WorkspaceManifest`：同步的 workspace 身份和兼容版本。
- `LocalProfile`：workspace id、显示名、本机 work root/vault path、provider 非秘密配置、最后打开时间。
- `DeviceIdentity`：device id、设备显示名、创建时间；安装时生成一次。
- `DeviceRole`：`automation-primary` 或 `secondary`。
- `Compatibility`：`read-write`、`read-only-upgrade-required`、`cannot-open`。

**实现要求**：

1. 使用 UUID v4；用 Pydantic 严格解析；未知字段前向兼容但不写回丢失。
2. `registry.json` 只存 profile 索引和 active workspace id；profile config 独立存放，原子写。
3. `device.json` 首次运行生成，之后稳定；从 App 升级、重新签名、移动路径都不改变 id。
4. workspace marker 存在 vault 内并进入 Git；绝不包含 device id、本机绝对路径、凭据引用以外的秘密。
5. 凭据访问 API 必须传 workspace id；旧 Keychain account 的读取只作为显式迁移兼容，不再写旧命名。
6. 环境变量只作为 development/test 覆盖，production 不再用 `WORK_ROOT` 作为正常配置源。
7. 没有 active profile 时返回明确 `onboarding-required` 状态，不再静默创建 `~/Documents/Work`。
8. 加入文件权限：本机 profile/runtime 文件建议 0600，目录建议 0700；测试兼容 umask。

**测试矩阵**：

- 首次生成 device id；重复加载不变；两个模拟 Home 得到不同 id。
- 同一 vault 在两台模拟设备读取相同 workspace id；本机 profile 路径和角色互不污染。
- 两个 workspace 的同 provider 凭据引用不会串用。
- 旧/新/未知 workspace schema 分别得到 read-write、read-only、cannot-open。
- 空安装不访问或创建 `~/Documents/Work`，而是进入 onboarding-required。

**验收**：核心业务获得路径必须经 active profile/`WorkspacePaths`；固定 home 路径只剩兼容迁移代码和测试。

**复核状态（`bf734d8`）**：`[~]`。模型、registry、Application Support 和解析器已完成；生产入口与 provider 接线当时仍待收口。

**P0-07C 收口证据（2026-09-05）**：`ActiveWorkspaceContext` 由 active profile 一次解析并冻结
paths、workspace/device id、compatibility、Application Support 与 profile config；打包
`server_entry` 与 `wb web` 在 production 禁止 `WORK_ROOT` 回退，空安装只启动 onboarding
受限控制面；WebContext、doctor/status、brief runner、Feishu/LLM 配置均消费该上下文或显式
development fallback。read-only/cannot-open 在 Web unsafe middleware 统一拒绝，profile TOML
未知字段往返保留，provider 凭据引用使用 workspace-scoped Keychain 命名。

目标测试：`tests/unit/test_active_profile_runtime.py`（6 项）以及全量现有测试；质量门为
ruff、format、mypy（241 files）、pytest（682 passed，1 skipped，跳过需
`WB_PACKAGED_APP` 的既有打包 smoke）。未执行真实 Keychain、真实 remote、clean-account
或 Apple 真机验证；这些仍属于后续 P0-09C/P0-13 门。

### P0-08 · 新建、升级与连接工作区服务

**目的**：让新同事无需终端即可得到自己的知识库，让当前使用者可把旧 vault 升级为带身份的工作区。

**建议新增**：`workflows/onboarding.py`、`domain/onboarding.py`、相关 API；本包先完成服务和 API，不做完整 UI。

**三条流程**：

1. `create-new`：选择 Work Root → 创建 `_vault` → 复制当前模板 → 写 workspace marker → 建 local profile。
2. `upgrade-existing`：选择旧 Work Root/vault → 只读预检 → 备份 → 写 marker/profile → 不移动业务数据。
3. `connect-local`：选择已经 clone 好的 vault → 校验 marker → 建 local profile；远端 clone 在 P0-10 完成。

**实现要求**：

1. 预检输出结构化报告：路径是否存在/可写、是否为空、是否为 Git repo、是否已有 marker、schema compatibility、模板冲突、空间与 Git 可用性。
2. 新建时采用 staging 目录，全部成功后原子改名到最终 `_vault`；目标非空或已存在时不覆盖。
3. 模板复制使用 allowlist；已有文件绝不覆盖。模板带当前使用者个性数据时，先拆为通用默认模板与个人内容。
4. 升级旧 vault 前创建 timestamped backup，至少包含将被修改的配置/marker；不要复制整个大 vault。
5. 失败必须回滚本次创建的 registry/profile/marker；不得删除用户原有目录。
6. 检测 iCloud Drive、Dropbox、OneDrive 等常见 CloudStorage 路径。若目标将包含 `.git`，阻止并解释；不自动迁移用户数据。
7. 新工作区默认不启用飞书、模型、Git remote 或自动化；这些是后续可跳过步骤。
8. 新工作区初始化本地 Git 只能经 P0-09 backend；backend 尚未完成前不临时调用系统 git 扩大依赖。

**测试矩阵**：

- 新建成功、目标非空拒绝、中途失败回滚、重复提交幂等。
- 旧 vault 升级后内容哈希不变，仅新增 marker/profile/backup。
- 连接 workspace A 后不会读取 workspace B 的 local config。
- CloudStorage + Git 组合被拒绝；普通本地路径通过。
- templates 中故意加入个人化 fixture 时，扫描测试失败。

**验收**：使用临时 Home 可完整创建独立 workspace，且产物中没有开发者路径、账号或 remote。

### P0-09 · 可打包 Git 后端与凭据适配

**目的**：正式 App 不依赖用户安装 Xcode Command Line Tools，同时保留开发时系统 Git 的可诊断性。

**建议方案**：先以 Dulwich 实现 HTTPS remote 的产品后端；系统 Git 保留为 development backend。若验证失败，停在决策门，不勉强上线。

**建议新增**：

- `repositories/git_backend.py`：`RepositoryBackend` Protocol 和领域结果
- `repositories/system_git.py`：迁移现有 subprocess 实现
- `repositories/dulwich_git.py`：产品实现
- `config/git_credentials.py`：Keychain 引用与 callback
- ADR `0030-packaged-git-backend.md`

**后端能力契约**：

- repo detect/init/clone
- status 与 staged/unstaged/untracked 精确列表
- add explicit paths、commit、log/filter、show diff、revert wb commit
- remote/upstream detect、fetch、ahead/behind、fast-forward、push
- current branch、commit identity、错误分类

**实现要求**：

1. 先为现有 `GitRepo` 行为建立 backend conformance tests，再迁移调用方；不能一边换库一边改变同步语义。
2. production backend 不调用 `/usr/bin/git`；测试通过 mock PATH 为空证明。
3. P0 只承诺 HTTPS private remote。PAT/credential 只从 workspace-scoped Keychain callback 读取，不写 remote URL、不写磁盘、不进异常文本。
4. clone 到 staging 目录，完成 marker/remote 校验后原子移动到最终路径。
5. 严禁 force/rebase/stash/reset；fast-forward 失败返回 typed conflict。
6. Git author 使用 profile 的显示名和用户配置邮箱；没有邮箱时 onboarding 要求输入或使用明确的本地占位，不复制开发者 identity。
7. 评估并记录：PyInstaller 收集项、arm64/x86_64 wheel、证书校验、代理、GitHub/GitLab HTTPS、仓库大小和许可证。
8. 如果 Dulwich 无法可靠满足 revert/HTTPS/证书/打包测试，输出 spike 结果并暂停：备选顺序为打包 libgit2/pygit2，其次在 App 中明确引导安装系统 Git。不得偷偷保留“clean Mac 实际不能 sync”的假完成状态。

**测试矩阵**：

- 两种 backend 对同一临时 bare remote 跑 conformance suite，结果一致。
- PATH 为空时 production backend 完成 init/commit/fetch/ff/push。
- 凭据不会出现在 remote URL、`repr`、日志、异常、fixture snapshot。
- wrong credential、TLS 失败、remote missing、non-ff 分别有 typed error。
- 打包 server smoke 能导入 backend 所需全部模块和 CA 资源。

**验收**：clean account 使用打包 App 能操作本地/HTTPS Git，不触发 CLT 安装弹窗。

**复核状态（`bf734d8`）**：`[~]`。双 backend 与本地 bare-remote conformance 已完成；workspace-scoped 凭据尚未进入 Dulwich remote transport，production backend 仍依赖环境变量选择，clone staging/marker 确认与 packaged CA smoke 尚未完成，交由 P0-09C 收口。

**P0-09C 收口证据（2026-09-05）**：`GitRepo` 支持单次调用显式注入 `system`/`dulwich`
backend，production 固定 backend helper 不读取进程环境；Dulwich clone/fetch/push 统一通过
workspace id、host、username 的 credential resolver 传递短生命周期 HTTPS Basic Auth，remote
URL 与异常保持脱敏。新增 remote onboarding staging/confirm/cancel 服务：仅 HTTPS、拒绝
userinfo，marker 缺失/不兼容/目标冲突均有稳定错误，失败只清理本次 staging，确认后 atomic
move 并创建 secondary profile。CA bundle 可发现，PATH 为空时 Dulwich 可完成本地 init/commit。

目标测试：`tests/unit/test_remote_onboarding.py`（11 项）以及既有 Git backend/credentials/
packaging 测试（28 项合计）通过；未执行真实私有 HTTPS、代理、自签证书或 clean-account 打包运行，
这些继续属于 P0-13 真机门。

### P0-10 · 多设备同步协调器与自动化主设备规则

**目的**：将当前“手动 work-sync”升级为每个 workspace 可观察、非破坏的同步状态机。

**建议新增**：

- `domain/sync.py` 中明确状态机，或扩展现有领域文件
- `workflows/sync_coordinator.py`
- `repositories/local_sync_state.py`
- sync status API 与前端 banner
- ADR `0031-multi-device-sync.md`

**状态机**：

```text
unconfigured
ready
syncing
offline-local-ahead
remote-ahead
local-ahead
diverged-protected
dirty-protected
auth-required
error
```

**实现要求**：

1. App 启动、回到前台、用户点击同步和本地写入前执行轻量 preflight；相同 workspace 的同步通过 lock 合并，不能并发 fetch/push。
2. 可联网且 remote ahead、工作树干净时只做 ff；本地 ahead 时正常 push。
3. 写操作完成 wb commit 后触发 push。push 被拒绝时保留本地提交，状态转 `diverged-protected` 或 `local-ahead`，绝不回滚用户内容。
4. 网络不可用允许本地写，记录 pending commit count 与最后成功同步时间，显示 `offline-local-ahead`。
5. 已确认 diverged 时，默认阻止会修改共享 vault 的操作；问答、浏览、导出仍可读。允许“导出本机副本”，不提供自动覆盖远端按钮。
6. dirty 需区分 wb 管理文件与用户手工改动；无法安全 ff 时进入保护态，不自动 stash。
7. `DeviceRole` 只控制定时 writer，不阻止辅助设备上的交互操作。一个 workspace 只能由用户显式选择一台 automation-primary。
8. 主设备租约以同步的轻量状态/心跳表达时，要容忍旧心跳；不得仅凭“最近在线”自动抢主。更换主设备必须显式操作并提示先停旧设备自动化。
9. UI 显示：状态、最后成功时间、本地领先数、远端领先数、当前 branch、remote host、下一步建议；不显示 token。
10. remote clone：从私有 HTTPS URL clone 到 staging，读取 workspace marker，用户确认后创建 local profile；若 remote 没有 marker，引导升级而非猜测。

**测试场景**：

- A 写并 push，B 启动后 ff；workspace id 相同、device id 不同。
- A/B 离线各写一条，先后上线后产生 diverged：两侧都不 force、不丢文件，UI 进入保护态。
- offline 写入后重启，pending 状态仍在；联网后 push 清零。
- secondary 设备运行 scheduler entry 时拒绝并记录 `not-primary`，交互 capture 仍允许。
- auth required 与网络离线分别提示，不混成普通失败。
- 同时点击同步三次只执行一个实际 fetch/push 序列。

**验收**：所有 Git 分支路径最终都落在状态机中的一个可解释状态；代码中无 force/rebase/stash/reset。

**复核状态（`bf734d8`）**：`[~]`。十态模型、基础 fetch/ff/push、API 与最小 banner 已完成；生产调用未携带 active profile/home，pending 仅是 0/1 而非真实累计，失败同步可能覆盖持久状态，写前保护与提交后 push 未统一接入所有本地 mutation，状态字段与 remote clone/主设备唯一声明不完整，交由 P0-10C 收口。

### P0-07C · Active Profile 生产运行时收口

**目的**：让 P0-07 的 profile 不再只是旁路存储，而成为 production 所有路径、兼容性和 provider 作用域的唯一运行时上下文。

**必读文件**：P0-07/P0-08 全节与实施记录、ADR 0029、`config/profiles.py`、`config/settings.py`、`repositories/profile_registry.py`、`cli/web.py`、`webapp/server_entry.py`、`webapp/app.py::WebContext`、`cli/doctor.py`、provider 配置与 secrets 模块。

**实现要求**：

1. production 入口必须调用 `resolve_workspace(allow_env_fallback=False)`；有 active profile 时只从其 `WorkspacePaths` 构建运行上下文，不能再回落到默认 `~/Documents/Work` 或普通 `WORK_ROOT`。
2. onboarding-required 时启动只含版本、onboarding 与脱敏诊断能力的受限控制面；不得先构造旧默认 vault，不得让主界面读取或创建默认目录。development/测试兼容入口必须显式声明允许 env fallback。
3. 建立单一 `ActiveWorkspaceContext`（或等价对象），至少携带 profile、workspace/device id、compatibility、paths、Application Support home；Web、doctor、sync 和 provider 只消费该上下文，不在调用点重新解析全局配置。
4. `read-only-upgrade-required` 与 `cannot-open` 在后端统一门控：前者允许浏览/导出/诊断但拒绝所有共享 vault 写，后者只展示升级提示；前端不得靠中文字符串决定权限。
5. 飞书、模型和 Git 的运行时配置/凭据引用必须以 workspace id 为作用域；旧全局凭据只允许显式迁移，不得静默回退。doctor 提取可复用领域检查，不再绑定 CLI 输出。
6. `LocalProfile` 的未知字段在读写往返中不得丢失；如果 TOML writer 不能安全保留，必须以版本迁移或明确拒绝替代静默丢字段。

**测试矩阵**：

- 两个临时 Home、两个 profile 交替启动，Web/API/doctor/provider 全部只读取当前 active workspace；旧 workspace 的路径、缓存与凭据引用不出现。
- 空安装 production 启动只进入 onboarding-required，监控证明未访问/创建模拟 `~/Documents/Work`。
- env fallback 只在显式 development/test 模式有效；production 即使设置 `WORK_ROOT` 也不采用。
- read-write/read-only/cannot-open 三态覆盖所有写中间层；只读态仍能浏览和导出。
- 带未知 profile 字段读写一次后字段仍保留，或得到稳定的版本不兼容错误。

**验收**：production 核心路径不再直接调用旧 `load_settings().work_paths()` 获取 workspace；active profile 是唯一路径与 workspace/provider 作用域来源。完成后同步更新 ADR 0029，并把 P0-07 改为 `[x]`。

### P0-09C · 私有 HTTPS Git 与 remote clone 收口

**目的**：把“Dulwich 能在临时 bare repo 工作”推进到“打包生产路径可安全使用 workspace-scoped 私有 HTTPS remote”。

**必读文件**：P0-09/P0-10 原始要求与实施记录、ADR 0030、全部 Git backend/credentials 文件、onboarding service、打包 spec/build 脚本和 packaged smoke。

**实现要求**：

1. backend 通过显式运行时依赖注入选择：packaged/production 固定 Dulwich，development 可显式选 system；不得依赖可能跨测试泄漏的进程全局环境变量决定单次业务调用。
2. 为 clone/fetch/push 建立统一 HTTPS transport/credential callback，从 `workspace_id + host + username` 读取 Keychain；密码不得进入 remote URL、磁盘、异常、日志、进程参数或持久对象 repr。
3. 新增 remote onboarding 服务：校验仅支持 `https://` 与无 userinfo URL；clone 到目标同文件系统 staging；读取 marker、检查 compatibility 与预期 workspace id；用户确认后原子移动并创建 secondary profile。失败/取消只清理本次 staging。
4. remote 无 marker 时不得创建或猜测 workspace id；返回稳定错误并提示在原设备显式升级。目标已存在、认证失败、TLS 失败、remote missing、分支异常分别返回稳定错误码。
5. 本地新工作区若启用 Git，只能通过注入的 production backend init/add/commit；作者身份来自 profile，缺省邮箱明确为 `wb@local`。
6. packaged server smoke 必须导入 Dulwich HTTP transport 与 CA 资源，并证明 PATH 为空不会调用系统 Git。真实 GitHub/GitLab/代理/证书测试仍按 §0.1-9 记录为 P0-13 真机门，不得伪造通过。

**测试矩阵**：

- fake/注入式 HTTPS transport 覆盖正确凭据、错误凭据、TLS、超时、remote missing；canary secret 不出现在 URL、日志、异常和快照。
- clone staging 成功确认、取消、marker 缺失、schema too new、目标冲突和中途异常；失败后用户目录与 registry 字节级不变。
- 两个 workspace 对同 host/user 使用不同凭据，调用记录不串用。
- packaged smoke 在 PATH 为空时完成 import、本地 init/commit，并验证 CA bundle 可发现。

**验收**：remote clone 服务与 Dulwich HTTPS 凭据链路可被 P0-11A 直接调用；production 路径不调用系统 Git。完成后同步更新 ADR 0030，并把 P0-09 改为 `[x]`；真实远端/clean-account 证据继续留在 P0-13 真机矩阵。

### P0-10C · 同步状态、写边界与主设备声明收口

**目的**：把现有同步原型接入真实 active profile 与全部本地写事务，使状态可恢复、计数可信、保护态不可绕过。

**必读文件**：P0-02/P0-10 全节与实施记录、ADR 0031、`workflows/local_mutation.py`、同步 domain/coordinator/state repo、全部 Web 写路由分类、前端 sync banner、profile/device 模型。

**实现要求**：

1. coordinator 只接受 P0-07C 的 active context/显式 backend；所有持久状态必须落到当前 profile 的 `sync-state.json`，API 不得省略 home 后退化成无持久化模式。
2. `pending_commits` 必须由实际未推送 wb commits/ahead 结果计算或可靠累计；重复离线写会递增。失败同步保留原 `last_sync_at`，只有成功完成全部目标仓库的 fetch/ff/push 才更新成功时间并清零已确认推送的 pending。
3. 启动、回到前台、手动同步和共享 vault 写入前复用同一个轻量 preflight；不得在每个端点复制判断。跨进程与同进程并发同步合并为一次实际序列，并向其余调用者返回同一结果或明确 busy/syncing 状态。
4. 在 `run_local_mutation`（或等价单一事务边界）统一接入 compatibility/sync mutation guard 与 commit 后 push；覆盖 P0-02 已列全部共享 vault 写路径，不只 `/api/capture`。外部网络调用仍不得放进 workspace 文件锁。
5. 状态快照必须填充并正确恢复 state、last success、pending、ahead、behind、branch、remote host、逐仓库状态和 next step；状态 API 只展示脱敏 host，不展示 URL userinfo/token。
6. dirty 区分 wb 管理路径与用户手工修改；只有无法安全 ff/写入时进入保护态，不自动 stash/rebase/reset。diverged/dirty/read-only 时允许浏览、问答、诊断与“导出本机副本”，拒绝所有共享 vault 修改。
7. 新增同步的主设备声明（建议 `.summit-workbench/automation-primary.json` 或 ADR 0031 选定的等价契约）：权威值为一个 device id；更换必须显式确认、比较当前 generation 并提交同步，旧心跳不得自动抢主。`LocalProfile.device_role` 不得单独宣称全局唯一。
8. banner/详情面板展示原计划第 9 项全部字段和明确下一步；提供手动重试与导出本机副本，不提供 force/覆盖远端按钮。

**测试矩阵**：

- 离线连续三次 mutation 后 pending=3，重启仍为 3；联网成功 push 后清零且保留/更新正确 last success。
- 表中所有共享 vault 写 API 在 diverged、dirty 与 read-only 下统一拒绝，问答/浏览/诊断/导出仍通过。
- 同进程三连点击与两个进程并发各只发生一次 fetch/ff/push，结果状态一致。
- A/B 双 Home 场景覆盖 ff、local ahead、remote ahead、offline、auth、TLS、dirty、diverged；所有分支落入十态之一且不丢文件。
- A 显式成为 primary，B 默认 secondary；B 未确认不能覆盖声明，显式 takeover 生成更高 generation，旧心跳不反抢。
- API/DOM 展示完整字段且 secret canary 不出现。

**验收**：原 P0-10 的 10 项实现要求和 6 个测试场景均有代码接线与证据；完成后同步更新 ADR 0031，并把 P0-10 改为 `[x]`。

### P0-11A · 可恢复首次使用向导

**目的**：不懂终端的同事可以完成自己的工作台配置；当前使用者可以通过私有 HTTPS remote 连接 Air。本包只做首次向导，已配置用户的设置中心与 profile 切换留给 P0-11B。

**必读文件**：P0-08/P0-09C/P0-10C 及其测试、前端 `main.ts` 与 `lifecycle/*`、Web onboarding API、模板目录、provider 配置/凭据服务。只允许新增边界清晰的 `web/src/onboarding/*`，不得借机实施 P1-04 全前端重构。

**页面流程**：

1. 欢迎页：`新建我的工作台` / `连接已有工作台` / `升级这台 Mac 上的旧工作台`。
2. 名称与本机目录：显示默认建议，但允许选择；解释哪些内容会同步。
3. Git：本地使用 / 连接私有 HTTPS remote；可跳过。
4. 模型：provider、endpoint、model、Keychain key；提供“测试连接”，可跳过。
5. 飞书：app id、最小 scope、登录；可跳过。
6. 设备角色：主设备或辅助设备；连接已有 workspace 时默认辅助。
7. 最终检查：路径、workspace id 短码、device id 短码、同步、凭据、自动化状态。

**实现要求**：

1. 向导是可恢复状态机；每一步保存非秘密进度，关闭 App 后从安全步骤继续。
2. 非秘密草稿持久化在本机 Application Support 的 installation-level onboarding draft 中，原子写且 mode 0600；没有 workspace 前不得伪造 workspace id。完成或显式取消后清理草稿。
3. UI 不直接写文件/Keychain；只调用 onboarding/provider service API。secret 只在用户提交当前步骤时进入一次请求，由后端立即写入 workspace-scoped Keychain。
4. 每一步支持后退；对已创建的远端/Keychain 外部状态不假装可回滚，需解释并显示精确的本机清理范围。
5. 所有 secret 输入默认遮挡，不回显，不保存到前端 store、sessionStorage/localStorage、onboarding draft、日志、错误详情或网络调试快照。
6. 空安装只渲染向导；已配置用户启动直接进入主界面。连接 remote 必须调用 P0-09C 的 staging/confirm 服务，不能在前端拼 Git 操作。
7. 模型“测试连接”和飞书登录都是显式可跳过步骤；测试结果只持久化非敏感状态。跳过全部 provider/Git 后仍能完成本地 capture。
8. 连接已有 workspace 时默认 secondary；选择 automation-primary 必须调用 P0-10C 的显式主设备声明流程并展示接管影响。
9. 最终检查必须来自后端 active context/doctor/sync 领域结果，显示路径、workspace/device 短码、兼容性、同步、凭据是否就绪和自动化角色；不由前端重复推导规则。
10. 所有文案避免暴露技术细节，但错误详情允许复制脱敏诊断；稳定错误码驱动页面状态。

**测试矩阵**：

- 空安装完整新建流程；跳过 Git/Feishu/model 后仍可本地 capture。
- 关闭重开后继续向导。
- 新建、升级本地旧 vault、remote clone 三条人物旅程；连接已有 workspace 默认 secondary。
- secret canary 不出现在 DOM 持久化、Application Support 草稿、日志、错误和网络快照。
- 引入最小 Playwright 浏览器门，覆盖成功、后退/恢复、路径冲突、remote auth、marker 缺失、schema too new；不以只测 TypeScript helper 代替真实页面旅程。
- 向导重复提交、关闭重开与后端成功但前端丢响应均保持幂等，不重复创建 workspace/profile/Keychain 状态。

**验收**：在临时 Home、无终端操作的条件下完成两种核心人物旅程：同事新建独立 workspace 并 capture；Air 从私有 HTTPS remote 连接现有 workspace 并默认为 secondary。P0-11 总包仍保持未完成，直至 P0-11B 通过。

### P0-12 · 动态端口、会话认证与原生生命周期

**目的**：消除固定 8787 端口冲突，并确保只有当前 App 实例能调用本地写 API。

**必读文件**：`native/SummitWorkbench/*`、`webapp/server_entry.py`、`cli/web.py`、前端 `lifecycle/*`、native contract tests。

**实现要求**：

1. production 不再从 build manifest 固定端口。Python 先绑定 `127.0.0.1:0` 获得 OS 分配端口，再把已绑定 socket 交给 Uvicorn，避免“先找空闲端口再启动”的竞态。
2. 服务启动后原子写 runtime record：schema、pid、port、server instance、workspace id、device id、started_at；文件 mode 0600，位于 active profile runtime 目录。
3. 原生壳启动时生成 256-bit 随机会话 token，使用进程环境传给子服务，不放命令参数、不写普通日志。
4. API 接受 HttpOnly、SameSite=Strict session cookie 或受控 header；所有 unsafe route 必须认证，敏感 read route 也认证。
5. 原生壳通过 `WKHTTPCookieStore` 在导航前写 cookie；不要把 token 注入 JavaScript、URL query 或 localStorage。
6. `wb web` development 入口若仍支持普通浏览器，生成一次性 bootstrap URL，交换 HttpOnly cookie 后立即 redirect 清除 query；控制台只显示一次并明确仅限本机。
7. native probe 同时校验 product id、api protocol、frontend build、server instance、workspace id 和 session；不能误连接同端口的旧实例。
8. profile 切换或 App 退出时优雅停止子进程，等待有限时间后再 terminate；只操作自己记录的 pid/server instance。
9. runtime record 过期或 pid 不存在时安全清理；不得杀掉仅凭端口匹配的其他进程。
10. build manifest 保留产品/前端/API 兼容信息，删除运行端口职责并升级 schema。

**测试矩阵**：

- 8787 被占用时 App 正常启动到另一端口。
- 无 cookie、错误 cookie、跨 workspace cookie 请求均被拒绝；合法 WKWebView 会话通过。
- token 不出现在 `ps` 参数、runtime record、结构化日志、API version payload。
- 两个开发实例并行启动各自连接正确服务，不互相 terminate。
- crash 后 stale runtime record 被清理，正常实例记录不被误删。
- native/server/frontend build 不兼容时显示可恢复错误，不无限重连。

**验收**：production 包不再依赖固定端口；任意写 API 都要求当前实例会话。

### P0-11B · 设置中心与安全 profile 切换

**目的**：在 P0-12 已具备受控子服务生命周期后，为已配置用户提供多 profile 管理、provider 设置、doctor 与不会串 workspace 的切换流程。

**必读文件**：P0-07C/P0-10C/P0-11A/P0-12 全节与测试、profile registry、active context、provider 配置/凭据服务、doctor 领域检查、前端 drafts/connection/native bridge、原生进程管理。

**实现要求**：

1. 设置中心列出 profile 显示名、workspace 短码、本机路径、兼容性、设备角色、同步摘要和 provider 就绪状态；一次只允许一个 active profile。
2. 切换使用后端 prepare/commit 协议：先验证目标 profile 与 compatibility，阻止新 mutation，等待在途 mutation 有界结束，原生壳停止旧子服务，再以目标 profile 启动并完成 workspace/session 握手；任一步失败回到旧 profile 或显示明确可恢复错误。
3. 前端缓存、草稿、轮询和请求必须按 workspace id 作用域。切换时清除旧作用域的内存状态与无命名空间的旧草稿；任何旧响应到达后不得写入新 workspace 页面。
4. 模型、飞书与 Git 设置只调用后端服务；secret 更新同 P0-11A，一次请求后进入 workspace-scoped Keychain，不回显。切换后不得读取前一个 profile 的凭据引用。
5. GUI doctor 复用 P0-07C 提取的领域检查，默认离线、无副作用；在线检查必须由用户显式触发并说明可能发生的 token 轮换/网络访问。
6. “移除此 Mac 上的工作台”默认只删除选中的 local profile/runtime/draft，不删除 vault、不改 remote、不删 Keychain；执行前列出精确目标。删除 vault、远端或凭据不纳入默认操作，危险清理必须另行显式确认与测试。
7. 修改 automation-primary 必须走 P0-10C 的显式声明/takeover，不得只改本机 `LocalProfile.device_role`。
8. 使用稳定错误码和脱敏诊断；UI 不显示完整 workspace/device id、secret、带 userinfo 的 remote 或其它 profile 的绝对路径。

**测试矩阵**：

- profile A/B 往返切换后，API workspace id、页面数据、session token、draft、轮询、Keychain 引用完全隔离；模拟 A 的迟到响应不能污染 B。
- 切换时存在 mutation、目标 schema too new、子服务启动失败、握手失败和旧服务退出超时，均得到确定状态且不同时运行两个 writer。
- 移除非 active/active profile 的默认操作只影响本机允许列表；vault、remote、Keychain 字节级/调用级不变。
- doctor 离线检查无网络/写入；显式在线检查走 fake/MockTransport 且 secret 不泄漏。
- Playwright + native contract 覆盖设置查看、切换、失败回滚、移除与重新连接。

**验收**：两个 profile 连续切换与重启不发生跨 workspace 展示或写入；默认移除操作不删除用户数据。通过后将 P0-11A/P0-11B 均标 `[x]`，P0-11 总目标才视为完成。

### P0-13 · Apple Silicon 内部 DMG 分发

**目的**：生成仅供 M2+ Apple Silicon 内部/个人自用的可安装 macOS 包；不支持 Intel、Windows、
Apple Developer ID 或 App Store 发布。

**建议新增/修改**：

- `packaging/entitlements.plist`
- `packaging/dmg-background`（若需要）
- `scripts/release-macos.sh`
- `scripts/verify-macos-release.sh`
- `docs/RELEASING.md`
- ADR `0032-macos-distribution.md`
- 重构 `scripts/build-macos-app.sh`

**实现要求**：

1. `pyproject.toml` 为唯一 `CFBundleShortVersionString` 来源；build number 由 CI run 或显式参数提供，不再使用当天日期和 epoch 作为产品版本。
2. 只构建并验证 `arm64`，目标为 Apple Silicon M2 及以上；不得生成、宣传或伪装 Intel/universal 包。
3. build 在临时目录完成并先 smoke，成功后才移动产物；沿用当前原子替换策略。
4. 对 bundle 内嵌 dylib、framework、PyInstaller executable 按由内到外顺序 ad-hoc 签名，供内部机器完整性校验。
5. 不要求 Developer ID、hardened runtime、timestamp 或 notarization；保留最小 entitlement，不添加 library validation 绕过权限。
6. 创建 DMG，包含 App 与 `/Applications` 引导；内部包不提交 Apple notarization、不 staple。
7. 验证至少包括：`codesign --verify --strict`、arm64 架构、bundle 文件清单、无开发路径/secret 扫描、离线启动 smoke。
8. 发布脚本不得要求 Apple 证书、Keychain 签名 profile 或真实网络凭据。
9. 生成 checksum、架构、最低 macOS、version、build、Git commit、workspace schema range 和 SBOM/依赖清单。
10. 文件名、UI 和 manifest 标明 `INTERNAL-DEV`；包只允许内部/个人自用，不标为公开 release。

**真机矩阵**：

- Apple Silicon：当前 Mac Studio、MacBook Air 的实际 macOS 版本。
- M2+ Apple Silicon：至少当前 Mac Studio 和 MacBook Air 各完成一次实际安装/启动验证。
- 干净用户账户：未装 Python/Node/uv，使用 M2+ Mac 的真实用户账户验证。
- 升级安装：保留 profile/vault/Keychain，替换 App 后正常启动。
- 删除 App：用户数据仍保留；卸载文档明确如何另行删除本机数据。

**验收**：P0 内部发布门全部通过，形成带 checksum 的 arm64 `INTERNAL-DEV` DMG；M2+ 用户按一页图形化说明完成安装与新建 workspace。

## 5. P1 工作包：长期运行、维护与扩展性

### P1-01 · App 内定时任务与自动化主设备

**目的**：不依赖 `wb` CLI 和 `install-launchd.sh`，在 App 设置中管理晨间简报、周报与会议同步。

**实现要求**：

1. 使用 Apple Service Management 的现代注册方式（`SMAppService`）管理嵌入 App、同证书签名的 helper/agent；不要让 GUI 临时写任意 plist 到用户目录。
2. 新增自包含 worker executable，打包必要 CLI/workflow，但不启动 Web server。
3. helper 通过 profile/workspace id 查本机配置，不依赖 shell 环境、当前目录或 `PATH`。
4. 运行前检查当前 device role；secondary 返回成功跳过状态 `not-primary`，绝不生成重复简报。
5. UI 可启用/停用、查看下一次/上一次结果、手动运行和复制错误摘要。
6. App 升级后重新核对 helper 版本与签名；旧 helper 不得继续调用不兼容 workspace schema。
7. 保留旧 launchd 脚本仅作开发/迁移，文档标为非产品路径。

**测试/验收**：worker 在空 PATH 可执行；注册/取消不残留；主设备运行一次、辅助设备零写入；睡眠唤醒补跑仍幂等；签名包内 helper 通过验证。

### P1-02 · 工作区 schema 迁移、备份与回滚

**目的**：Studio 与 Air 版本不一致时也不破坏共享 vault。

**实现要求**：

1. 建立 migration registry：每个迁移只有 `from_version -> to_version`，可重复检查但只执行一次。
2. 写迁移前要求同步状态 ready、当前设备为用户确认的迁移设备、工作树干净、remote 可达。
3. 在本机 backups 生成 manifest + 被修改文件快照；记录 checksum、App version、workspace id、Git HEAD。
4. 迁移全部在 workspace lock 下使用原子写；失败恢复备份，并留下失败报告。
5. 成功后单独生成 `wb: migrate workspace vN -> vN+1` 提交并 push；其他设备看到 `min_writer_version` 后自动只读并提示升级。
6. 至少保留前一个正式版本的 reader compatibility；不能兼容时必须通过 marker 明确拒绝。

**测试/验收**：旧版本 fixture 升级、重复迁移、半途异常回滚、两设备版本错位、remote 不可达、dirty tree、schema 太新全部有测试。

### P1-03 · 后端路由与应用服务拆分

**目的**：降低 `webapp/app.py` 的变更半径，为 onboarding、sync、settings、diagnostics 持续扩展。

**目标结构**：

```text
webapp/
├── app_factory.py
├── dependencies.py
├── errors.py
├── middleware/
├── routers/
│   ├── system.py
│   ├── workspace.py
│   ├── projects.py
│   ├── threads.py
│   ├── review.py
│   ├── feishu.py
│   ├── sync.py
│   └── onboarding.py
└── services/
```

**实现要求**：

1. 先生成现有 route contract snapshot：method、path、request、response status/error code。
2. 只移动代码和注入依赖，不在同包改变业务行为、路由或前端样式。
3. `create_app` 接收显式 `AppContext`；消除 route 内重复加载 settings/client 的隐式全局。
4. 每个 router 只负责编解码和调用 workflow/service；不得继续增长业务逻辑。
5. 单文件建议上限 400 行；超限需说明而非机械拆成无意义 helper。

**验收**：route contract snapshot 不变；全量测试通过；`webapp/app.py` 只保留兼容导出或小型 app factory。

### P1-04 · 前端 feature 拆分与状态管理

**目的**：降低 `web/src/main.ts` 的耦合，防止 profile 切换和同步状态加入后出现跨页面脏状态。

**目标结构**：

```text
web/src/
├── api/
├── core/
├── features/onboarding/
├── features/workspace/
├── features/projects/
├── features/threads/
├── features/review/
├── features/sync/
├── features/settings/
└── lifecycle/
```

**实现要求**：

1. 先拆 typed API client、error normalization、active workspace store，再按 feature 移动 UI。
2. 所有 cache/draft key 必须包含 workspace id；profile 切换统一 dispose subscriptions 与 abort requests。
3. 禁止引入大型框架只为拆文件；若继续 vanilla TypeScript，使用小型明确模块和 typed events。
4. 保持 DOM/样式/键盘行为，先做等价重构；每次只迁移一个 feature。
5. 为 onboarding、sync banner、review apply、profile switch 添加浏览器级测试。

**验收**：`main.ts` 仅作 composition root；无循环依赖；profile A 的草稿与响应不会出现在 profile B。

### P1-05 · 诊断包、日志、隐私与可支持性

**目的**：同事出问题时可提供足够证据，但不泄露工作内容和凭据。

**实现要求**：

1. Python/Swift 统一结构化日志字段：timestamp、level、component、operation id、workspace id 短码、device id 短码、error code。
2. 日志滚动与容量上限；默认不记录正文、prompt、模型回复、Authorization、cookie、remote credential URL。
3. 建立中央 redactor，并用秘密 canary 测试所有诊断出口。
4. “导出诊断包”只包含：版本/架构、schema、状态摘要、最近脱敏错误、签名信息、同步计数、配置键名；文件清单需用户预览。
5. crash report 默认本地；任何远程 telemetry 必须以后单独 opt-in，不在本包暗中添加。
6. UI 提供复制诊断摘要与打开日志目录；失败不要求用户运行命令。

**验收**：带 canary token/会议正文的模拟运行后，导出包全文扫描为零命中；诊断足以区分 auth、offline、schema、server crash、sync divergence。

### P1-06 · CI、覆盖率门与发布矩阵

**目的**：把当前本地可运行的质量门变成每次变更和每次发布都可复现的自动门禁。

**实现要求**：

1. PR CI：Python lint/format/mypy/pytest；Node install/build/verify；secret scan；依赖锁一致性。
2. 初始覆盖率门设为不低于 80%，并生成模块报告；后续以当前基线逐步上调，禁止因新增代码静默下降。
3. macOS build CI 按 arm64/x86_64 分开，产物 metadata 必须与 runner 架构一致。
4. release workflow 只允许 tag 与 pyproject version 一致时签名；签名 secrets 仅在受保护环境可用。
5. release 产出 DMG、checksum、SBOM、notary log 摘要、测试清单；任何一步失败不发布 partial latest。
6. packaged integration tests 不再仅靠可选环境变量静默跳过；release job 必须执行并上传结果。

**验收**：故意破坏 Python、前端 build、coverage、架构标记和签名各一次，CI 都能在对应门失败。

### P1-07 · 签名自动更新

**目的**：让 Studio、Air 和同事可靠升级，而不是手工反复传 DMG。

**建议**：采用 Sparkle 2；更新 feed 与包都使用独立 EdDSA 签名，仍保留 Apple code signing/notarization。

**实现要求**：

1. 先完成手工“检查更新”；自动后台检查默认开启，但自动下载安装策略尊重用户设置。
2. feed 按架构/最低系统版本发布兼容 enclosure；绝不把 x86_64 包发给 arm64 原生通道或反之。
3. 更新前检查 workspace migration compatibility；App 更新失败不得触碰 vault。
4. 支持跳过版本、稍后提醒和显示 release notes；同一 workspace 两台设备允许短期不同 App 版本并受 schema gate 保护。
5. 验证从上一正式版升级、签名被篡改拒绝、下载中断、磁盘不足、回滚启动。

**验收**：已 notarized 的 N-1 版本可通过签名 feed 更新到 N，用户数据和 profile 完整；恶意/损坏包被拒绝。

## 6. P2 工作包：降低跨设备冲突与可选团队服务

### P2-01 · 追加式操作事件与确定性投影视图

**目的**：将最容易发生 Git 冲突的共享热点文件，从“整页 RMW”演进为“每次操作一个不可变事件文件”。

**首批候选**：全局 inbox、meeting review decisions、daily signal/completion events、线程 activity；会议原文和项目档案暂不迁移。

**建议布局**：

```text
_vault/_events/<device_id>/<yyyy>/<mm>/<ulid>.json
_vault/_views/...                         # 可重建投影
```

**实现要求**：

1. 事件含 schema、event id、workspace/device id、occurred_at、kind、aggregate id、payload、causation operation id。
2. 使用单调 ULID 或等价 sortable id；两个设备离线生成不得重名。
3. 事件不可修改/删除；更正通过 compensating event。投影按稳定排序和幂等 event id 重建。
4. views 是派生物；损坏或冲突时可从 events 重建并校验 checksum。
5. 采用 `shadow-read -> dual-write -> event-primary -> stop-legacy-write` 四阶段迁移，每阶段可回退并有一致性报告。
6. 不把 Git commit 当业务事件；Git 只负责传输与历史，业务操作有自己的 operation/event id。
7. 先对一个低风险 aggregate 做纵向切片，不一次迁移全部 Markdown。

**测试/验收**：属性测试覆盖乱序、重复、时钟相同、离线双设备、投影中途失败；两设备 event 文件 Git merge 无同路径冲突；投影视图与旧格式结果等价。

### P2-02 · 同步冲突解释与恢复工作台

**目的**：当 Git 真的分叉时，给非技术用户一个安全、可解释、可导出的恢复流程。

**实现要求**：

1. 冲突页区分：仅追加事件可自动集合并、生成视图可重建、人工 Markdown 需选择、二进制不可合并。
2. 所有自动合并先在临时 clone/worktree 进行，验证 schema/投影/test 后才替换当前分支；不得直接在用户工作树试错。
3. 提供“导出本机更改包”“复制诊断”“稍后处理”；不提供 force push 快捷按钮。
4. 人工选择前展示双方时间、设备、操作 id 和结构化差异，不只展示原始 Git 冲突标记。
5. 恢复完成生成审计事件和普通 push；远端仍变化时重新进入保护态。

**验收**：构造事件/Markdown/二进制三类分叉，自动项不丢事件，人工项无确认不写，恢复后两设备能 ff 到同一 HEAD。

### P2-03 · 组织级 OAuth Broker（可选，不默认实施）

**目的**：若未来不希望每位同事自行创建飞书应用，可建设组织托管的 OAuth 回调与 token 服务。

**开始条件**：产品所有者明确接受新增云服务、隐私责任、运维成本和组织管理员审批；否则保持本地 BYOK。

**最小职责**：OAuth state/PKCE、回调、token 加密存储/轮换、用户与 workspace 绑定、撤销、审计、速率限制、区域与保留策略。模型 API key 托管不自动包含在此范围。

**禁止事项**：不得把共享 app secret 打进桌面 App；不得让一个同事读到另一人的 token；不得以“方便”之名上传 vault 或会议正文。

**验收**：威胁模型、数据处理说明、删除/撤销流程、密钥轮换、越权测试和服务不可用时的桌面降级全部完成后才可试点。

## 7. 跨工作包的契约与禁止事项

### 7.1 稳定错误码

至少保留以下机器码，具体文字可本地化：

- `onboarding_required`
- `workspace_not_found`
- `workspace_schema_too_new`
- `workspace_read_only_upgrade_required`
- `session_required`
- `origin_rejected`
- `input_too_large`
- `workspace_busy`
- `git_index_not_clean`
- `sync_offline`
- `sync_diverged`
- `sync_auth_required`
- `external_action_unknown`
- `not_automation_primary`

前端不得通过匹配中文 message 决定状态。

### 7.2 隐私清单

以下内容不得出现在 Git、App bundle、日志、诊断包、崩溃报告、前端持久缓存或测试 fixture：

- 飞书 user access token、refresh token、app secret；
- 模型 API key；
- Git PAT/密码；
- session token、cookie；
- 完整 Authorization header；
- 未脱敏的会议正文、模型 prompt/response；
- 当前使用者或同事的真实 Home 绝对路径；
- 私有 remote 中嵌入的 credential。

### 7.3 不允许 Luna 自行做出的架构变更

- 不引入中央数据库、向量库、远程后端或多租户服务。
- 不把 Git 替换成网盘文件同步。
- 不把自动化设成所有设备默认开启。
- 不在分叉时自动选择一侧覆盖另一侧。
- 不因重构改变 Markdown 稳定格式、PRD 审批边界或“飞书是远端事实源”的现有规则。
- 不关闭 TLS 验证、Gatekeeper、hardened runtime 或代码签名检查。
- 不把 secret 从 Keychain 迁到普通配置文件。
- 不用 `--deep` 代替由内到外的正式签名流程。
- 不为了通过测试删除/放宽原有测试、mypy strict 或错误可见性。

## 8. 测试分层与最小矩阵

### 8.1 单元测试

- 领域状态机、schema compatibility、profile 隔离、retry mode、outbox 幂等、sync transition。
- 路径与 lock root 必须使用临时 Home；不能依赖当前开发机目录。
- 所有网络用 fake/MockTransport；所有 Keychain 用 protocol fake。

### 8.2 集成测试

- 临时 bare Git remote + 两个 clone 模拟 Studio/Air。
- 两个独立 Home 模拟使用者/同事，验证任何配置、凭据引用、缓存不交叉。
- 启动真实 bundled server，验证动态端口、cookie、runtime record、shutdown。
- 中断点测试：atomic replace、outbox prepared、push reject、onboarding staging、migration rollback。

### 8.3 App 黑盒测试

- 空账号首次启动、新建 workspace、capture、退出、重启。
- 连接 remote、断网、恢复、分叉保护。
- profile 切换和旧版本 workspace 只读。
- DMG 安装、Gatekeeper、签名、卸载后数据保留。

### 8.4 真机验收脚本必须记录

- 设备型号、芯片、macOS 版本；
- App version/build/checksum；
- workspace id 只记录短码，不记录路径和 secret；
- 每一步预期/实际/截图或日志 operation id；
- 回滚办法；
- 未通过项不得写成“基本可用”。

## 9. 两条最终用户验收旅程

### 9.1 你的 Mac Studio + Air

1. Studio 升级旧 vault，生成 workspace marker，保持所有原内容和 Git 历史。
2. Studio 设置为 automation-primary，完成一次同步并 push。
3. Air 安装同一正式 App，选择“连接已有工作台”，通过私有 HTTPS remote clone。
4. Air 读取相同 workspace id，生成不同 device id，默认 secondary。
5. Studio 写一条 capture 并同步；Air 前台刷新后看到。
6. Air 断网写一条 capture，看到待同步计数；联网后 push，Studio ff 后看到。
7. 构造两端离线同时修改同一旧热点文件，确认双方进入保护态且无 force/丢失。
8. 两台 Mac 同时跨过 08:00，只有 Studio 生成简报；Air 显示由主设备负责。

### 9.2 同事的独立工作台

1. 在干净账户下载 DMG，校验 checksum，拖入 Applications，首次启动通过 Gatekeeper。
2. 点击“新建我的工作台”，选择自己的本地目录和名称。
3. 跳过 Git、飞书和模型，先完成本地 capture、项目建档和重启恢复。
4. 逐项配置自己的模型 key、飞书授权、私有 remote；所有 secret 只进她的 Keychain。
5. 启用自己的自动化主设备；查看一次手动运行结果。
6. 导出诊断包，确认没有正文和 token。
7. 检查她的 workspace、App Support、Keychain 和 Git remote 中完全不存在当前使用者的数据。

## 10. 发布与回滚策略

### 10.1 版本建议

- `0.5.0-alpha.*`：完成 P0-07C/P0-09C/P0-10C 后，仅开发者双设备测试。
- `0.5.0-beta.*`：完成 P0-11A、P0-12、P0-11B、P0-13 后，邀请同事 clean-account 试用。
- `0.5.0`：P0 发布门通过。
- `0.6.0`：P1 自动化、迁移、诊断、CI、更新完成。
- `0.7.0` 或更高：P2 event store；因持久化模型变化，不混入普通 patch。

### 10.2 回滚原则

- App 二进制回滚与 workspace schema 回滚分离；旧 App 不兼容时只读，不能强开。
- 每次 migration 前有本机备份和 Git HEAD；回滚不使用 `reset --hard` 操作用户仓库。
- 外部飞书动作不能随 vault rollback 自动撤销；outbox 与 UI 必须持续显示真实远端状态。
- 自动更新失败只回滚 App，不删除 profile、Keychain 或 vault。
- 分发错误可撤下 feed/DMG，但已安装设备仍能离线读取兼容 workspace。

## 11. 风险登记

| 风险 | 早期信号 | 缓解 | 决策门 |
|---|---|---|---|
| Dulwich 与现有 Git 语义不完全一致 | conformance/revert/TLS 失败 | P0-09C time-box；改用 libgit2 或明确系统 Git 前置 | P0-09C |
| 两台 Mac 离线修改旧 RMW 热点 | non-ff push | P0 保护态；P2 event store 根治 | P0-10/P2-01 |
| 飞书日历无可靠幂等键 | timeout 后无法判断 | unknown 状态 + 核对，禁止自动重试 | P0-04 |
| PyInstaller universal2 依赖不全 | lipo/启动验证失败 | 首发按架构分别发布 | P0-13 |
| Keychain 迁移串 workspace | 相同 app id 读到旧 token | workspace-scoped service + 显式一次性迁移 | P0-07C/P0-11B |
| helper 签名或路径在升级后失效 | 定时任务不再运行 | SMAppService 状态 UI + 版本握手 | P1-01 |
| 大文件/日志撑满磁盘 | App 变慢、写失败 | 输入上限、日志轮换、容量诊断 | P0-05/P1-05 |
| schema 在双设备版本错位时被旧版写坏 | Air 旧版仍能写 | min reader/writer gate，先升级再写 | P0-07C/P1-02 |
| profile 切换时旧请求污染新工作区 | 切换后出现旧数据或写错 vault | P0-12 受控重启 + P0-11B workspace 作用域缓存/请求代际 | P0-11B |
| Luna 跨包重构造成回归 | diff 过大、验收不聚焦 | 一任务一包、测试先行、明确停止条件 | 全程 |

## 12. ADR 交付要求

以下 ADR 随对应代码包创建并加入 `docs/decisions/README.md`：

| ADR | 工作包 | 必须回答 |
|---|---|---|
| 0028 | P0-04 | 哪些飞书动作可重试；unknown 如何核对；如何避免重复 |
| 0029 | P0-07 | workspace/profile/device 边界；同步与本机数据分别是什么 |
| 0030 | P0-09 | Git backend 选择、HTTPS 凭据、打包/许可证/架构证据 |
| 0031 | P0-10 | 同步状态机、离线策略、主设备、分叉保护 |
| 0032 | P0-13 | arm64 内部产物、ad-hoc 签名顺序、版本与发布验证；明确不需要 notarization |
| 0033 | P1-01 | helper/SMAppService 生命周期、权限、升级兼容 |
| 0034 | P1-02 | 工作区 schema 迁移、备份与安全回滚 |
| 0035 | P1-03 | Web route contract、显式 AppContext 与兼容拆分边界 |

ADR 必须记录最终实现与验证证据，不得只复制本计划。

P0-07C/P0-09C/P0-10C 不新建平行 ADR；分别修订 0029/0030/0031，加入最终生产接线、被否决方案与新增验证证据。旧 ADR 的“已实现”摘要若与复核结论冲突，必须同步改为“部分完成”，直至对应收口包通过。

## 13. Luna 单包交付模板

每完成一个工作包，在回复中使用以下结构：

```text
工作包：P0-XX · 名称
结果：完成 / 部分完成 / 阻塞

完成范围：
- ...

用户可见变化：
- ...

主要文件：
- path: 变化

验证：
- 命令：结果
- 新增测试：数量与覆盖场景

原始验收逐项对照：
- 要求/测试 N：完成（文件/测试证据）或未完成（原因）

未验证/阻塞：
- ...

计划状态：
- 是否已勾选本工作包
- 下一工作包（只说明，不实施）
```

若任何全量门失败，或原始实现要求/测试矩阵存在未完成项，不得写“完成”；要区分本次引入失败、基线已有失败与真机待验，并提供证据。只有真机门因 §0.1-9 的外部条件无法执行时，才可在离线实现完成后单独记录“实现完成、真机未验证”。

## 14. 推荐执行节奏

为减少 Luna 长上下文漂移，建议每个新窗口只交付一个工作包：

1. 第一轮：P0-01、P0-02，封住本地数据与 undo 边界。
2. 第二轮：P0-03、P0-04，封住飞书重复副作用。
3. 第三轮：P0-05、P0-06，统一 Web/文件基础设施。
4. 第四轮：P0-07、P0-08，建立用户、工作区和设备模型。
5. 第五轮（历史）：P0-09、P0-10 已建立基础实现，但经 `bf734d8` 复核仍为 `[~]`。
6. 第六轮：P0-07C，只收口 active profile production 上下文；完成后单独提交、验收、更新 ADR 0029。
7. 第七轮：P0-09C，只收口 Dulwich HTTPS 凭据与 remote clone；完成后单独提交、验收、更新 ADR 0030。
8. 第八轮：P0-10C，只收口同步持久状态、全写边界和主设备声明；完成后进行开发者双设备 alpha 验收并更新 ADR 0031。
9. 第九轮：P0-11A，完成可恢复首次向导；不得同时实现设置中心。
10. 第十轮：P0-12，完成动态端口、会话认证和受控原生服务生命周期。
11. 第十一轮：P0-11B，基于 P0-12 完成设置中心与安全 profile 切换。
12. 第十二轮：P0-13，签名分发与同事 clean-account 试点。
13. P0 真实使用一至两周后，再进入 P1；不要在试点前建设 P2 event store。

每轮两个工作包也应分别开任务、分别验收；这里的“轮”只表示同一主题，不表示一次提交。

## 15. 实施记录

完成工作包后按以下格式追加，不覆盖历史：

```text
### YYYY-MM-DD · P0-XX

- 状态：完成
- Git commit：<sha 或“未提交”>
- 变更摘要：...
- 目标测试：...
- 全量质量门：...
- 真机验证：通过 / 未执行（原因）
- 遗留：...
```

### 2026-09-05 · P0-01

- 状态：完成
- Git commit：4269f36（已推送至 `origin/main`）
- 变更摘要：GitRepo 新增暂存路径、提交主题、父节点数和 commit 对象校验；自动提交拒绝调用前已有 staged path，主题规范化为单行 `wb:`，只检查本次目标路径；撤销与 diff 仅接受完整 40 位十六进制的 `wb:` 单父提交，并在同一工作区锁内完成撤销前读取、脏检查和执行；undo Web API 拒绝路径返回 4xx 与稳定错误码。
- 目标测试：`uv run pytest tests/unit/test_autocommit.py tests/unit/test_webapi_undo.py`（20 passed）
- 全量质量门：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy` 通过；`uv run pytest`（528 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（本工作包使用临时 Git 仓库离线验证，无 Apple Developer 证书、第二台 Mac 或真实远端门）
- 遗留：无；P0-02 及后续工作包未开始。

### 2026-09-05 · P0-02

- 状态：完成
- Git commit：db00659（已推送至 `origin/main`）
- 变更摘要：新增本地 mutation 单一编排器，在工作区锁内串行完成本地写入、路径收集与 `wb: <action> [<operation_id>]` 自动提交；迁移 capture、线程日志/产物/状态、项目创建/激活/归档/改名、任务/会议本地镜像，以及会议导入的原文归档、结构化收尾和审批页刷新阶段；网络、LLM 与飞书调用均位于锁外；API 返回 operation id、操作列表及可见 Git 提交状态。
- 目标测试：`uv run pytest tests/unit/test_local_mutation.py tests/unit/test_backfill_workflow.py tests/unit/test_process_archived_workflow.py tests/unit/test_webapi.py`（56 passed）
- 全量质量门：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy` 通过；`uv run pytest`（535 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（本工作包使用临时目录/临时 Git 仓库和 fake/MockTransport 离线验证，无真实飞书、模型、Keychain、工作目录或第二台 Mac）
- 遗留：无；P0-03 及后续工作包未开始。

### 2026-09-05 · P0-03

- 状态：完成
- Git commit：a9bee3f（已推送至 `origin/main`）
- 变更摘要：引入显式 `RetryMode`（`safe`、`idempotency-key`、`never`）；GET 明确使用 safe，任务创建携带稳定 `client_token` 后才允许幂等重试，普通 POST、日历创建、PATCH/DELETE 与 token POST 均禁止自动重放；网络/超时错误保留 `retryable`、`retry_after`、`result_unknown` 机器字段；`FeishuClient` 支持 close/context manager，并由 FastAPI lifespan 复用和确定性释放用户态客户端。
- 目标测试：`uv run pytest tests/contract/test_feishu_client.py tests/contract/test_feishu_tasks.py tests/contract/test_feishu_calendar.py tests/contract/test_feishu_meetings_list.py tests/unit/test_feishu_session.py tests/unit/test_feishu_lifecycle.py tests/unit/test_resilient.py tests/unit/test_webapi.py tests/unit/test_webapp.py`（98 passed）
- 全量质量门：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy` 通过；`uv run pytest`（542 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（本工作包使用 MockTransport/fake 客户端离线验证，未访问真实飞书或真实凭据）
- 遗留：无；P0-04 及后续工作包未开始。

### 2026-09-05 · P0-04

- 状态：完成
- Git commit：0d874bb（已推送至 `origin/main`）
- 变更摘要：新增 schema-versioned 外部动作 outbox 与状态机（prepared/sending/succeeded/failed/unknown/reconciled）；apply 先落 prepared、再落 sending，成功记录 remote id，FeishuError/验证/IO 错误按 action 隔离；unknown 与未二次确认的核对未找到状态禁止自动重试；任务/会议写回贯通 operation id 与最小 WB marker；新增外部动作查询/人工核对/二次确认重试 API 和审批页状态组件；坏行沿用 quarantine，workspace id 与候选指纹隔离；新增 ADR 0028。
- 目标测试：`uv run pytest tests/unit/test_external_action_outbox.py tests/unit/test_external_actions.py tests/unit/test_review_apply.py tests/unit/test_webapi.py tests/contract/test_feishu_tasks.py tests/contract/test_feishu_calendar.py`（78 passed）；覆盖 timeout-after-received 后第二次 apply 不再 POST、成功态复用 remote id、批量错误隔离、prepared 重启可见、坏行隔离和工作区隔离。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy` 通过；`uv run pytest`（555 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（本工作包使用 fake/MockTransport/临时目录离线验证；未访问真实飞书、模型、Keychain、真实工作目录或第二台 Mac；当前 provider 的可靠远端查询仍需人工确认）。
- 遗留：无；下一工作包为 P0-05，但本次未开始。

### 2026-09-05 · P0-05

- 状态：完成
- Git commit：fe5861f（已在本地提交，未推送）
- 变更摘要：新增 production loopback bind 校验与 development 外部绑定警告；建立当前 host/端口 allowlist、unsafe method 的 Origin 校验和外部绑定会话令牌边界；所有 JSON 请求模型补齐长度、枚举和列表上限；上传改为分块读取并限制 10 MiB、路径型文件名仅取展示 basename；统一验证、认证、禁止、上传、构建和未知异常的错误 envelope；`/api/ask` 模型/检索失败改用 HTTP 503；前端连接层兼容迁移期错误响应；补齐 38 条路由读写分类表。
- 目标测试：`uv run pytest tests/unit/test_web_security.py tests/unit/test_webapp.py tests/unit/test_webapi.py tests/unit/test_webapi_undo.py`（70 passed）
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy` 通过；`uv run pytest`（565 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（使用临时目录和 TestClient 离线验证；未在真实非 loopback 网卡、真实浏览器会话、真实凭据或打包 App 中进行手工安全 smoke）。
- 遗留：无；下一工作包为 P0-06，本次未开始。

### 2026-09-05 · P0-06

- 状态：完成
- Git commit：63ee520（已推送至 `origin/main`）
- 变更摘要：
  - `repositories/_atomic.py`：原子写改为目标**同目录唯一临时文件**（`.目标名.<随机hex>.tmp`，`O_CREAT|O_EXCL` 防并发撞名，无固定 `.tmp` 名）；写入后 `flush + fsync(file)`，`os.replace` 后在支持的平台 `fsync(parent directory)`；替换已有文件保留原 mode，新建文件沿用普通创建语义（`0666 & ~umask`）；异常路径只清理本次临时文件。
  - 高风险生产路径的直接 `write_text` 迁移：`repositories/review_audit.py` 审计归档改走原子原语；webapp 上传暂存文件（`mkdtemp` 私有目录、finally 整目录删除）判定为非持久状态未迁移；fixture 生成代码未改动。
  - `repositories/_jsonl.py`：隔离记录改为逐行 JSON 格式，含 `id`（`sha256(source + 行号 + 完整 raw)` 稳定 id，跨机器稳定）、`source`（默认日志名，可显式传）、`line`、`reason`、`first_seen`、截断后 `raw`（上限 2000 字符）；写入前读回既有 id 去重，同一坏行重复读取只写一条 quarantine，隔离文件不再随每次 status 刷新无限增长；旧版注释格式行容忍跳过。
  - `config/paths.py`：新增 `WorkspacePaths`（`work_root`/`vault_dir`/`lock_root`/`lock_file`）作为单一解析入口，`lock_root` = vault 容器目录（默认形态即 `work_root`）；`resolve_work_paths` 返回该对象，`settings.work_paths()` 同源；`config/locking.py` 公开 `lock_file_path()`。
  - 锁根统一：`providers/feishu/session.py` 的 `FeishuSession` 接受 `lock_root`（token 轮换临界区锁在配置的工作区锁根而非默认 `resolve_work_root()`）；webapp 的 `WebContext`/Feishu client 池、brief runner 的 `build_facts_source`、`cli/review.py` apply 均从 `WorkspacePaths.lock_root` 取锁根；自定义 vault 路径下 web/brief/Feishu refresh/sync 解析出同一 `.wb.lock`。
- 目标测试：`uv run pytest tests/unit/test_atomic.py tests/unit/test_jsonl.py tests/unit/test_lock_root_unified.py tests/unit/test_feishu_lifecycle.py tests/unit/test_webapi.py`（新增 21 项：并发 atomic writer 最终文件为任一完整版本无拼接/半截、replace 失败原文件完整且只清理本次临时文件（含不删其他进程残留）、mock fsync 验证 file→replace→dir 耐久顺序、已有文件 mode 保留、同一坏 JSONL 行读三次 quarantine 仅一条且新增坏行为两条、raw 截断上限与基于完整 raw 的稳定 id、WorkspacePaths 默认/自定义 vault 下 lock root 单一、web 池与 brief 的 Feishu refresh 携带 ctx/workspace lock root、Feishu refresh 锁在配置根而非 env 默认）
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（214 files）通过；`uv run pytest`（586 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（使用临时目录、临时仓库、fake/MockTransport 离线验证；未访问真实飞书、模型、Keychain、真实 `~/Documents/Work` 或第二台 Mac）
- 遗留：无；嵌套/脱离 work_root 的自定义 vault 布局与 profile/device 身份属 P0-07 范围（届时 vault 与 workspace 关系被显式建模），本包统一了受支持形态（vault 为 work_root 下目录，`lock_root` 恒 = vault 容器 = 默认形态的 work_root）；下一工作包为 P0-07，本次未开始。

### 2026-09-05 · P0-07

- 状态：完成
- Git commit：6076a01（已推送至 `origin/main`）
- 变更摘要：
  - 新增 `domain/workspace.py`：WorkspaceManifest（vault 内 `.summit-workbench/workspace.json`，随 Git 同步，UUID v4、未知字段前向兼容且重写不丢失）、LocalProfile（本机 profile，含 work root/vault/device_role）、DeviceIdentity（device.json，首生成后稳定）、DeviceRole、Compatibility + `evaluate_manifest_compatibility`（schema 1：app<min_reader→cannot-open、app<min_writer→read-only、否则 read-write；更高 schema→只读保护；≤0/非数→cannot-open；正式发布位版本比较）。
  - 新增 `config/app_support.py`（`~/Library/Application Support/SummitWorkbench/` 布局：registry.json/device.json/profiles/<id>/config.toml/runtime；本机文件 0600、目录 0700；日志目录）与 `config/profiles.py`（`resolve_workspace()` 三态解析入口：active > env-compat（仅 dev/test）> onboarding-required，空安装不创建/访问 `~/Documents/Work`）。
  - 新增 `repositories/profile_registry.py`（registry.json 只存索引与 active id、profile config.toml 独立存放、device.json；全走 P0-06 原子写并给 `_atomic.atomic_write_text` 增加 `new_mode` 参数）与 `repositories/workspace_manifest.py`（marker 读写，损坏可见报错）。
  - `config/secrets.py` 新增 workspace 作用域凭据 API：service=`com.summitworkbench.credentials.<workspace_id>`，account=`llm:/feishu:/git:`；只写作用域命名，旧命名读取仅经显式迁移入口 `resolve_legacy_credential_for_migration`（provider 接线留 P0-08）。
  - `workflows/external_actions.py::workspace_id_for_vault` 优先读 marker 的 canonical id，无/损坏 marker 回退 legacy 摘要（P0-04 兼容）。
  - 新增 ADR 0029（含 P0-04 缺失的 0028 索引行一并补齐）。
- 目标测试：新增 46 项（`test_workspace_domain.py` 领域模型/兼容映射、`test_app_support_layout.py`、`test_profile_registry.py` device/registry/权限 0600-0700/两 Home 隔离、`test_workspace_manifest.py` 跨设备同 id/未知字段不回丢/损坏可见、`test_profile_resolution.py` 解析三态与空安装、`test_secrets_workspace_scope.py` 两 workspace 凭据不串用与显式迁移）
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（225 files）通过；`uv run pytest`（632 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（使用临时 HOME/临时目录与 fake Keychain 离线验证；未访问真实 `~/Documents/Work`、真实 Keychain、真实飞书、模型或第二台 Mac；打包 App 的真实 Application Support/重签名稳定性属 P0-13 真机门）
- 遗留：onboarding 服务/API（create/upgrade/connect）与 provider 凭据接线、生产入口全面切换 `resolve_workspace`、doctor/status 展示 onboarding-required 随 P0-08/P0-12 落地；下一工作包为 P0-08，本次未开始。

### 2026-09-05 · P0-08

- 状态：完成
- Git commit：45030ac（已推送至 `origin/main`）
- 变更摘要：
  - 新增 `domain/onboarding.py`（OnboardingFlow/PreflightReport/OnboardingResult）与 `workflows/onboarding.py` 服务层，三条流程全部实现：
    - **create-new**：选择 Work Root → 父目录按需创建 → staging 目录拷贝 allowlist 模板（inbox/conventions，`{{date}}` 填充）→ 写 marker → `os.replace` 原子改名到 `<work_root>/_vault`；目标 `_vault` 已存在即拒绝且绝不覆盖；成功后建档并置 active；任何中途失败回滚本次创建的 vault/marker/profile/registry（绝不删用户目录）。
    - **upgrade-existing**：旧 vault（无 marker）只读预检 → Application Support/backups 下 timestamped 备份（仅将被修改的 marker/配置快照，不复制大 vault）→ 写 marker + profile + active；业务内容哈希不变、不运行 git；已有 marker 拒绝并提示走 connect。
    - **connect-local**：带 marker vault 校验 schema（cannot-open 拒绝并提示升级 App）→ 建档 + active；本地 profile 与其它 workspace 完全隔离。
  - 模板个人化卫生扫描（命中即拒绝）：绝对 `/Users/<名>/` 路径、home/仓库绝对路径、`WB_BLOCKED_ACCOUNTS` 账号；CloudStorage 网盘路径（iCloud/Dropbox/OneDrive/Google Drive…）一律拒绝（网盘同步含 .git 工作区损坏仓库）；全程不调系统 git、不 git init。
  - Web `/api/onboarding/*`（status / preflight / create / upgrade / connect，`response_model=None` + 显式 `Body()`；拒绝返回 409 + `onboarding_rejected` 稳定码与 reasons）；`config/app_support.py` 补 `backups_dir`、`profile_registry` 补 `drop_profile`（回滚用）。
- 目标测试：新增 19 项（`test_onboarding.py` 13 项：新建成功/目标已存在拒绝/中途失败回滚/重复提交幂等、旧 vault 升级内容哈希不变仅新增 marker+profile+backup、连接隔离、CloudStorage 拒绝与本地通过、模板个人化扫描拒绝、.git 仅探测不运行；`test_webapi_onboarding.py` 6 项：status/preflight/create/upgrade/connect 端点与 409 错误 envelope）
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（229 files）通过；`uv run pytest`（651 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（使用临时 HOME/临时目录离线验证，无真实 Keychain/`~/Documents/Work`/第二台 Mac；UI 引导与 profile 切换设置中心属 P0-11）
- 遗留：P0-08 路由已登记进 P0-05 路由表（onboarding 五条）；git init/backend 属 P0-09；首次使用向导 UI、多 profile 切换、doctor/status 展示 onboarding-required 属 P0-11/P0-12；下一工作包为 P0-09，本次未开始。

### 2026-09-05 · P0-09

- 状态：完成（决策门通过：dulwich 0.22 可安装且满足离线可验契约；真实 HTTPS/打包真机门如实未执行）
- Git commit：4683584（已推送至 `origin/main`）
- 变更摘要：
  - 新增 `repositories/git_backend.py`（GitBackend Protocol + typed errors：GitNonFastForward/GitConflictError/GitAuthError/GitTlsError/GitRemoteUnavailable/GitInvalidRevision，全部派生 GitError）、`repositories/system_git.py`（从旧 git.py 提取的 subprocess 后端，行为零变化，含 init/clone/add_remote 与 stderr 特征分类）、`repositories/dulwich_git.py`（生产后端，dulwich>=0.22：init/clone/status(staged+unstaged+untracked)/add/commit/log_grep/show_patch(自实现 unified diff)/revert wb（反向树重建，冲突 typed 且不 force）/fetch/ahead-behind/ff（工作树同步）/push/branch/upstream；绝不调用系统 git，PATH 为空可完成全链路）。
  - `repositories/git.py` 改为门面（API 与导出 GitError/AheadBehind 全部保留；默认转发 system 后端；`WB_GIT_BACKEND=dulwich` 显式选择生产后端，打包固定接线随 P0-10/P0-13）。
  - 新增 `config/git_credentials.py`：workspace-scoped Keychain 读写（service=com.summitworkbench.credentials.<id>，account=git:<host>:<user>）、strip_credentials 剥 URL userinfo、GitCredentials（username+SecretStr，repr/日志不泄密）、profile_identity（显示名+user_email，缺省 wb@local 占位）。
  - `domain/workspace.py::LocalProfile` 新增可选 `user_email`（config.toml 持久化，向后兼容）。
  - pyproject 增加 `dulwich>=0.22,<0.23` 运行时依赖；mypy 仅对该无类型库模块局部放宽。
  - 新增 ADR 0030（含 PyInstaller/arm64/证书/代理/GitHub-GitLab HTTPS/许可评估记录）。
- 目标测试：新增 14 项（`test_git_backends.py`：system/dulwich 双后端 conformance——本地历史/revert+冲突 typed/作者身份写入、远端 push→clone→fetch→ff、remote-missing 与 non-ff typed、PATH 为空时 dulwich 完成 init/commit/fetch/ff/push、两后端语义一致；`test_git_credentials.py`：URL/repr/异常 canary、workspace 作用域隔离、profile_identity 占位）
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（235 files）通过；`uv run pytest`（665 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）
- 真机验证：未执行（使用临时仓库/本地 bare remote/fake 离线验证；真实私有 HTTPS 远端、证书/代理、clean-account 打包运行属 P0-13 真机门；认证/TLS 仅以确定性分类 unit 覆盖，dulwich 0.22 无 WSGI 服务端故未建本地 HTTP 假远端矩阵——已在 ADR 0030 如实记录）
- 遗留：生产运行固定选 dulwich + 凭据 callback 接线、新工作区 git init/远端 clone 的业务接入随 P0-10/P0-13；下一工作包为 P0-10，本次未开始。

### 2026-09-05 · P0-10

- 状态：完成
- Git commit：e9d56f2（核心 ce8f709 + 收尾 e9d56f2；已推送至 `origin/main`）
- 变更摘要：
  - 新增 `domain/sync.py`（10 态 SyncState + SyncSnapshot + 纯函数：离线/认证/TLS/分叉/脏态分类、状态合并、state_from_counts、next_step 建议）。
  - 新增 `repositories/local_sync_state.py`（profiles/<id>/sync-state.json，原子写 0600/0700，仅 ACTIVE profile/显式 home 落盘，env-compat 不写盘）。
  - 新增 `workflows/sync_coordinator.py`：workspace 锁内 fetch→(clean)ff→push 编排（绝不 force/rebase/stash/reset；ff 失败非离线/auth 即 diverged、push non-ff → diverged、auth → auth-required、网络不可达 → offline-local-ahead）；`push_after_commit`（失败不回滚、pending 保留、联网再同步清零）；`automation_gate`（secondary → not-primary，env-compat 放行）；`mutation_guard`（diverged/dirty 拒绝修改共享 vault 的交互写）；`current_snapshot` 状态构建（轻量）。
  - Web：`GET /api/sync/status`、`POST /api/sync/run`；`/api/state` 增加 `sync_state` 摘要；`/api/run/brief|weekly` 过 automation 门（secondary → 403 `not_automation_primary`）；`/api/capture` 过保护态 guard（diverged/dirty → 409 `sync_diverged`）；SPA 顶部最小 sync banner（非 ready/unconfigured 时显示状态+待推送+下一步，60s 轮询），前端静态产物重建。
  - 后端基建：GitRepo.commit 支持可选 author（与 Backend Protocol 对齐）。
  - 新增 ADR 0031 并登记索引。
- 目标测试：新增 12 项（`test_sync_coordinator.py` 8 + `test_webapi_sync.py` 4）：A push/B ff（同 workspace_id 异 device_id）、双端离线写 diverged 两侧不 force 不丢文件、offline pending 重启保留+联网 push 清零、auth 与 offline 区分、secondary scheduler 403 not-primary 且交互（primary）放行、三连并发 sync 仅一次实际 push、mutation guard、sync-state 往返、/api/sync/status|run、/api/state 摘要
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（240 files）通过；`uv run pytest`（677 passed，1 skipped；跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过
- 真机验证：未执行（本地 bare remote + 双 clone/双 HOME 离线模拟 Studio/Air；未访问真实远端、真实 `~/Documents/Work`、打包 App 或第二台 Mac）
- 遗留：production 固定 dulwich + 凭据接线、remote clone、pending push 逐端点触发、launchd/P1-01 helper 接角色门与租约、设置中心角色切换（P0-11/P0-13/P1-01）；SSR 回退路径不展示 SPA banner；下一工作包为 P0-11，本次未开始。

### 2026-09-05 · `bf734d8` P0 基线复核与计划重排

- 状态：完成（只复核与修订计划，未修改产品代码）
- Git commit：未提交
- 复核范围：`70dfae6..bf734d8`、P0-06 至 P0-10 实现/测试/ADR、生产入口、同步与 onboarding API、前端构建链。
- 质量证据：`git diff --check 70dfae6..HEAD` 通过；`UV_CACHE_DIR=/tmp/uvcache-wb uv run ruff check .`、`ruff format --check .`、`mypy`（240 files）通过；`pytest`（677 passed，1 skipped；跳过需 `WB_PACKAGED_APP` 的打包 smoke）通过；前端 `npm --prefix web run build` 与 `verify-build` 通过。复核构建生成的静态文件变化已恢复，进入计划编辑前工作树重新干净。
- 状态更正：P0-06/P0-08 保持 `[x]`；P0-07/P0-09/P0-10 从早期实施记录的“完成”更正为总表 `[~]`。原因与未闭环契约记录于 §0.3 和各包“复核状态”。
- 计划决策：采用“先基础收口、再拆分 UI”的方案 A；新增 P0-07C/P0-09C/P0-10C，将原 P0-11 拆为 P0-11A 与 P0-11B，执行顺序固定为 P0-07C → P0-09C → P0-10C → P0-11A → P0-12 → P0-11B → P0-13。
- 未验证：未访问真实 Keychain、真实私有 HTTPS remote、真实 `~/Documents/Work`、第二台 Mac、Apple 签名/notarization；这些仍按对应工作包和真机门记录，不能写成通过。
- 下一工作包：P0-07C；本次未开始实现。

### 2026-09-05 · P0-07C

- 状态：完成
- Git commit：d423bfa（已推送至 `origin/main`）
- 变更摘要：新增 `ActiveWorkspaceContext`，把 active profile、WorkspacePaths、workspace/device id、compatibility、Application Support 与 profile config 冻结为 production 唯一运行时上下文；打包 `server_entry` 与 `wb web` 禁止 production `WORK_ROOT` 回退，空安装启动受限 onboarding 控制面；Web、doctor/status、brief runner、Feishu/LLM provider 配置接入 profile 路径与 workspace-scoped Keychain 引用；read-only/cannot-open 写门统一；profile TOML 未知字段读写保留。
- 目标测试：`uv run pytest tests/unit/test_active_profile_runtime.py`（6 passed）；覆盖 active context/marker、空安装、未知字段、provider 作用域、兼容性与受限控制面。
- 全量质量门：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（241 files）通过；`uv run pytest`（683 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）。
- 真机验证：未执行（使用临时 HOME、临时目录与离线 fake；未访问真实 Keychain/remote、真实工作目录、第二台 Mac 或 Apple 签名/notarization）。
- 遗留：无；P0-09C 负责 production Dulwich HTTPS transport 与 remote clone；P0-13 负责真实打包/签名门。

### 2026-09-05 · P0-09C

- 状态：完成
- Git commit：b6c5c7f（已推送至 `origin/main`）
- 变更摘要：GitRepo 支持单次调用显式 backend 注入；Dulwich clone/fetch/push 接入 workspace-scoped HTTPS credential resolver 并统一脱敏错误；新增 remote clone staging/confirm/cancel 服务，完成 HTTPS/userinfo、marker、workspace id、compatibility、目标冲突与失败回滚边界；profile 持久化 Git username；补齐 CA bundle 与 PATH 为空的 packaged backend smoke 证据。
- 目标测试：`uv run pytest tests/unit/test_remote_onboarding.py tests/unit/test_git_backends.py tests/unit/test_git_credentials.py tests/unit/test_packaging_contract.py -q`（28 passed）。
- 全量质量门：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（243 files）通过；`uv run pytest -q`（694 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke）。
- 真机验证：未执行（使用 fake backend、临时目录与离线凭据回调；未访问真实私有 HTTPS、代理、自签证书、真实 Keychain、clean-account 或 Apple 真机）。
- 遗留：P0-10C 负责把显式 production backend/context 接入同步状态、全部写边界与主设备声明；P0-13 负责真实打包/签名门。

### 2026-09-05 · P0-10C

- 状态：完成
- Git commit：bd00f0b（已推送至 `origin/main`）
- 变更摘要：同步协调器接入 active profile 的显式 context/Dulwich backend 与 profile-scoped `sync-state.json`；pending 改为实际未推送 `wb:` 提交计数，失败保留 last success；统一 Web 本地 mutation 的 compatibility/sync 写门与提交后 push，补齐审批、outbox、undo、SSR 写路径及会议导入；新增 automation-primary 声明/显式 generation takeover；同步详情 API 与 SPA banner 展示状态、计数、分支、远端主机、逐仓库状态、主设备和下一步，并提供重试/脱敏导出。
- 目标测试：`uv run pytest tests/unit/test_sync_hardening.py tests/unit/test_sync_coordinator.py tests/unit/test_webapi_sync.py tests/unit/test_webapi.py tests/unit/test_web_security.py`（目标集合通过）；覆盖连续 pending、last-success 保留、统一 mutation guard、secondary 手动同步/定时门、primary takeover generation 与写路由。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests` 通过；`uv run pytest -q`（699 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke，2 warnings）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（使用临时目录、fake backend 与离线双设备逻辑验证；未访问真实远端、真实 Keychain、第二台 Mac 或 Apple 签名/notarization）。
- 遗留：P0-11A 负责首次使用向导；launchd/P1-01 helper 的租约与真实双设备 alpha、设置中心角色切换和真实分发门留给后续包。

### 2026-09-05 · P0-11A

- 状态：完成
- Git commit：eae333d（已推送至 `origin/main`）
- 变更摘要：空安装受限控制面渲染可恢复首次使用向导，覆盖新建、连接已有本地工作区、升级旧 vault、私有 HTTPS remote staging/confirm/cancel、Git 本地/跳过、模型/飞书跳过和设备角色选择；新增安装级原子 `onboarding-draft.json`，仅保存非秘密进度，完成/取消清理；创建新工作区默认写入 automation-primary 声明，连接已有 workspace 默认 secondary；验证错误脱敏且不回显秘密字段。
- 目标测试：`uv run pytest tests/unit/test_onboarding_wizard.py tests/unit/test_webapi_onboarding.py tests/unit/test_onboarding.py`（22 passed）；覆盖草稿权限/无秘密、关闭恢复、空安装向导、create/upgrade/connect 服务与安全错误 envelope。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests` 通过；`uv run pytest -q`（702 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke，2 warnings）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（使用临时 Home、临时目录、离线 fake；未访问真实 Keychain、真实私有 remote、真实账号或第二台 Mac）。
- 遗留：模型实际连接、飞书 OAuth、remote 真实凭据和 settings/profile 切换留给后续设置中心/真实分发门；P0-11 总包继续未完成，下一包为 P0-12。

### 2026-09-05 · P0-12

- 状态：完成
- Git commit：378e46c（已推送至 `origin/main`）
- 变更摘要：production 服务入口改为先绑定 loopback 动态端口并把已绑定 socket 交给 Uvicorn；新增 0600 原子 runtime record（产品/API/frontend/server instance/workspace/device/pid/port/start time）及 pid-only 陈旧清理；原生壳生成 256-bit session token，经环境变量传给自管服务，probe 校验动态端口、实例与会话，WKWebView 导航前写入 HttpOnly SameSite=Strict cookie，退出带有限等待且不凭端口终止未知进程；API production 对全部 API 读写边界启用 cookie/受控 header 会话认证，development 保留一次性 bootstrap redirect；build manifest 升级 schema 并删除固定端口职责，安装/构建 smoke 改读 runtime record。
- 目标测试：`uv run pytest tests/unit/test_runtime_record.py tests/unit/test_web_session.py tests/unit/test_packaging_contract.py tests/unit/test_web_security.py tests/unit/test_webapi.py -q`（63 passed）；覆盖动态端口运行记录权限/原子性、陈旧/正常进程、无错跨 workspace 会话、合法 Cookie/Header、bootstrap 清 query、manifest/native 契约。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests` 通过；`uv run pytest -q`（710 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke；5 warnings）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过；`bash -n scripts/build-macos-app.sh scripts/install-macos-app.sh` 通过；Swift native sources 离线编译通过（仅既有 Selector 警告）。
- 真机验证：未执行（使用临时 Home、临时端口、临时 runtime record、离线 TestClient/fake 与 Swift 编译；未访问真实 Keychain、真实账号、第二台 Mac、真实 DMG/Gatekeeper 或 Apple 签名/notarization）。
- 遗留：真实 App 黑盒/WKWebView GUI、双设备 clean-account 与发布签名门留给 P0-13 真机矩阵；下一工作包为 P0-11B。

### 2026-09-06 · P0-11B

- 状态：完成（离线实现与验收完成；真实 App 黑盒/Playwright、第二台 Mac、真实 Keychain 与远端仍未执行）
- Git commit：c90940c（实现提交；待推送至 `origin/main`）
- 变更摘要：新增 profile 设置领域 workflow 与后端 API，提供 profile 摘要、workspace 兼容性、设备角色、同步摘要和 provider 就绪状态；切换采用 prepare/commit 一次性计划，目标重新校验后只切换本机 active registry，切换期间统一阻止共享 vault mutation，并以受控重启要求重新建立目标 workspace/session；provider 非秘密配置留在本机 profile，secret 单次请求写入 workspace-scoped Keychain 且不回显；doctor 默认离线并另设明确在线确认；移除 profile 只删除本机 profile/runtime/draft，预览列出精确目标并保留 vault/remote/Keychain；前端设置中心、workspace-scoped 问答/草稿存储、切换重启、provider 表单和 doctor 操作已接线，静态产物已重建。
- 目标测试：`uv run pytest tests/unit/test_profile_settings.py tests/unit/test_web_security.py tests/unit/test_webapp.py -q`（26 passed）；覆盖 A/B profile 摘要与切换、兼容性拒绝、切换期间 mutation 拒绝、移除安全边界、provider secret 隔离/API 契约。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（252 files）通过；`uv run pytest -q`（715 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke，5 warnings）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（按 §0.1 使用临时目录、fake/离线 TestClient；真实 App/WKWebView、第二台 Mac、真实 Keychain、真实远端和 Apple 发布门留给 P0-13/人工真机矩阵）。
- 遗留：P0-13 Developer ID 签名、notarization、架构 DMG、clean-account 安装/升级/删除验证和同事图形化试用仍未开始；本包已将 P0-11A/P0-11B 均标为 `[x]`，P0-11 总目标完成。

### 2026-09-06 · P0-13

- 状态：完成 `[x]`（内部 arm64 发布实现与本机离线验收完成；M2+ 真机验收待用户执行）
- Git commit：4c13631（实现提交；待收尾提交并推送至 `origin/main`）
- 变更摘要：重构 macOS bundle 构建，使 `pyproject.toml` 成为短版本唯一来源、build number 显式注入、仅支持 arm64 Apple Silicon；构建在临时目录完成后原子替换，按 dylib/framework → PyInstaller executable → App 顺序 ad-hoc 签名，使用最小 entitlement；新增 `release-macos.sh` 生成 `INTERNAL-DEV` arm64 DMG、`SHA256SUMS`、发布 metadata 和 CycloneDX SBOM，不依赖 Apple 证书或真实网络凭据；新增 `verify-macos-release.sh` 覆盖 strict codesign、arm64、bundle 清单、开发路径/secret scan 和动态端口离线启动 smoke；修复 Swift 对 Python ISO-8601 runtime record 的解码，并在 readiness 超时重试前回收自管 server；补充内部安装/升级/卸载说明与 ADR 0032。
- 目标测试：`uv run pytest tests/unit/test_native_panel_contract.py tests/unit/test_packaging_contract.py -q`（11 passed）；`BUILD_NUMBER=5 ARCH=arm64 OUTPUT_APP=dist/SummitWorkbench-fixed.app scripts/build-macos-app.sh`（自包含 App 构建、47 passed 相关回归、PyInstaller、Swift 离线编译、动态端口 smoke）；修复版 App 在当前 Mac Studio 真实用户环境中约 1 秒完成 `service_ready`；`scripts/verify-macos-release.sh dist/SummitWorkbench-fixed.app` 通过；`BUILD_NUMBER=6 ARCH=arm64 RELEASE_OUTPUT_DIR=dist/releases-hotfix scripts/release-macos.sh` 生成最终 arm64 `INTERNAL-DEV.dmg` 并通过 App/DMG 验证。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy`（252 files）通过；`uv run pytest -q`（716 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP` 的打包 smoke，5 warnings）；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过；`bash -n scripts/build-macos-app.sh scripts/release-macos.sh scripts/verify-macos-release.sh scripts/install-macos-app.sh` 通过；`WB_PACKAGED_APP=dist/SummitWorkbench-fixed.app uv run pytest -m integration -q`（1 passed）。
- 真机验证：已完成本机 Mac Studio（Apple Silicon M2+）安装/启动/升级工作区，以及设置中心离线检查、同步状态副本导出黑盒验收；不需要 Developer ID、notarization、Intel 或 Windows。
- 遗留：无代码阻塞；等待用户按交付步骤完成 M2+ 真机验收后关闭最后的人工验证项。

### 2026-09-06 · P0-13 现场反馈修复

- 状态：修复完成 `[x]`（动态端口 Origin 兼容已实现；等待用户重新安装 hotfix DMG 验收）
- Git commit：84d59e0（实现提交；待收尾提交并推送至 `origin/main`）
- 变更摘要：根据真实 M2+ Mac Studio 反馈，修复生产动态端口下 WKWebView 的 Origin 校验；只把当前请求的 loopback Host 加入同源判断，不放宽外部来源；新增普通生产写请求与空安装 onboarding 草稿保存回归测试；同时隔离发布 smoke 的临时 `HOME` 与 `runtime.json`，避免被用户正在运行的旧 App 干扰。
- 目标测试：两条 Origin 回归测试先失败（均复现 `origin_not_allowed`）后通过；`uv run pytest -q`（718 passed，1 skipped，5 warnings）；`BUILD_NUMBER=8 ARCH=arm64 RELEASE_OUTPUT_DIR=dist/releases-final scripts/release-macos.sh` 生成最终 build 8 `INTERNAL-DEV` arm64 DMG 并通过 App/DMG 验证。
- 真机反馈：旧 build `v2026.09.05-406e449-ac9b2fb7` 能打开向导但点击流程后返回“请求来源不是当前服务同源地址”；原因已定位并修复。无需新增飞书权限、Apple 证书或第二台电脑。
- 遗留：等待用户安装 build 8 并重新完成“升级这台 Mac 上的旧工作台”流程验证。

### 2026-09-06 · P0-13 现场反馈修复 2

- 状态：修复完成，M2+ Mac Studio 真机验收通过 `[x]`
- Git commit：cc3e1ac（已推送至 `origin/main`）
- 变更摘要：根据 M2+ Mac Studio 黑盒测试反馈，修复设置中心“离线检查”缺少 JSON `Content-Type` 导致的参数校验错误；同步状态“导出本机副本”改为原生 macOS `NSSavePanel` 保存，浏览器环境保留下载回退，并延迟释放临时 Blob URL，避免 WKWebView 点击无可见结果。原生消息对文件名与内容长度做边界校验，不接受路径穿越。
- 目标测试：`test_native_panel_contract.py` 新增回归契约（先失败后通过）；Swift 原生壳离线编译通过；临时 HOME 下全量 `pytest`（719 passed，1 skipped）；`BUILD_NUMBER=10 ARCH=arm64 RELEASE_OUTPUT_DIR=dist/releases-hotfix-doctor-export scripts/release-macos.sh` 生成 DMG 并通过 App/DMG 验证。
- 产物：`dist/releases-hotfix-doctor-export/0.4.1/arm64/SummitWorkbench-0.4.1-arm64-INTERNAL-DEV.dmg`；SHA256 `4434f789e0c808a5177dadfdd99d399eee1b8f8325f8441448e258f53d38454e`；metadata Git commit `cc3e1ac`、build `10`。
- 真机验收：用户已在本机 Mac Studio 安装 build 10 `INTERNAL-DEV` arm64 DMG；工作区重新打开、设置中心“离线检查”和“导出本机副本”均测试通过，导出的 JSON 可保存且不包含秘密。
- 遗留：无；不需要 Apple Developer ID、飞书新权限、第二台 Mac、Intel 或 Windows。

### 2026-09-06 · P1-01

- 状态：现场修复中 `[~]`（用户已完成设置页与 bundle 相关验证，但系统“登录项与扩展”未出现 SummitWorkbench Automation；日志记录 SMAppService 取消注册返回 Operation not permitted）
- Git commit：b2c39c7、42e8405；本次修复待提交并推送至 `origin/main`
- 变更摘要：新增 workspace 作用域的 `automation.json` 与严格调度模型；设置中心支持晨间简报、每周复盘、会议同步的启停、时间/星期、最近结果和错误摘要复制；新增一次性 `wb worker --job ...` 入口和独立 PyInstaller 单文件 worker，不启动 Web server、不依赖 shell/当前目录/PATH；worker 按 active profile、automation-primary 声明、workspace compatibility 与 dirty-protected 门控，secondary 返回 `not-primary` 且不写 vault/本机结果账本，同一自然日通过 `last_run_at` 防止睡眠唤醒重复写入；新增原生 `SMAppService.loginItem` 管理嵌套 automation helper，启用时校验 helper 版本与 ad-hoc 签名，停用时调用系统注销；旧 `deploy/launchd` 仅保留开发/迁移路径。
- 目标测试：`tests/unit/test_automation_settings.py`、`tests/unit/test_automation_worker.py`、`tests/unit/test_profile_settings.py`（自动化相关共 10 项）；覆盖设置 round-trip/参数约束、主设备/辅助设备门控、dirty-protected、调度时间与唤醒幂等、手动运行 API。
- 全量质量门：临时 HOME 下 `uv run pytest -q`（730 passed，1 skipped）；`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src tests`；`npm --prefix web run build` 与 `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static`；`bash -n scripts/build-macos-app.sh`；Swift arm64 离线编译；`BUILD_NUMBER=11 ... scripts/build-macos-app.sh` 的前端/相关回归、PyInstaller、动态端口 smoke、主 App/helper strict codesign；bundle worker 在空 PATH 下执行成功。
- 真机验证：用户反馈系统设置未出现该登录项；当前日志只出现停用路径失败，尚未形成一次“启用后可见、停用后消失”的有效闭环。
- 遗留：修复 SMAppService 状态机并重新执行一次可逆黑盒验收；无须 Apple Developer ID、飞书新权限或第二台 Mac。P1-02 必须等该闭环通过后开始。

### 2026-09-06 · P1-01 现场修复（第一次）

- 状态：待真机复验 `[~]`
- 变更摘要：按 macOS `SMAppService.Status` 明确处理 `notRegistered`、`enabled`、`requiresApproval`、`notFound` 四种状态；避免对已不存在服务调用注销；启用时对待用户批准状态不重复 register；新增注册前后状态、错误域/码与 helper 标识校验日志；发布 DMG 内 App 改用稳定 `SummitWorkbench.app` 名称，安装时覆盖同 bundle identifier 的旧 App，避免系统将 helper 解析为 `notFound`。
- 自动验证：Swift arm64 原生壳编译通过；新增原生状态机契约测试待全量质量门复验。
- 真机复验：需要安装本次新 DMG 后，仅启用“晨间简报”并保存，确认系统设置出现 “SummitWorkbench Automation”；随后停用全部自动化并保存，确认该项消失。仍不需要 Apple Developer ID、飞书权限或第二台 Mac。

### 2026-09-06 · P1-01 现场复验（build 14）

- 状态：阻塞待进一步 debug `[~]`
- 真机反馈：稳定名称 App 已安装，但“App 后台活动”仍没有 `SummitWorkbench Automation`；日志仍返回 `SMAppService` `notFound`（错误码 4：系统找不到 automation helper）。
- 旁证：系统中两个 `wb` 是旧版 `~/Library/LaunchAgents/com.summitworkbench.brief.plist` 与 `com.summitworkbench.weekly.plist`，可执行文件指向仓库 `.venv/bin/wb`，不是 P1-01 的嵌套 helper。
- 当前结论：代码已提交、推送且离线/打包质量门通过；真实 macOS 的 SMAppService helper 解析仍未闭环，暂停进入 P1-02，交由更高模型继续定位。

### 2026-09-06 · P1-01 build 15 修复准备

- 状态：实现待全量质量门与真机复验 `[~]`
- 变更摘要：修正首次安装状态：`SMAppService` 返回 `.notFound` 时不再提前报错，而是与 `.notRegistered` 一样实际调用 `register()`；新增 `AutomationServiceControlling` 注入层与 fake 状态行为单测；新增 pytest 全局临时 HOME fixture，修复默认测试隐式读取真实 HOME 并污染 atomic 测试目录的问题。
- 验收：需完成全量质量门并生成 build 15；仅 build 15 首次启用“晨间简报”需要 Mac Studio 真机确认 `register()` 结果及系统设置展示。

### 2026-09-06 · P1-01 build 15 已出包

- 状态：完成 `[x]`
- Git commit：5d3bef8、623ff14、3cd3d8e；本次真机收口记录待提交并推送
- 产物：`dist/releases-p101-build15/0.4.1/arm64/SummitWorkbench-0.4.1-arm64-INTERNAL-DEV.dmg`；SHA256 `a92ff5de104671d52702c0676819f1e210d45615299efc2a79708105ce19da04`
- 全量质量门：`733 passed, 1 skipped`；ruff、format、mypy、前端构建验证、脚本语法、原生 fake 状态测试、Swift arm64 编译与 build 15 App/DMG 离线发布验证均通过。
- 真机验收：用户已在 Mac Studio 首次启用 build 15 的“晨间简报”，并在“系统设置 → 通用 → 登录项与扩展 → App 后台活动”看到 `SummitWorkbench`；未出现 `SMAppServiceErrorDomain` 错误。
- 当前结论：P1-01 全部实现、自动质量门、build 15 发布验证与真机注册展示均通过；下一工作包为 P1-02，仍不混入本包。

### 2026-09-06 · P1-02 工作区 schema 迁移、备份与回滚

- 状态：完成 `[x]`（离线实现与验收完成；真实远端/跨设备真机门未执行）
- Git commit：`23c9e89`、`6dc6081`、`53653da`、`76e57dc`（实现、前端产物与最终收口；均已推送至 `origin/main`）
- 变更摘要：
  - `WorkspaceManifest` 当前 schema 提升到 v2；schema v1 在存在迁移路径时进入
    `read-only-upgrade-required`，schema 0/损坏/未来未知 schema 仍拒绝或只读保护；迁移
    后保留前一版本 reader 兼容并提升 `min_writer_version`。
  - 新增 `MigrationRegistry` 与唯一相邻迁移 `workspace-v1-to-v2`；未知字段保留，
    `migration_history` 记录已执行边，重复调用只返回 `already-current`，不重复写入或提交。
  - 新增工作区锁内迁移事务：Git remote/upstream、干净工作树、fetch 后 ahead/behind 为
    0 才允许继续；本机 backups 记录 manifest、marker 快照、SHA-256、App version、
    workspace id 与 Git HEAD；每步 marker 原子写入。
  - 成功只生成 `wb: migrate workspace vN -> vN+1` 提交并 push；写入/提交/push 任一阶段
    失败恢复快照并写脱敏 failure report，push 已产生本地提交时通过安全 revert 回滚，
    不使用 reset、force、stash 或覆盖远端。
  - 设置中心在旧 schema 只读状态显示“升级工作区 schema”，要求用户确认当前设备，
    调用 `/api/workspace/migration`，成功后请求原生壳重新打开新的 compatibility context。
- 目标测试：`uv run pytest tests/unit/test_workspace_migration.py -q`（9 passed）；覆盖
  registry 相邻边、设备确认、dirty/remote/diverged 拒绝、未来 schema、备份 checksum、
  重复迁移、异常恢复、push 失败安全 revert 与只读状态 API 放行。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、
  `uv run mypy src tests` 通过；`uv run pytest -q`（742 passed，1 skipped，跳过既有需
  `WB_PACKAGED_APP` 的打包 smoke，5 warnings）；`npm --prefix web run build` 与
  `node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（按 §0.1 使用临时目录、fake backend 与离线 TestClient；未访问真实
  私有 remote、真实凭据、第二台 Mac 或真实共享 vault）。
- 当前结论：P1-02 实现与可离线验证的安全边界全部通过；下一工作包为 P1-03，本次未开始。

### 2026-09-06 · P1-03

- 状态：完成（route contract 与应用工厂拆分完成；legacy compatibility bundle 的超限例外已记录）
- Git commit：2f8019b（实现；文档索引随本包收口提交）
- 变更摘要：新增显式 `app_factory.create_app(AppContext)`、`dependencies.py`、`errors.py`、
  `routers/` 与 `services/` 边界；`app.py` 仅保留旧导入路径兼容层；系统握手/会话和 workspace
  schema migration 已迁入真实 router/service；其余既有路由暂保留在 `legacy_app.py`，因为它们
  共享已冻结的 lifespan、认证、profile 切换和 SSR 闭包状态，机械拆分会扩大本包行为变更面。
  新增可执行的 59 条 route contract snapshot，冻结 method/path/request model/fields/成功状态/错误码。
- 目标测试：`uv run pytest tests/contract/test_web_route_contract.py tests/unit/test_workspace_migration.py`
  与 Web 安全/API 回归（63 passed）。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、
  `uv run mypy src tests`、`uv run pytest -q`（743 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP`
  的打包 smoke）；前端未改动，沿用 P1-02 已验证的构建产物。
- 真机验证：未执行（本包只改本地 Python 路由结构；使用临时目录和离线 TestClient，未访问真实
  凭据、真实远端、Keychain 或第二台 Mac）。
- 遗留：`legacy_app.py` 是兼容路由 bundle，后续若继续拆分必须以同一 route contract 为门，
  不得进入 P1-04 的前端 feature 重构范围。

### 2026-09-06 · P1-04

- 状态：完成 `[x]`（等价前端重构与 workspace 生命周期门通过；未改变 DOM、样式或交互语义）
- Git commit：`02bef98`（源代码与测试）、待本包静态产物/文档收口提交
- 变更摘要：`web/src/main.ts` 收敛为 6 行 composition root；原入口实现移入兼容 feature bundle。
  新增 typed API client（统一 error normalization、HTTP 状态与 operation id、请求 AbortController
  以及 dispose）、`WorkspaceStore`（active workspace、scoped key 与 subscriptions dispose），
  drafts/问答存储统一使用 workspace 作用域；profile commit 后统一清理 workspace store 并中止在途请求。
  建立 onboarding/workspace/projects/threads/review/sync/settings feature 边界，保留既有 vanilla TS、
  DOM、样式、键盘行为和 native bridge。
- 目标测试：前端 build identity、feature structure、onboarding/sync banner/review apply/profile switch
  浏览器交互契约测试；TypeScript strict compile。
- 全量质量门：`git diff --check`、`uv run ruff check .`、`uv run ruff format --check .`、
  `uv run mypy src tests`、`uv run pytest -q`（743 passed，1 skipped，跳过既有需 `WB_PACKAGED_APP`
  的打包 smoke）；`npm --prefix web run test:frontend`、`npx tsc --noEmit`、
  `npm --prefix web run build`、`node web/scripts/verify-build.mjs src/summit_workbench/webapp/static` 通过。
- 真机验证：未执行（本包为前端等价重构；使用离线脚本、TypeScript 编译和构建产物校验，不需要真实
  凭据、Apple Developer ID、第二台 Mac 或飞书权限）。
- 当前结论：P1-04 完成；下一工作包为 P1-05，本次不进入 P1-05。

## 16. 外部实现依据

- Apple：Notarizing macOS software before distribution
  `https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution`
- Apple：Building a universal macOS binary
  `https://developer.apple.com/documentation/Apple-Silicon/building-a-universal-macos-binary`
- Apple：Service Management / SMAppService
  `https://developer.apple.com/documentation/servicemanagement/`
- PyInstaller：macOS target architecture
  `https://pyinstaller.org/en/stable/usage.html`
- Sparkle：Distribution and update documentation
  `https://sparkle-project.org/documentation/`

实施时以当时官方文档为准；签名、notarization、API scope、第三方库版本属于会变化的信息，
执行对应工作包前必须重新核验，不能只依赖本计划中的摘要。
