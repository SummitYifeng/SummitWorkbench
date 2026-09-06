# ADR 0041 · P1-07D 远端规范化与一次性双设备验收

- 状态：进行中；`v0.4.3-rc` 候选完成后等待一次 Studio + Air 真机闭环
- 日期：2026-09-06
- 范围：P1-07D；不进入 P2-01B，不迁移 inbox、会议决策或项目正文

## 背景

v0.4.2 的 packaged App 暴露了 Dulwich clean-worktree 判定错误。随后确认现有工作台的
origin 仍是 GitHub SSH remote。生产同步必须有一个可验证、可诊断且与开发环境一致的远端
契约，不能把 SSH/scp-style URL 混同为离线或远端不可达。

## 决策

1. 生产 backend 固定为 Dulwich，生产 remote 只接受 HTTPS。其它 scheme 返回稳定错误
   `remote_scheme_unsupported`，同步状态与迁移门均保留该语义。
2. 设置中心提供 preview/apply/rollback 事务。preview 在临时 clone 中验证 PAT 认证、仓库
   身份、workspace marker、branch/upstream、fetch 与 ahead/behind；apply 重新验证后才更新
   origin、本机 profile 和 workspace-scoped Keychain。事务不提交、不推送、不改 vault，失败
   恢复旧 URL/profile，事务记录绝不含 PAT。
3. acceptance preflight 是只读门：检查 App/build、生产 backend、remote scheme、凭据、
   system Git 与 Dulwich dirty 结果、fetch、ahead/behind、schema 路径、备份可写性和
   automation role，并返回可复制脱敏报告。
4. 双设备自动验收使用两个临时 HOME、两个 clone 和临时 bare remote，覆盖 v1→v2、提交推送、
   fast-forward、双端离线追加、恢复联网、non-fast-forward/diverged-protected、数据保留与
   迁移失败回滚；dirty 回归覆盖 ignored directory、真正未跟踪文件和已跟踪删除。
5. `v0.4.3-rc.N` 只进入 draft/prerelease 渠道，feed 使用 tag-specific URL，不更新 `latest`。
   候选包完成 packaged integration 与双设备自动验收后，再由用户做唯一一次 Studio/Air 真机
   验收。稳定 `v0.4.3` 必须从同一 RC DMG 原资产晋升，哈希不变，禁止重新构建。

## 安全边界

PAT 只在请求生命周期内以 `SecretStr` 传递，绝不进入 URL、profile、事务记录、日志、报告或
仓库。公开更新仓库只提供 DMG/feed 的完整性（Ed25519、大小和 SHA-256），不提供保密性；
任何私有 workspace 内容都不得放入公开更新仓库。

## 未决外部验收

需要用户在 Studio 输入 GitHub username 与 workspace-scoped PAT，点击 preview/apply（如需可
rollback），然后在 Air 完成一次引导式往返同步。只有该验收成功后，才允许将完全相同的 RC
DMG 晋升为稳定 `v0.4.3`。
