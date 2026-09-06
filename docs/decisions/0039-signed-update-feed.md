# ADR 0039 · 内部 arm64 签名更新 feed

- 状态：部分实现（P1-07；离线代码与质量门通过，真实 feed 发布验收待补）
- 日期：2026-09-06
- 依据：产品化计划 P1-07、ADR 0032/0038、用户平台约束（仅 M2+ Apple Silicon、内部/个人自用）

## 背景

内部用户需要知道新 DMG 是否适用于当前 Mac，也需要避免损坏或被篡改的包进入安装流程。
本产品不面向 Apple Store 或商业外部分发，因此不把 Developer ID/notarization 作为内部
更新检查的安全信任根；但 App 包和更新 feed 仍必须互相独立、可审计。

## 决策

采用一个小而明确的 JSON feed，不在本包引入 Sparkle 自动安装依赖。每个 artifact 包含
版本、build、`arm64` 架构、最低 macOS、HTTPS 下载地址、DMG 大小、SHA-256、release
notes 和 Ed25519 签名。签名正文由固定字段按换行拼接，Python 发布脚本和 Swift App
共同实现；App 只信任自身 manifest 中固定的公钥，不信任 feed 自己携带的公钥。

App 首次准备好工作台后默认每天后台检查，顶部“检查更新”可手动触发。候选必须满足
架构、最低系统、版本/build 更高、HTTPS、大小/hash/签名字段有效；签名不通过则拒绝。
用户可选择跳过版本或稍后提醒。确认下载后先落到 Application Support 的 updates 目录，
校验大小和 SHA-256，再打开 DMG；不会自动替换 App、写入 vault、改 profile 或触发同步。
没有 feed 配置时保持当前 App 正常工作并记录稳定错误码。

发布脚本只在显式提供 `UPDATE_SIGNING_KEY_PATH` 与 `UPDATE_FEED_URL` 时生成 feed；私钥不
写入 manifest、DMG、日志、metadata 或仓库。普通内部 ad-hoc DMG 可以在无私钥时继续构建，
但不会冒充可自动更新的发布包。

## 未完成与边界

当前完成的是可离线验证的生产接线和安全拒绝路径。开发环境的 OpenSSL 不支持 Ed25519，
因此真实签名生成单测按能力安全跳过；发布机必须使用支持 Ed25519 的 OpenSSL。计划原始
验收要求的真实 HTTPS feed、已签名/公证 N-1→N、下载中断、磁盘不足、回滚启动尚未执行。
用户已明确不需要 Apple Developer ID；若要完成原计划的 notarized 验收，仍需改变这一
外部约束，而不是由本地测试伪造通过。
