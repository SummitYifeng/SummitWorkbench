# ADR 0041 · P1-07D 远端规范化与一次性双设备验收

- 状态：已完成（2026-09-07 Studio + Air 真机闭环，候选包 build 23）
- 日期：2026-09-06（2026-09-07 更新 TLS 阻塞处理与真机闭环）
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
   恢复旧 URL/profile，事务记录绝不含 PAT。旧 schema 的只读保护对这三个受控端点例外，
   以打破“迁移要求 HTTPS、转换又被只读拦截”的循环；其它 vault/profile 写入仍被只读保护。
3. acceptance preflight 是只读门：检查 App/build、生产 backend、remote scheme、凭据、
   system Git 与 Dulwich dirty 结果、fetch、ahead/behind、schema 路径、备份可写性和
   automation role，并返回可复制脱敏报告。
4. 双设备自动验收使用两个临时 HOME、两个 clone 和临时 bare remote，覆盖 v1→v2、提交推送、
   fast-forward、双端离线追加、恢复联网、non-fast-forward/diverged-protected、数据保留与
   迁移失败回滚；dirty 回归覆盖 ignored directory、真正未跟踪文件和已跟踪删除。
5. `v0.4.3-rc.N` 只进入 draft/prerelease 渠道，feed 使用 tag-specific URL，不更新 `latest`。
   候选包完成 packaged integration 与双设备自动验收后，再由用户做唯一一次 Studio/Air 真机
   验收。稳定 `v0.4.3` 必须从同一 RC DMG 原资产晋升，哈希不变，禁止重新构建。
6. 若 App 被强制退出而遗留自有 server，下一次启动只在 runtime record 与当前 bundle
   server 可执行文件精确匹配时终止该孤儿进程并重新启动；未知进程仍绝不接管或终止。

## 安全边界

PAT 只在请求生命周期内以 `SecretStr` 传递，绝不进入 URL、profile、事务记录、日志、报告或
仓库。公开更新仓库只提供 DMG/feed 的完整性（Ed25519、大小和 SHA-256），不提供保密性；
任何私有 workspace 内容都不得放入公开更新仓库。

## 验收结果（2026-09-07 · 已闭环）

最终候选包 build 23（git `23b7455`，DMG SHA-256 `7ea55042…5ffc89f9`）在 Mac Studio
（automation-primary，device `51885d3d`）与 MacBook Air（secondary，device `8fd4294b`）安装
同一 DMG。Studio 完成 remote preview/apply 与 schema v1→v2 迁移；两端 acceptance preflight
全 PASS（fetch PASS、ahead=0/behind=0、dirty=False）；验证 Studio→Air 与 Air 离线→Studio 双向
同步、pending 归零、Air 自动化安全跳过、双端离线冲突进入 `diverged-protected`
（不 force/reset/rebase/stash、不丢数据）。进入 P2-01B 的前置门已解除。

## 2026-09-07 · 收口期追加修复

- 根因 1（ahead/behind 永不清零）：Dulwich `fetch()/push()` 传 URL 而非 remote 名，导致
  `_import_remote_refs` 永不执行、`refs/remotes/origin/*` 停在旧值。改为传 remote 名，
  push 成功后 ahead/behind 与 `pending_wb_commits` 归零，状态不再回退为 `local-ahead`。
- 根因 2（packaged fetch 失败）：App 经 Finder 启动时无代理环境变量，dulwich 直连
  `github.com` 被本网络阻断。无 env 代理时回退 macOS 系统代理（`scutil --proxy`），
  TLS 校验保持 `CERT_REQUIRED` + bundled CA。
- preflight 报告完整 build identity（version/build/frontend_build/git_revision），fetch 失败
  输出稳定脱敏码（auth/tls/certificate/proxy/credentials-unavailable/network/backend）与
  host/credential/CA/proxy 诊断，不含 PAT、URL 路径或本机路径。
- Air「连接已有工作台」向导新增 PAT 输入与 `connect-remote` 预检流；secondary 的自动化与
  手动简报/周报生成改为友好跳过（200 `ok=true`），不显示红色 ApiError，写入仍被角色门控。

## 操作顺序

旧 schema 工作区应先在设置中心完成 HTTPS remote 预览与转换，再点击“升级工作区 schema”。
转换成功后重新加载设置页，确认工作区状态为 ready，再执行 schema 迁移；迁移前仍不得有
未提交改动、ahead/behind 或不可达远端。
