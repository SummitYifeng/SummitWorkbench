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
