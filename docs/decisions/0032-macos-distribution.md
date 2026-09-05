# ADR 0032 · macOS 签名分发、notarization 与 DMG

- 状态：✅ 内部 arm64 发布实现完成；M2+ 真机验收待执行
- 日期：2026-09-06
- 里程碑：v0.4.1 → P0-13
- 依据：计划 P0-13（实现要求 1–10、真机矩阵与验收）、P0-12 动态服务生命周期、ADR 0030 packaged Git

## 背景与决策

App bundle 必须自包含、可审计并能区分内部包。构建脚本现在从
`pyproject.toml` 读取 `CFBundleShortVersionString`，`BUILD_NUMBER` 单独由 CI run 或显式发布参数提供；
产品只接受 `arm64` Apple Silicon（M2+），写入 App manifest 和发布 metadata，不生成 Intel/universal 包。

构建、ad-hoc 签名、smoke 和最终移动均在临时目录完成。嵌套 dylib/framework 先签名，然后签 PyInstaller
server executable，最后签 App；使用最小 `packaging/entitlements.plist`，不添加 library-validation
绕过权限。构建成功后才原子替换输出 App。

`release-macos.sh` 只接受显式 build number，固定生成 `INTERNAL-DEV` arm64 包，不读取 Apple 证书、
Keychain 签名 profile 或 notarization 凭据。App 名称、bundle display name、manifest、DMG 文件名都
明显标识内部用途，并且不尝试 notarization/staple。

每个架构的发布目录包含 DMG、`SHA256SUMS`、`release-metadata.json`、CycloneDX `SBOM.json` 和
notary 摘要；metadata 记录产品版本、build、架构、最低 macOS、Git commit、workspace schema range
和 bundle/DMG digest。DMG 内容包含 App 与 `/Applications` 引导。

## 验证

- `tests/unit/test_packaging_contract.py` 覆盖版本来源、显式 build/架构、内部 ad-hoc、签名工具、
  metadata、SBOM、entitlement 和隐私验证契约。
- 原生启动器已修复跨语言运行记录的 ISO-8601 日期解码；readiness 超时重试前会终止当前 App
  自己创建的子进程，避免孤儿 server 继续占用端口或阻塞后续 runtime record。对应契约测试先失败后通过。
- `BUILD_NUMBER=1 ARCH=arm64 scripts/build-macos-app.sh` 在当前 Apple Silicon 机器通过：前端构建、
  47 项 packaged/native 回归、PyInstaller、Swift 离线编译、自包含 server 动态端口 smoke。
- 修复后重新编译的 arm64 App 在当前 Mac Studio 真实用户环境中约 1 秒完成 `service_ready`，未再进入
  `crashLoop`；此前失败包的残留测试进程已清理。
- `scripts/verify-macos-release.sh dist/SummitWorkbench.app` 通过：内部 ad-hoc strict codesign、
  bundle 清单、开发路径/secret scan、动态端口 `/api/version` 离线启动。
- `scripts/release-macos.sh` 在临时输出目录生成 arm64 `INTERNAL-DEV.dmg`、checksum、SBOM、metadata 和
  notary `not-applicable` 摘要。

## 未执行的外部门

本产品明确不追求 Developer ID、notarization、Intel、Windows 或 App Store 发布。仍需在 M2+ Apple Silicon
上人工验证 DMG 安装/启动、创建 workspace、profile 切换、升级保留 profile/vault/Keychain，以及删除 App
后用户数据仍保留；这些验证不需要新增飞书权限。
