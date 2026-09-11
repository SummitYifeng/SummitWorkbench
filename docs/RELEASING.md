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

## 用户安装与卸载

把对应架构的 DMG 拖入 `/Applications`，首次启动后按图形化向导新建或连接 workspace。
升级替换 App 不删除 profile、vault 或 Keychain；删除 App 也不会删除用户数据。若要
清理本机数据，须在 App 外另行备份并明确删除 `~/Library/Application Support/
SummitWorkbench`、日志目录和用户选择的 vault，不能把卸载 App 当成数据删除操作。
