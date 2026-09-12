# SummitWorkbench macOS 发布

当前 v0.4.4 build 9 的本地内部包已经完成发布验证。它是 arm64、M2+、ad-hoc 的
`INTERNAL-DEV` 包，不是 Developer ID/notarized 公网发行包。发布结论依据本地门禁和本机交互验收；
远端 CI 质量门（`.github/workflows/ci.yml`）已在 `SummitYifeng/SummitWorkbench` 上全绿。

tag 触发的 `.github/workflows/release.yml` 曾在 `v0.4.3-rc.3`–`v0.4.3-rc.5` 上成功运行；随后账户
用完免费 Actions 额度且没有有效支付方式，`v0.4.3` 与 `v0.4.4` 的 tag 运行被平台拒绝启动。仓库迁移到
`SummitYifeng` 组织后额度已恢复，并已用 `v0.4.4-rc.1` 实跑验证：签名 DMG、`update-feed.json`、
SBOM、SHA256SUMS 全部产出，作为 **prerelease** 发布到公开 Updates 仓库，`latest` 保持 `v0.4.2`
不变（rc 渠道不污染 stable）。自动发布链路因此可用；日常发布仍可继续使用本文件的本地脚本。

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

`dist/releases-local-v0.4.4-brief-fix-df4ba1f/0.4.4/arm64/SummitWorkbench-0.4.4-arm64-INTERNAL-DEV.dmg`

SHA-256：`d6104112cfce8598457c04126d355112d85e3957bb07bf6268f4a9411adbcdc8`

对应前端 build identity 为 `v2026.09.10-df4ba1f-1cb9c2eb`。发布目录同时包含
`SHA256SUMS`、`release-metadata.json`、`SBOM.json` 和本地验证摘要。

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
升级替换 App 不删除 profile、vault 或 Keychain；删除 App 也不会删除用户数据。若要
清理本机数据，须在 App 外另行备份并明确删除 `~/Library/Application Support/
SummitWorkbench`、日志目录和用户选择的 vault，不能把卸载 App 当成数据删除操作。
