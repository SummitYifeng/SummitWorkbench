# ADR 0045 · v0.4.4 UI/UX 与交付稳定性收口

- 状态：✅ 已实现并验收
- 日期：2026-09-10
- 里程碑：v0.4.4
- 依据：[WEB_USAGE_GUIDE.md](../product/WEB_USAGE_GUIDE.md)、[WEB_WORKBENCH.md](../product/WEB_WORKBENCH.md)、[v0.4.4 本地验收记录](../acceptance/V0-4-4-LOCAL-RELEASE-ACCEPTANCE.md)

## 背景

v0.4.4 的目标是把工作台从“功能入口集合”收敛为每天可直接使用的行动界面，同时确保首次安装、授权、
工作区身份、原生服务生命周期和网页写入路径在真实使用中保持一致。设计变更必须兼容现有
`features/projects`、`features/review`、纯渲染模块、WebContext/router/presenter 边界、旧入口和既有数据格式。

## 决策

1. **首页行动顺序固定**：今日简报置顶；捕捉并入简报快捷行；会议导入收进抽屉；宽屏简报使用日程/任务两栏，窄屏自动单列。
2. **设置保持白话**：工作区、AI 模型、飞书、自动化使用四张卡；高级与维护默认折叠；模型或飞书连接成功统一显示绿色 `✓`。
3. **授权和凭据按 workspace scope 归一**：旧版飞书凭据只在兼容读取路径中迁移到当前工作区作用域；设置页读取与 OAuth 回调相同的授权状态，不复制 doctor、provider、Keychain 或授权业务逻辑。
4. **原生服务只认自己的运行记录**：必须同时匹配 PID、启动时间和精确可执行路径；PID 被系统复用或记录过期时忽略旧记录，不能接管未知进程或误报 crash loop。
5. **网页简报沿用既有 workflow**：`run_brief` 返回实际写入的显式路径；Web handler 只负责调用既有提交/推送边界，提交仅包含当次简报、快照、用量和授权状态文件，禁止 `add -A`。
6. **发布保持内部包边界**：只生成 M2+ Apple Silicon arm64、ad-hoc、`INTERNAL-DEV` DMG；不引入新框架或第三方依赖，不把本地门禁误写成远端 CI 成功。

## 验证

- build identity：`v2026.09.10-df4ba1f-1cb9c2eb`，版本 `0.4.4`，build `9`。
- 本地门禁：Ruff、格式检查、mypy、`pytest tests/unit`（762 passed，5 warnings）、route contract（51 passed，1 warning）、
  `npm run test:frontend`、生产构建和 packaged smoke 均通过。
- Computer Use 真实工作区验收：从最新 DMG 启动，点击“重新生成”成功；生成后 vault 工作树保持干净，
  自动提交 `wb: brief 2026-09-10` 已推送，重启 App 后显示“已同步”。
- 本地 DMG：`dist/releases-local-v0.4.4-brief-fix-df4ba1f/0.4.4/arm64/`，SHA-256
  `d6104112cfce8598457c04126d355112d85e3957bb07bf6268f4a9411adbcdc8`。
- GitHub Actions 当时因账户额度/付款问题未启动；该 ADR 不把它记为 CI 通过。后续已在组织
  `SummitYifeng/SummitWorkbench` 上恢复额度并跑通质量门（见下方「后续修订」）。

## 后续边界

M3 上下文启动/会话收尾和 P2-03 组织级 OAuth Broker 仍不实施。后续仅处理现有功能缺陷、稳定性维护和
用户明确提出的增量需求；任何新的外部权限或服务都必须先新增 ADR 并重新确认产品边界。

## 后续修订（2026-09-11）

- **仓库迁移**：从个人账户迁移到组织 `SummitYifeng/SummitWorkbench`。Actions 分钟数按**仓库所有者**
  计费，组织 Team 额度对个人账户名下的仓库不生效；迁移后远端 CI 恢复。secrets、environment 与
  releases 均随仓库保留。
- **CI 暴露并修复一个缺陷**：macOS framework 版 Python（python.org 安装包）会 re-exec 到
  `Python.app/Contents/MacOS/Python`，使真实进程路径与 `sys.executable` 永不相等。原
  `_same_server_executable()` 因此把活着的 server 误判为复用 PID，删除活着的 runtime 记录并绕过
  `server_entry.py` 的重复实例保护——正是本 ADR 决策 4 要防的场景。修复为同时接受
  `sys.executable`、`sys._base_executable` 和 `sys.base_prefix/Resources/Python.app/.../Python`
  三个合法镜像，并新增回归测试；在触发该问题的 runner 上验证 `same_executable` 由 `False` 变为 `True`。
- **门禁补强**：`packaged App smoke` 已接入 CI 的 arm64 构建矩阵，不再只在本地执行；两个 workflow
  的 action 升级到 node24 大版本，项目 Node 工具链由 20 升到 24。
- **本地门禁前置**：`scripts/pre-push-gate.sh` + pre-push hook 在 push 前跑完 CI 的全部检查，并校验每个
  `uses:` 的 action ref 是否真实存在；Dependabot 接管 action / uv / npm 的版本漂移。
- **未验证清单的单一真源**：后续未验证项统一维护在
  [`docs/acceptance/OPEN-VERIFICATION-ITEMS.md`](../acceptance/OPEN-VERIFICATION-ITEMS.md)。
