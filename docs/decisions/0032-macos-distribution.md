# ADR 0032 · macOS 签名分发、notarization 与 DMG

- 状态：⚠ 离线实现完成；Apple Developer ID、notarization 与真机发布门未执行
- 日期：2026-09-06
- 里程碑：v0.4.1 → P0-13
- 依据：计划 P0-13（实现要求 1–10、真机矩阵与验收）、P0-12 动态服务生命周期、ADR 0030 packaged Git

## 背景与决策

App bundle 必须自包含、可审计并能区分开发包与正式发布包。构建脚本现在从
`pyproject.toml` 读取 `CFBundleShortVersionString`，`BUILD_NUMBER` 单独由 CI run 或显式发布参数提供；
`ARCH` 只接受 `arm64` / `x86_64`，写入 App manifest 和发布 metadata，不把当前机器包标成 universal。

构建、签名、smoke 和最终移动均在临时目录完成。嵌套 dylib/framework 先签名，然后签 PyInstaller server
executable，最后签 App；正式路径使用 Developer ID Application、hardened runtime、timestamp 和
`packaging/entitlements.plist`，没有 library-validation 绕过权限。构建成功后才原子替换输出 App。

`release-macos.sh` 只接受显式 build number，使用 `NOTARY_PROFILE` 指向已存于 macOS Keychain 的
`notarytool` profile，绝不把密码放入仓库、环境日志或 argv。完整身份与 profile 缺任一项时强制切换为
`UNSIGNED-DEV`：App 名称、bundle display name、manifest、DMG 文件名都明显标识开发包，并且不尝试
notarization/staple。

每个架构的发布目录包含 DMG、`SHA256SUMS`、`release-metadata.json`、CycloneDX `SBOM.json` 和
notary 摘要；metadata 记录产品版本、build、架构、最低 macOS、Git commit、workspace schema range
和 bundle/DMG digest。DMG 内容包含 App 与 `/Applications` 引导。

## 验证

- `tests/unit/test_packaging_contract.py` 覆盖版本来源、显式 build/架构、unsigned-dev、签名工具、
  metadata、SBOM、entitlement 和隐私验证契约。
- `BUILD_NUMBER=1 ARCH=arm64 scripts/build-macos-app.sh` 在当前 Apple Silicon 机器通过：前端构建、
  47 项 packaged/native 回归、PyInstaller、Swift 离线编译、自包含 server 动态端口 smoke。
- `scripts/verify-macos-release.sh dist/SummitWorkbench.app` 通过：ad-hoc unsigned-dev strict codesign、
  bundle 清单、开发路径/secret scan、动态端口 `/api/version` 离线启动。
- `scripts/release-macos.sh` 在临时输出目录生成 arm64 `UNSIGNED-DEV.dmg`、checksum、SBOM、metadata 和
  notary `not-run` 摘要。

## 未执行的外部门

当前没有 Developer ID Application 身份或 notarytool Keychain profile，不能声称 notarized DMG，不能把
`spctl`/stapler 成功写成通过。当前机器也不能替代原生 x86_64 runner；Apple Silicon、Intel、clean-account、
升级保留 profile/vault/Keychain、删除 App 保留数据以及同事图形化安装仍需用户提供环境后人工执行。
