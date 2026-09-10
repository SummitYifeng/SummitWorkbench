# v0.4.4 build 9 · 本地发布与工作区交互验收

状态：✅ 已完成（2026-09-10）

本记录只描述本地门禁和脱敏后的交互结果，不包含真实凭据、会议正文或 vault 内容。GitHub Actions
因账户付款/额度问题未启动，因此本记录不宣称远端 CI 全绿。

## 1. 交付物

| 项目 | 结果 |
|---|---|
| 版本 / build | `0.4.4` / `9` |
| 架构 / 分发 | `arm64` / `INTERNAL-DEV`，M2+ Apple Silicon |
| 前端 build identity | `v2026.09.10-df4ba1f-1cb9c2eb` |
| 源码修复 | `df4ba1f` |
| 静态产物 | `2dc9dd7` |
| DMG | `dist/releases-local-v0.4.4-brief-fix-df4ba1f/0.4.4/arm64/SummitWorkbench-0.4.4-arm64-INTERNAL-DEV.dmg` |
| DMG SHA-256 | `d6104112cfce8598457c04126d355112d85e3957bb07bf6268f4a9411adbcdc8` |

## 2. 本地门禁

- Ruff lint：通过。
- Ruff format check：通过（312 files already formatted）。
- mypy：通过（38 source files，无错误）。
- `pytest tests/unit`：762 passed，5 warnings。
- Web route contract：51 passed，1 warning。
- `npm run test:frontend`：build identity、feature contract、projects/review 纯渲染、浏览器交互契约全部通过。
- 生产前端构建、PyInstaller server/worker 构建、release 验证和 packaged smoke：通过。

## 3. Computer Use 交互验收

使用上述 DMG 启动隔离的验收 App，并连接用户已授权的实际工作区；未删除或重置 vault。

1. App 启动后显示 build `v2026.09.10-df4ba1f-1cb9c2eb`，服务正常，今日页和六个页签可用。
2. 点击“重新生成”完成简报生成，页面回到正常今日内容。
3. 命令行核对工作区工作树干净，`origin/main...HEAD` 为 `0/0`；自动提交消息为
   `wb: brief 2026-09-10`，生成内容已推送。
4. 退出并重启 App 后，顶部显示“已同步”，未再出现由网页简报生成引起的 `dirty-protected`。

## 4. 修复范围

- 网页简报提交使用 workflow 返回的显式持久化路径，不会把其他用户改动加入提交。
- 旧版飞书凭据兼容迁移到 workspace scope，设置页显示实际授权状态并统一绿色 ✓。
- 旧 OAuth callback 入口保持兼容。
- 原生运行记录在 PID 复用或过期时不会误认旧服务，降低 crash loop 误判风险。
- UI/UX 方案保持审批、同步保护、数据格式、旧入口和本地数据边界不变。

## 5. 未覆盖项

- GitHub Actions 远端运行：因账户付款/额度阻塞，未启动。
- Developer ID、notarization、Intel/Windows 和公开自动更新 feed：不属于当前 `INTERNAL-DEV` 交付范围。
- M3 与 P2-03：按 ADR 0044 和当前产品边界不实施。

## 6. v0.4.4 增量可靠性回归（2026-09-10）

本节记录 build 9 之后的源码增量，不改变上方已发布 DMG 的历史身份。

- 自动化简报提交路径补齐运行心跳及 workflow 返回的全部显式持久化路径；系统信号不会再单独制造
  `dirty-protected`。
- 设置页「立即运行」改为强制执行语义；顶部「刷新」同时更新业务数据和同步横幅。
- 本地回归：`pytest tests/unit` 763 passed、前端契约测试通过、生产构建与静态产物验证通过。
- 使用 Computer Use 连接本机 `127.0.0.1:8797` 真实界面：设置页立即运行成功；核对 vault 工作树清洁；刷新后
  同步接口为 `ready`，顶部旧保护横幅消失。
- 同一界面回归项目线视图：打开后焦点进入弹层内的「✎ 日志」，按 Escape 关闭后焦点归还到原始项目按钮；
  嵌套日志/产物弹层沿用原始返回焦点。
- 本轮未执行真实飞书写回，未推送 vault 内容；项目代码提交与推送另按当前开发任务处理。

## 7. UX/UI 增量复核（2026-09-10）

本节记录 build 9 之后源码继续演进后的本地浏览器复核，不改变上方已发布 DMG 的历史身份。

- 当前源码提交：`ce0b27e`；设置页布局修复已提交并推送到 `main`。
- 质量门复核：`pytest tests/unit` 766 passed、5 warnings；Web route contract 1 passed；ruff、format、mypy 全部通过。
- CUA 真实浏览器复核覆盖今日、审批、项目、指南、第二大脑和设置：导入抽屉、项目线视图、指南搜索、问答范围切换、设置高级区均可正常打开/关闭；审批预演显示 `DRY-RUN（零写入）`，未执行写回。
- 设置页及高级维护区的页面宽度复核为 `scrollWidth=clientWidth`，修复了真实浏览器中发现的横向滚动。
- 未覆盖：真实文件导入、真实模型回答、真实飞书写回、真实 OAuth、320/390px 与 200% 缩放、WKWebView/打包 App 黑盒验收、动态端口迁移。
