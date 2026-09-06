# ADR 0039 · 内部 arm64 签名更新 feed

- 状态：进行中（P1-07C；本地与远端发布闭环完成，真机/双设备验收待补）
- 日期：2026-09-06
- 依据：产品化计划 P1-07、ADR 0032/0038、用户平台约束（仅 M2+ Apple Silicon、内部/个人自用）

## 背景

内部用户需要知道新 DMG 是否适用于当前 Mac，也需要避免损坏或被篡改的包进入安装流程。
本产品不面向 Apple Store 或商业外部分发，因此不把 Developer ID/notarization 作为内部
更新检查的安全信任根；但 App 包和更新 feed 仍必须互相独立、可审计。

## 决策

采用一个小而明确的 JSON feed，不在本包引入 Sparkle 自动安装依赖。每个 artifact 包含
版本、build、`arm64` 架构、最低 macOS、HTTPS 下载地址、DMG 大小、SHA-256、release
notes、workspace schema compatibility 和 Ed25519 签名。签名正文由固定字段按换行拼接，Python 发布脚本和 Swift App
共同实现；App 只信任自身 manifest 中固定的公钥，不信任 feed 自己携带的公钥。

App 首次准备好工作台后默认每天后台检查，顶部“检查更新”可手动触发。候选必须满足
架构、最低系统、版本/build 更高、HTTPS、大小/hash/签名字段有效；签名不通过则拒绝。
用户可选择跳过版本或稍后提醒。确认下载前先检查 workspace schema compatibility，随后落到
Application Support 的 updates 目录，校验大小和 SHA-256，再打开 DMG；不会自动替换 App、
写入 vault、改 profile 或触发同步。没有 feed 配置时保持当前 App 正常工作并给出可见反馈。

发布脚本只在显式提供 `UPDATE_SIGNING_KEY_PATH`、`UPDATE_FEED_URL` 与
`UPDATE_DOWNLOAD_URL` 时生成 feed；tag release 从受保护的 `release` environment 取得
Ed25519 私钥及公开更新仓库配置，并额外强制 OpenSSL 3 真实生成/验签。公开更新仓库为
`yifeng93/SummitWorkbench-Updates`；私有代码仓库不作为 App 的匿名下载源。跨仓库发布所需
的写入凭据通过 `UPDATE_REPO_TOKEN` secret 提供。私钥不写入 manifest、DMG、日志、metadata
或任何仓库。普通内部 ad-hoc DMG 可以在无私钥时继续构建，但不会冒充可自动更新的发布包；
tag job 失败时只允许保留公开仓库 draft，不得发布 partial latest。

## 验收与边界

本地已验证 workflow actionlint、OpenSSL 3 真实 Ed25519 生成/验签，以及 Swift 注入式行为
测试。远端 `v0.4.1` tag release 已在 protected `release` environment 中成功完成；后续
`v0.4.2` 修复 packaged App 内置模板路径并重新发布后，公开
更新仓库中的 feed 与 DMG 已下载复核，feed 声明的大小和 SHA-256 与 DMG 一致。真机和双
设备验收仍属于外部证据，尚未宣称通过。公开更新仓库只提供完整性（HTTPS、SHA-256、
Ed25519），不提供保密性；不得放入私有工作区内容或秘密。不纳入本项目的仍包括 Developer
ID/notarization、Apple Store、Windows 和 Intel 分发。
