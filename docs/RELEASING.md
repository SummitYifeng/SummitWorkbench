# SummitWorkbench macOS 发布

## 本机离线开发包

发布脚本要求显式 build number，并按架构命名产物。没有 Developer ID 和
`notarytool` Keychain profile 时，脚本只生成名字和 App 界面均标明
`UNSIGNED-DEV` 的开发包：

```bash
BUILD_NUMBER=123 ARCH=arm64 scripts/release-macos.sh
```

产物包含 App、DMG、`SHA256SUMS`、`release-metadata.json`、`SBOM.json` 和 notary
结果摘要。`UNSIGNED-DEV` 不能作为 release 或发给同事；它只用于离线启动 smoke 和
包内容检查。

## 正式发布

签名身份与 notarization 凭据不写入仓库、脚本参数或命令历史。把 notarization 凭据
预先存入 macOS Keychain profile，然后在受保护的 CI/发布终端提供 profile 名称：

```bash
BUILD_NUMBER=456 ARCH=arm64 \
SIGNING_IDENTITY='Developer ID Application: Example' \
NOTARY_PROFILE='summitworkbench-release' \
scripts/release-macos.sh
```

正式路径按 `arm64` / `x86_64` 分别构建，完成 hardened runtime、timestamp、DMG、
`notarytool submit --keychain-profile`、staple、`codesign`/`spctl`/stapler 验证后才
发布。Intel 包必须在原生 x86_64 runner/设备上验证，不能用 Rosetta 代替。

## 用户安装与卸载

把对应架构的 DMG 拖入 `/Applications`，首次启动后按图形化向导新建或连接 workspace。
升级替换 App 不删除 profile、vault 或 Keychain；删除 App 也不会删除用户数据。若要
清理本机数据，须在 App 外另行备份并明确删除 `~/Library/Application Support/
SummitWorkbench`、日志目录和用户选择的 vault，不能把卸载 App 当成数据删除操作。
