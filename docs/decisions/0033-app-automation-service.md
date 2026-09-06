# ADR 0033 · App 内自动化 worker 与 SMAppService

- 状态：🟡 P1-01 现场修复中；SMAppService 注册/取消需在目标 Mac 做一次可逆黑盒确认
- 日期：2026-09-06
- 里程碑：v0.4.1 → P1-01
- 依据：计划 P1-01、ADR 0031 主设备声明、ADR 0032 arm64 内部分发

## 背景与决策

旧的 `deploy/launchd` 脚本把 `wb`、`WORK_ROOT` 和用户目录写入 `~/Library/LaunchAgents`，不适合 App 内设置、profile 作用域和版本升级。
P1-01 改为由 App 设置页保存本机 `Library/Application Support/SummitWorkbench/profiles/<workspace_id>/automation.json`，
再由原生壳通过 `SMAppService.loginItem(identifier:)` 管理包内 helper。App 不直接写 LaunchAgents/LaunchDaemons，不调用
launchctl；旧脚本和 README 只作为开发/迁移兼容路径保留。

helper 位于 `Contents/Library/LoginItems/SummitWorkbenchAutomation.app`，只负责每分钟轮询并以绝对 bundle 路径启动
`Contents/Helpers/SummitWorkbenchWorker`。worker 是 PyInstaller 单文件 arm64 可执行文件，直接读取 active profile 和
workspace id，不依赖 shell、当前目录或 `PATH`，也不启动 Web server。worker 自身按 workspace 时区、星期、设定时间和
`last_run_at` 判断是否到期；睡眠唤醒后的再次轮询因此不会重复生成同一天的简报。

执行门按以下顺序生效：workspace/profile 可读且可写 → vault 内 automation-primary 声明与 device id 匹配 → 本机任务启用且到期
→ `current_snapshot` 通过 dirty/diverged 保护 → workflow 写入。secondary 返回成功的 `not-primary` 跳过结果，不写 vault，也不
更新本机最近结果账本。会议同步暂以显式安全跳过状态呈现，避免在未有独立幂等实现前产生外部重复动作。

启用任一任务时，原生管理器先检查嵌套 helper 的 `CFBundleVersion`、bundle identifier 与主 App build 一致，并用 Security API 验证 helper 签名，
再按 `SMAppService.Status` 注册 `SMAppService`；`requiresApproval` 等待用户在系统设置批准，不重复 register；`notFound` 不调用注销。
全部任务停用时仅对已注册或待批准服务注销。旧 helper 不会因版本不同继续运行：注册前版本/签名校验失败，worker 运行时还要通过
当前 workspace compatibility writer gate。helper 与 worker 随每个 App 包一起构建并按嵌套代码顺序 ad-hoc 签名。

## 权限与升级

本产品只面向 M2+ Apple Silicon 的内部/个人自用，不申请 Developer ID、不 notarize、不上 App Store。`SMAppService` 登录项由用户
对当前 App 的启停设置控制；不新增飞书权限，不读取或回显 token。升级替换 App 后，旧注册项保留的 helper 路径必须通过版本/签名校验，
新设置保存时重新注册；校验失败只记录脱敏错误，不执行旧 helper 的不兼容写入。

## 验证证据

- 自动化设置、API 校验、主/辅设备门控、dirty-protected、空 PATH 和唤醒幂等均由离线临时目录测试覆盖。
- `BUILD_NUMBER=11 ARCH=arm64 OUTPUT_APP=dist/p101-check/SummitWorkbench.app scripts/build-macos-app.sh` 通过；
  `SummitWorkbenchWorker` 与嵌套 helper 均为 arm64，主 App `codesign --verify --deep --strict` 通过。
- `env -i HOME=<临时目录> WB_PANEL_MODE=production <bundle>/Contents/Helpers/SummitWorkbenchWorker --job brief --json`
  成功返回 `skipped/尚未选择工作区`，证明 worker 不要求 PATH。
- 目标用户环境首次黑盒发现系统设置未出现登录项，且旧实现停用路径记录 `Operation not permitted`；已补状态机与脱敏诊断日志，待新包复验。具体人工步骤：
  1. 打开当前 P1-01 arm64 App，在“设置 → App 内自动化”只启用“晨间简报”并保存；系统设置的“登录项”应出现 SummitWorkbench Automation。
  2. 回到 App 停用全部自动化并保存；系统设置中该登录项应消失，设置页不应再显示注册失败。
  3. 不需要等待 08:00；可用“立即运行”验证主设备门控和最近结果，确认不会产生重复简报。
